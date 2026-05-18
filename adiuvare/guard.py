import asyncio
import contextlib
import inspect
from dataclasses import replace
from pathlib import Path
from typing import Any
from functools import wraps

from .config import build_snapshot, load_config
from .core.events import EventHooks
from .core.gate import configure_trackA, run_trackA
from .core.models import RequestContext
from .core.pipeline import Pipeline
from .policies import BUILTIN_POLICIES
from .runtime_analysis import (
    analyst_prompt,
    build_report,
    local_analyst_answer,
    report_prompt,
    report_summary_prompt,
)
from .signals.ai import AISignal
from .signals.behavior import BehaviorSignal
from .signals.context import ContextSignal
from .signals.identity import IdentitySignal
from .signals.ip_rep import IPRepSignal
from .signals.payload import PayloadSignal
from .state.audit_log import AuditLog
from .state.event_stream import RedisEventStream, UnixSocketEventStream
from .state.identity_store import IdentityStore, ThreadSafeIdentityStore
from .state.persistence import (
    checkpoint_state,
    load_identity_state,
    load_whitelist_state,
    start_checkpoint_loop,
)
from .state.whitelist import WhitelistStore


def _wrap_route_handler(fn):
    if inspect.iscoroutinefunction(fn):
        @wraps(fn)
        async def async_wrap(*args, **kwargs):
            return await fn(*args, **kwargs)

        return async_wrap

    @wraps(fn)
    def sync_wrap(*args, **kwargs):
        return fn(*args, **kwargs)

    return sync_wrap


class Guard:
    """Own the configured signals, state stores, runtime stream, and framework hooks for one app instance."""

    def __init__(
        self,
        preset: str = "balanced",
        config_path: str | Path | None = None,
        soft_signals: list | None = None,
        hard_signals: list | None = None,
        flaskmode: bool = False,
    ) -> None:
        self._cfg = load_config(config_path, preset=preset)
        self._cfg_snap = build_snapshot(self._cfg)
        self._id_store = ThreadSafeIdentityStore() if flaskmode else IdentityStore()
        self._wl = WhitelistStore()
        self._hard_sigs = list(hard_signals or [])
        Path(".adiuvare").mkdir(exist_ok=True)
        self._state_DBpath = Path(self._cfg.runtime.state_db_path)
        self._audit = AuditLog(self._cfg.runtime.audit_db_path)
        sigs = soft_signals or [
            PayloadSignal(),
            BehaviorSignal(self._id_store),
            IdentitySignal(self._id_store),
            ContextSignal(),
            IPRepSignal(),
        ]
        self._pipeline = Pipeline(
            self._id_store,
            soft_signals=sigs,
            ai_sig=self._mk_ai_sig(),
        )
        self._hooks = EventHooks()
        self._stream = self._mkstream()
        if hasattr(self._stream, "set_command_handler"):
            self._stream.set_command_handler(self.handlestreamcmd)
        self.policies = dict(BUILTIN_POLICIES)
        self._route_cfg: dict[str, Any] = {}
        self._route_overview: dict[str, dict[str, Any]] = {}
        self._last_identity: str | None = None
        self._last_sink: dict[str, Any] | None = None
        self._bg_task: asyncio.Task | None = None
        self._bg_started = False
        self._bg_lock: asyncio.Lock | None = None
        configure_trackA(wl=self._wl, hard_sigs=self._hard_sigs)

    @property
    def hooks(self) -> EventHooks:
        return self._hooks

    @property
    def config(self):
        return self._cfg

    @property
    def pipeline(self):
        return self._pipeline

    @classmethod
    def from_config(
        cls,
        config_path: str | Path,
        preset: str = "balanced",
        soft_signals: list | None = None,
        hard_signals: list | None = None,
    ):
        """Build a guard from an explicit config file path."""

        return cls(
            preset=preset,
            config_path=config_path,
            soft_signals=soft_signals,
            hard_signals=hard_signals,
        )

    @classmethod
    def auto(
        cls,
        app: Any,
        preset: str = "balanced",
        config_path: str | Path | None = None,
        soft_signals: list | None = None,
        hard_signals: list | None = None,
    ):
        """Build a guard and attach the right middleware based on the app object."""

        guard = cls(
            preset=preset,
            config_path=config_path,
            soft_signals=soft_signals,
            hard_signals=hard_signals,
            flaskmode=hasattr(app, "wsgi_app"),
        )
        if hasattr(app, "wsgi_app"):
            guard.use(app, framework="flask")
        else:
            guard.use(app, framework="fastapi")
        return guard

    async def inspect(self, ctx: RequestContext, *, trackB: bool = True):
        """Run Track A first, then optional Track B scoring, streaming, and audit writes.

        A failed Track A gate short-circuits before any Track B work happens.
        """

        if ctx.snapshot is None:
            ctx.snapshot = self._cfg_snap

        self._last_identity = ctx.identity
        gate = run_trackA(ctx, self._id_store)
        if not gate.passed:
            self._hooks.emit_block(gate)
            return gate, None

        if not trackB:
            return gate, None

        event = await self._pipeline.trackB(ctx)
        if event is not None:
            await self._stream.emit(event)
            self._audit.write(event)
        if event is not None:
            self._hooks.emit_event(event)
        return gate, event

    def handle(self, ctx: RequestContext):
        return self.inspect(ctx)

    @property
    def event_stream(self):
        return self._stream

    @property
    def whitelist(self):
        return self._wl

    def record_sink_detection(
        self,
        *,
        statement: str,
        normalised: str,
        confidence: float,
        fingerprint: str = "",
    ) -> None:
        """Record one sink-side detection so operator history can show how it was triggered."""

        self._last_sink = {
            "statement": statement,
            "normalised": normalised,
            "confidence": confidence,
            "fingerprint": fingerprint,
        }
        self._audit.write_patch("sink_hit", self._last_sink)

    def elevate_identity_from_sink(self, identity: str | None = None) -> None:
        who = identity or self._last_identity
        if not who:
            return
        self._id_store.apply_score(who, 0.85)

    def checkpoint(self) -> None:
        """Persist the current identity and operator state snapshot."""

        checkpoint_state(self._state_DBpath, self._id_store, self._wl)

    async def startbgtasks(self) -> None:
        """Restore state, start the event stream, and launch periodic checkpoints once."""

        if self._bg_started:
            return

        load_identity_state(self._state_DBpath, self._id_store)
        load_whitelist_state(self._state_DBpath, self._wl)
        await self._stream.start()
        self._bg_task = asyncio.create_task(
            start_checkpoint_loop(self._state_DBpath, self._id_store, self._wl)
        )
        self._bg_started = True

    async def ensure_started(self) -> None:
        """Start background runtime tasks exactly once even under concurrent callers."""

        if self._bg_started:
            return
        if self._bg_lock is None:
            self._bg_lock = asyncio.Lock()
        async with self._bg_lock:
            if self._bg_started:
                return
            await self.startbgtasks()

    async def shutdown(self) -> None:
        """Stop background tasks, checkpoint state, and close the active stream backend."""

        if self._bg_task is not None:
            self._bg_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._bg_task
            self._bg_task = None

        self.checkpoint()
        await self._stream.stop()
        self._bg_started = False

    async def check(
        self,
        identity: str,
        payload: dict | str | None = None,
        context: dict[str, Any] | None = None,
    ):
        """Build a request context from SDK-style inputs and run the normal inspection flow.

        Dict payloads are JSON-encoded first, and a route snapshot is inferred from
        the supplied path when you do not pass one explicitly.
        """

        ctxdata = context or {}
        route_cfg = dict(ctxdata.get("route_cfg") or {})
        if "path" in ctxdata and not route_cfg:
            route_cfg = self.routecfg(str(ctxdata["path"]))

        if isinstance(payload, dict):
            import json

            payload_text = json.dumps(payload)
        else:
            payload_text = payload

        endpoint = str(ctxdata.get("endpoint") or ctxdata.get("path") or "/sdk")
        ctx = RequestContext(
            identity=identity,
            payload=payload_text,
            url=str(ctxdata.get("url") or endpoint),
            method=str(ctxdata.get("method") or "INTERNAL"),
            headers=dict(ctxdata.get("headers") or {}),
            ip=str(ctxdata.get("ip") or "127.0.0.1"),
            endpoint=endpoint,
            sensitivity=str(ctxdata.get("sensitivity") or route_cfg.get("sensitivity") or "internal"),
            snapshot=self.routesnap(route_cfg),
        )
        return await self.inspect(ctx, trackB=bool(route_cfg.get("trackB", True)))

    def check_sync(
        self,
        identity: str,
        payload: dict | str | None = None,
        context: dict[str, Any] | None = None,
    ):
        return asyncio.run(self.check(identity, payload=payload, context=context))

    def runtimesnapshot(self) -> dict[str, Any]:
        """Return the live runtime state the CLI, TUI, and stream commands consume."""

        recent = self._stream.recent() if hasattr(self._stream, "recent") else []
        monitored_identities = sorted(
            identity
            for identity, win in self._id_store.items()
            if win.monitored_remaining > 0
        )
        return {
            "ai_mode": self._cfg_snap.ai_mode,
            "ai_enabled": self._cfg.ai.enabled,
            "ai_model": self._cfg.ai.model,
            "ai_timeout_secs": self._cfg.ai.timeout_secs,
            "observe_only": self._cfg_snap.observe_only,
            "backend": self._cfg.runtime.backend,
            "hard_sigs": [sig.name for sig in self._hard_sigs],
            "whitelist_size": len(self._wl._ids),
            "banned_ip_count": len(self._wl._banned_ips),
            "monitored_identity_count": len(monitored_identities),
            "whitelisted_identities": sorted(self._wl.identities()),
            "banned_ips": sorted(self._wl.banned_ips()),
            "monitored_identities": monitored_identities,
            "monitored_window": self._cfg.runtime.monitored_window,
            "monitored_multiplier": self._cfg.runtime.monitored_multiplier,
            "recent_events": len(recent),
            "state_db": str(self._state_DBpath),
            "audit_db": self._cfg.runtime.audit_db_path,
            "flag_threshold": self._cfg.thresholds.flag,
            "throttle_threshold": self._cfg.thresholds.throttle,
            "block_threshold": self._cfg.thresholds.block,
            "payload_weight": self._cfg.weights.payload,
            "behavior_weight": self._cfg.weights.behavior,
            "identity_weight": self._cfg.weights.identity,
            "context_weight": ContextSignal.weight,
            "ip_rep_weight": IPRepSignal.weight,
            "route_overrides": len(self._route_cfg),
            "route_overview": self.routeoverview(),
            "bg_started": self._bg_started,
        }

    async def handlestreamcmd(self, name: str, args: dict[str, Any]) -> dict[str, Any]:
        """Handle the runtime command surface shared by the CLI and TUI.

        These commands mutate live state, record control-plane history, and return
        small JSON-friendly payloads for remote callers.
        """

        if name == "get_runtime_snapshot":
            return self.runtimesnapshot()

        if name == "confirm_block":
            identity = str(args["identity"])
            ttl = int(args.get("ttl_secs", 900))
            self._id_store.set_blocked(identity, ttl)
            self.checkpoint()
            return {"ok": True, "identity": identity, "ttl_secs": ttl}

        if name == "unblock_whitelist":
            identity = str(args["identity"])
            self._id_store.clear_block(identity)
            self._id_store.clear_monitored(identity)
            self._wl.add(identity)
            self._audit.write_patch("unblock_whitelist", {"identity": identity})
            self.checkpoint()
            return {"ok": True, "identity": identity}

        if name == "unblock_note":
            note = str(args.get("note", "")).strip()
            identity = str(args.get("identity", ""))
            self._audit.write_patch("unblock_note", {"identity": identity, "note": note})
            return {"ok": True, "identity": identity}

        if name == "monitor_identity":
            identity = str(args["identity"])
            requests = int(args.get("requests", self._cfg.runtime.monitored_window))
            multiplier = float(args.get("multiplier", self._cfg.runtime.monitored_multiplier))
            win = self._id_store.set_monitored(
                identity,
                requests=requests,
                multiplier=multiplier,
            )
            self._audit.write_patch(
                "monitor_identity",
                {
                    "identity": identity,
                    "requests": requests,
                    "multiplier": multiplier,
                },
            )
            self.checkpoint()
            return {
                "ok": True,
                "identity": identity,
                "monitored": True,
                "requests": win.monitored_remaining,
                "multiplier": win.monitored_multiplier,
            }

        if name == "unmonitor_identity":
            identity = str(args["identity"])
            self._id_store.clear_monitored(identity)
            self._audit.write_patch("unmonitor_identity", {"identity": identity})
            self.checkpoint()
            return {
                "ok": True,
                "identity": identity,
                "monitored": False,
            }

        if name == "unblock_monitor":
            identity = str(args["identity"])
            requests = int(args.get("requests", self._cfg.runtime.monitored_window))
            multiplier = float(args.get("multiplier", self._cfg.runtime.monitored_multiplier))
            self._id_store.clear_block(identity)
            win = self._id_store.set_monitored(
                identity,
                requests=requests,
                multiplier=multiplier,
            )
            self._audit.write_patch(
                "unblock_monitor",
                {
                    "identity": identity,
                    "requests": requests,
                    "multiplier": multiplier,
                },
            )
            self.checkpoint()
            return {
                "ok": True,
                "identity": identity,
                "monitored": True,
                "requests": win.monitored_remaining,
                "multiplier": win.monitored_multiplier,
            }

        if name == "ban_ip":
            ip = str(args["ip"])
            self._wl.ban_ip(ip)
            self._audit.write_patch("ban_ip", {"ip": ip})
            self.checkpoint()
            return {
                "ok": True,
                "ip": ip,
                "banned": True,
                "banned_ip_count": len(self._wl._banned_ips),
            }

        if name == "unban_ip":
            ip = str(args["ip"])
            self._wl.unban_ip(ip)
            self._audit.write_patch("unban_ip", {"ip": ip})
            self.checkpoint()
            return {
                "ok": True,
                "ip": ip,
                "banned": False,
                "banned_ip_count": len(self._wl._banned_ips),
            }

        if name == "patch_config":
            changes = args.get("changes") or {}
            if "ai_mode" in changes:
                self._cfg.ai.mode = str(changes["ai_mode"])
                self._cfg.ai.enabled = self._cfg.ai.mode != "off"
            if "observe_only" in changes:
                self._cfg.runtime.observe_only = bool(changes["observe_only"])
            if "flag_threshold" in changes:
                self._cfg.thresholds.flag = float(changes["flag_threshold"])
            if "throttle_threshold" in changes:
                self._cfg.thresholds.throttle = float(changes["throttle_threshold"])
            if "block_threshold" in changes:
                self._cfg.thresholds.block = float(changes["block_threshold"])
            self._cfg_snap = build_snapshot(self._cfg)
            self._audit.write_patch("patch_config", changes)
            return self.runtimesnapshot()

        if name == "get_analysis_report":
            window = str(args.get("window", "7d"))
            limit = int(args.get("limit", 500))
            return await self.analysis_report(window=window, limit=limit)

        if name == "get_route_overview":
            return {
                "routes": self.routeoverview(),
            }

        if name == "ask_ai_analyst":
            question = str(args.get("question", "")).strip()
            window = str(args.get("window", "7d"))
            limit = int(args.get("limit", 500))
            return await self.ask_ai_analyst(question=question, window=window, limit=limit)

        raise ValueError(f"unknown stream command: {name}")

    def policy(self, name: str, **overrides: Any):
        """Apply a named route policy, then layer any explicit overrides on top."""

        pol = self.policies.get(name)
        if pol is None:
            raise ValueError(f"unknown policy: {name}")
        return self.protect(**pol.with_overrides(**overrides).__dict__)

    def protect(
        self,
        sensitivity: str = "internal",
        ai_mode: str = "off",
        trackB: bool = True,
        sink_mode: str = "off",
    ):
        """Attach inline route policy metadata to an endpoint function."""

        def deco(fn):
            cfg = {
                "sensitivity": sensitivity,
                "ai_mode": ai_mode,
                "trackB": trackB,
                "sink_mode": sink_mode,
            }

            wrap = _wrap_route_handler(fn)
            wrap._adiuvare_cfg = cfg
            return wrap

        return deco

    def exempt(self):
        """Mark a route as exempt from Adiuvare request inspection."""

        def deco(fn):
            wrap = _wrap_route_handler(fn)
            wrap._adiuvare_exempt = True
            return wrap

        return deco

    def configure_routes(self, routes: dict[str, Any]):
        """Register saved route configuration and seed the route overview cache."""

        self._route_cfg.update(routes)
        for path, saved in routes.items():
            if isinstance(saved, dict):
                self._remember_route(path, self._expand_routecfg(saved), saved=saved)
        return self

    def use(self, app: Any, framework: str = "fastapi") -> None:
        """Attach the guard to the selected web framework."""

        if framework == "fastapi":
            from .integrations.fastapi import AdiuvareMiddleware

            app.add_middleware(AdiuvareMiddleware, guard=self, route_source=app)
            return

        if framework == "flask":
            self._use_flask_store()
            from .integrations.flask import AdiuvareMiddleware

            app.wsgi_app = AdiuvareMiddleware(app.wsgi_app, guard=self, flask_app=app)
            return

        if framework == "django":
            from .integrations.django import AdiuvareMiddleware

            app._adiuvare_mw = AdiuvareMiddleware(app, guard=self)
            return

        raise ValueError(f"unsupported framework: {framework}")

    def _mkstream(self):
        if self._cfg.runtime.backend == "redis" and self._cfg.runtime.redis_url:
            return RedisEventStream(
                project="adiuvare",
                redis_url=self._cfg.runtime.redis_url,
            )
        return UnixSocketEventStream()

    def _mk_ai_sig(self) -> AISignal:
        return AISignal(
            base_url=self._cfg.ai.base_url,
            model=self._cfg.ai.model,
            timeout=self._cfg.ai.timeout_secs,
            api_key=self._cfg.ai.api_key,
        )

    async def analysis_report(self, *, window: str = "7d", limit: int = 500) -> dict[str, Any]:
        """Build the operator report, then let AI replace parts of it when available.

        The local report is always produced first so callers still get a useful
        payload when the model is off, slow, or returns partial data.
        """

        days = self._window_days(window)
        rows = self._audit.window(days=days, limit=limit)
        runtime = self.runtimesnapshot()
        runtime["instances"] = self._cfg.meta.instances
        report = build_report(rows, runtime, window=window)
        if not self._cfg.ai.enabled:
            return report

        try:
            ai_json = await self._pipeline._ai_sig.complete_json(report_prompt(report))
        except Exception:
            ai_json = {}

        summary = str(ai_json.get("summary", "")).strip()
        findings = [str(item) for item in ai_json.get("findings", []) if str(item).strip()]
        recommendations = [
            str(item) for item in ai_json.get("recommendations", []) if str(item).strip()
        ]
        if not summary:
            try:
                summary = (
                    await self._pipeline._ai_sig.complete_text(report_summary_prompt(report))
                ).strip()
            except Exception:
                summary = ""
        if summary:
            report["summary"] = summary
        if findings:
            report["findings"] = findings
        if recommendations:
            report["recommendations"] = recommendations
        if summary or findings or recommendations:
            report["source"] = "ai"
        return report

    async def ask_ai_analyst(
        self,
        *,
        question: str,
        window: str = "7d",
        limit: int = 500,
    ) -> dict[str, Any]:
        """Answer one operator question with AI when possible and a local fallback otherwise."""

        days = self._window_days(window)
        rows = self._audit.window(days=days, limit=limit)
        runtime = self.runtimesnapshot()
        runtime["instances"] = self._cfg.meta.instances
        report = build_report(rows, runtime, window=window)
        if not question:
            return {
                "source": "local",
                "question": "",
                "answer": report["summary"],
                "window": window,
            }

        if not self._cfg.ai.enabled:
            return {
                "source": "local",
                "question": question,
                "answer": local_analyst_answer(question, report, rows),
                "window": window,
            }

        try:
            answer = await self._pipeline._ai_sig.complete_text(
                analyst_prompt(question, report, rows)
            )
        except Exception:
            answer = local_analyst_answer(question, report, rows)
            source = "local"
        else:
            source = "ai" if answer.strip() else "local"
            if source == "local":
                answer = local_analyst_answer(question, report, rows)

        return {
            "source": source,
            "question": question,
            "answer": answer.strip(),
            "window": window,
        }

    def _use_flask_store(self) -> None:
        if isinstance(self._id_store, ThreadSafeIdentityStore):
            return

        store = ThreadSafeIdentityStore()
        for identity, win in self._id_store.items():
            store.update(identity, win)

        self._id_store = store
        self._pipeline._id_store = store
        for sig in self._pipeline._soft_signals:
            if hasattr(sig, "_id_store"):
                sig._id_store = store

    def routecfg(self, path: str, endpoint=None) -> dict[str, Any]:
        """Resolve the effective route config from saved config and decorator metadata."""

        cfg = {}
        saved = self._route_cfg.get(path)
        if isinstance(saved, dict):
            cfg.update(self._expand_routecfg(saved))

        if endpoint is not None:
            if getattr(endpoint, "_adiuvare_exempt", False):
                self._remember_route(path, {"exempt": True}, saved=saved)
                return {"exempt": True}
            live = getattr(endpoint, "_adiuvare_cfg", None)
            if isinstance(live, dict):
                cfg.update(live)

        self._remember_route(path, cfg, saved=saved)
        return cfg

    def routesnap(self, route_cfg: dict[str, Any] | None):
        """Return a request snapshot with any route-level AI mode override applied."""

        if not route_cfg:
            return self._cfg_snap

        ai_mode = route_cfg.get("ai_mode")
        if not ai_mode or ai_mode == self._cfg_snap.ai_mode:
            return self._cfg_snap
        return replace(self._cfg_snap, ai_mode=str(ai_mode))

    def _expand_routecfg(self, saved: dict[str, Any]) -> dict[str, Any]:
        if "policy" not in saved:
            return dict(saved)

        pol = self.policies.get(str(saved["policy"]))
        if pol is None:
            return dict(saved)

        overrides = {key: val for key, val in saved.items() if key != "policy"}
        return pol.with_overrides(**overrides).__dict__

    def _window_days(self, window: str) -> int:
        label = window.strip().lower()
        if label.endswith("d"):
            label = label[:-1]
        try:
            return max(1, int(label))
        except ValueError:
            return 7

    def routeoverview(self) -> list[dict[str, Any]]:
        """Return the stable route summary used by the TUI Signals screen."""

        for path, saved in self._route_cfg.items():
            if isinstance(saved, dict) and path not in self._route_overview:
                self._remember_route(path, self._expand_routecfg(saved), saved=saved)
        ordered = sorted(
            self._route_overview.values(),
            key=lambda item: (str(item.get("route", "")) != "*", str(item.get("route", ""))),
        )
        return [dict(item) for item in ordered]

    def _remember_route(
        self,
        path: str,
        cfg: dict[str, Any] | None,
        *,
        saved: dict[str, Any] | None = None,
    ) -> None:
        route = path or "*"
        cfg = dict(cfg or {})
        saved = dict(saved or {})
        exempt = bool(cfg.get("exempt") or saved.get("exempt"))
        status = "exempt" if exempt else "active"
        sensitivity = str(
            cfg.get("sensitivity")
            or saved.get("sensitivity")
            or self._cfg.meta.strictness
        )
        ai_mode = str(
            cfg.get("ai_mode")
            or saved.get("ai_mode")
            or self._cfg.ai.mode
        )
        policy = str(saved.get("policy") or cfg.get("policy") or "-")
        self._route_overview[route] = {
            "route": route,
            "status": status,
            "sensitivity": sensitivity,
            "policy": policy,
            "ai_mode": ai_mode,
        }
