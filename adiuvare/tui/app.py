import asyncio
from datetime import datetime, timezone
from pathlib import Path

from rich.text import Text
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.widgets import Button, ContentSwitcher, Static

from ..config.editor import merge_sections
from ..config.loader import load_config
from ..config.watcher import ConfigWatcher
from ..runtime_analysis import build_report, local_analyst_answer
from ..state.audit_log import AuditLog
from ..state.event_stream import EventStreamClient
from .screens.ai import AIScreen
from .screens.audit import AuditScreen
from .screens.changes import ChangesScreen
from .screens.config import ConfigScreen
from .screens.events import EventsScreen
from .screens.monitor import MonitorScreen
from .screens.signals import SignalsScreen
from .workspace import PALETTE, WorkspaceView


class AdiuvareApp(App[None]):
    """Drive the multi-screen operator console against a live runtime or cached local audit data."""

    CSS_PATH = Path(__file__).with_name("replit.tcss")
    BINDINGS = [
        Binding("1", "switch_view('monitor')", show=False),
        Binding("2", "switch_view('events')", show=False),
        Binding("3", "switch_view('config')", show=False),
        Binding("4", "switch_view('signals')", show=False),
        Binding("5", "switch_view('ai')", show=False),
        Binding("6", "switch_view('audit')", show=False),
        Binding("7", "switch_view('changes')", show=False),
        Binding("q", "quit", show=False),
        Binding("r", "refresh_view", show=False),
    ]

    def __init__(self, socket_path: str | None = None, config_path: str | None = None) -> None:
        super().__init__()
        self.socket_path = socket_path
        self.connected = socket_path is not None
        self.config_path = config_path
        self.config = load_config(config_path)
        self.audit = AuditLog(self.config.runtime.audit_db_path)
        self.client = EventStreamClient(socket_path)
        self._view = "monitor"
        self._footer_note = ""
        self._watcher = ConfigWatcher(config_path) if config_path else None
        self._runtime_cache: dict | None = None
        self._route_cache: list[dict] = []
        self._stream_rows: list[dict] = []
        self._identity_ip_cache: dict[str, str] = {}
        self._tasks: list[asyncio.Task] = []
        self._refreshing_runtime = False

    def compose(self) -> ComposeResult:
        with Vertical(id="app-shell"):
            with Horizontal(id="header-bar"):
                yield Static("Adiuvare", id="brand")
                yield Static("", id="header-spacer")
                yield Static("", id="header-status")
                yield Static("", id="header-mode")
                yield Static("", id="header-backend")
                yield Static("", id="header-strictness")
                yield Static("", id="header-clock")

            with Horizontal(id="tab-strip-bar"):
                yield Button("1 Monitor", id="tab-monitor", classes="tab-btn")
                yield Button("2 Events", id="tab-events", classes="tab-btn")
                yield Button("3 Config", id="tab-config", classes="tab-btn")
                yield Button("4 Signals", id="tab-signals", classes="tab-btn")
                yield Button("5 AI", id="tab-ai", classes="tab-btn")
                yield Button("6 Audit", id="tab-audit", classes="tab-btn")
                yield Button("7 Changes", id="tab-changes", classes="tab-btn")
                yield Static("", id="tab-filler")

            yield Static("", id="connection-banner")

            with ContentSwitcher(initial="monitor-view", id="body-switcher"):
                yield MonitorScreen(id="monitor-view")
                yield EventsScreen(id="events-view")
                yield ConfigScreen(id="config-view")
                yield SignalsScreen(id="signals-view")
                yield AIScreen(id="ai-view")
                yield AuditScreen(id="audit-view")
                yield ChangesScreen(id="changes-view")

            with Horizontal(id="app-footer"):
                yield Static("Adiuvare WAF console", id="footer-left")
                yield Static("", id="footer-link-status")
                yield Static("Keyboard shortcuts active", id="footer-right")

    def on_mount(self) -> None:
        self._sync_view()
        self._update_header()
        if self.connected:
            self._tasks.append(asyncio.create_task(self._stream_loop()))
            self._tasks.append(asyncio.create_task(self._refresh_runtime()))
        self.set_interval(1.0, self._tick)
        self.set_interval(3.0, self._auto_refresh)

    async def on_unmount(self) -> None:
        for task in self._tasks:
            task.cancel()
        self._tasks.clear()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        button_id = event.button.id or ""
        if button_id.startswith("tab-"):
            self.action_switch_view(button_id.removeprefix("tab-"))

    def action_switch_view(self, view: str) -> None:
        self._view = view
        self._sync_view()

    def action_quit(self) -> None:
        self.exit()

    def action_refresh_view(self) -> None:
        page = self._active_page()
        page.refresh_view()
        self._sync_footer(page)

    def set_footer_status(self, text: str) -> None:
        self._footer_note = text
        self._sync_footer(self._active_page())

    def runtime_snapshot(self) -> dict:
        snap = {
            "framework": self.config.meta.framework,
            "instances": self.config.meta.instances,
            "strictness": self.config.meta.strictness,
            "ai_mode": self.config.ai.mode,
            "ai_enabled": self.config.ai.enabled,
            "ai_model": self.config.ai.model,
            "ai_timeout_secs": self.config.ai.timeout_secs,
            "observe_only": self.config.runtime.observe_only,
            "recent_events": len(self._stream_rows) if self._stream_rows else len(self.audit.recent(limit=20)),
            "whitelist_size": 0,
            "banned_ip_count": 0,
            "monitored_identity_count": 0,
            "whitelisted_identities": [],
            "banned_ips": [],
            "monitored_identities": [],
            "audit_db": self.config.runtime.audit_db_path,
            "state_db": self.config.runtime.state_db_path,
            "backend": self.config.runtime.backend,
            "connected": self.connected,
            "stream_path": self.socket_path,
            "flag_threshold": self.config.thresholds.flag,
            "throttle_threshold": self.config.thresholds.throttle,
            "block_threshold": self.config.thresholds.block,
            "payload_weight": self.config.weights.payload,
            "behavior_weight": self.config.weights.behavior,
            "identity_weight": self.config.weights.identity,
            "monitored_window": self.config.runtime.monitored_window,
            "monitored_multiplier": self.config.runtime.monitored_multiplier,
        }
        if self._runtime_cache:
            snap.update(self._runtime_cache)
        return snap

    def recent_rows(self, limit: int = 40) -> list[dict]:
        if self._stream_rows:
            return [self._normalise_row(row) for row in self._stream_rows[:limit]]
        return [self._normalise_row(row) for row in self.audit.recent(limit=limit)]

    def recent_by_identity(self, identity: str, limit: int = 40) -> list[dict]:
        return [self._normalise_row(row) for row in self.audit.by_identity(identity, limit=limit)]

    def recent_changes(self, limit: int = 40) -> list[dict]:
        return [self._normalise_change(row) for row in self.audit.history(limit=limit)]

    def route_overview(self) -> list[dict]:
        if self._route_cache:
            return [dict(row) for row in self._route_cache]

        seen: dict[str, dict] = {}
        for row in self.recent_rows(145):
            endpoint = str(row.get("endpoint", "")).strip()
            if not endpoint or endpoint in seen:
                continue
            seen[endpoint] = {
                "route": endpoint,
                "status": "active",
                "sensitivity": self.config.meta.strictness,
                "policy": "-",
                "ai_mode": self.config.ai.mode,
            }
        return [seen[key] for key in sorted(seen)]

    def save_config(self, changes: dict) -> None:
        path = Path(self.config_path) if self.config_path else Path("adiuvare.yaml")
        merge_sections(path, changes)
        self.config = load_config(path)
        self._watcher = ConfigWatcher(path)
        self.audit.write_patch("patch_config", changes)
        runtime_patch = self._runtime_patch(changes)
        if self.connected and runtime_patch:
            self.run_worker(
                self._send_command("patch_config", {"changes": runtime_patch}),
                exclusive=False,
            )
        self._update_header()

    def whitelist_identity(self, identity: str) -> None:
        if self.connected:
            self.run_worker(self._send_command("unblock_whitelist", {"identity": identity}), exclusive=False)
            return
        self.audit.write_patch("unblock_whitelist", {"identity": identity})

    def confirm_block(self, identity: str) -> None:
        if self.connected:
            self.run_worker(self._send_command("confirm_block", {"identity": identity}), exclusive=False)
            return
        self.audit.write_patch("confirm_block", {"identity": identity})

    def confirm_identity(self, identity: str) -> None:
        self.confirm_block(identity)

    def monitor_identity(self, identity: str) -> None:
        if self.connected:
            self.run_worker(self._send_command("monitor_identity", {"identity": identity}), exclusive=False)
            return
        self.audit.write_patch("monitor_identity", {"identity": identity})

    def unmonitor_identity(self, identity: str) -> None:
        if self.connected:
            self.run_worker(self._send_command("unmonitor_identity", {"identity": identity}), exclusive=False)
            return
        self.audit.write_patch("unmonitor_identity", {"identity": identity})

    def unblock_monitor(self, identity: str) -> None:
        if self.connected:
            self.run_worker(self._send_command("unblock_monitor", {"identity": identity}), exclusive=False)
            return
        self.audit.write_patch("unblock_monitor", {"identity": identity})

    def ban_ip(self, ip: str) -> None:
        if self.connected:
            self.run_worker(self._send_command("ban_ip", {"ip": ip}), exclusive=False)
            return
        self.audit.write_patch("ban_ip", {"ip": ip})

    def unban_ip(self, ip: str) -> None:
        if self.connected:
            self.run_worker(self._send_command("unban_ip", {"ip": ip}), exclusive=False)
            return
        self.audit.write_patch("unban_ip", {"ip": ip})

    async def get_analysis_report(self, window_days: int = 7) -> dict:
        """Return the analysis report, falling back to local audit summarization when needed."""

        window = f"{max(1, int(window_days))}d"
        if self.connected:
            try:
                report = await self.client.command("get_analysis_report", {"window": window})
            except Exception:
                report = self._local_analysis_report(window_days)
            else:
                report = self._normalise_report(report, window_days=window_days)
        else:
            report = self._local_analysis_report(window_days)
        return report

    async def ask_ai_analyst(self, question: str) -> dict:
        """Answer one operator question with runtime AI when available and local analysis otherwise."""

        if self.connected:
            try:
                result = await self.client.command("ask_ai_analyst", {"question": question, "window": "7d"})
            except Exception:
                result = self._local_ask_fallback(question)
        else:
            result = self._local_ask_fallback(question)
        return {
            "source": str(result.get("source", "local")),
            "question": str(result.get("question", question)),
            "answer": str(result.get("answer", "")),
            "window": str(result.get("window", "7d")),
        }

    def _local_analysis_report(self, window_days: int) -> dict:
        rows = [self._normalise_row(row) for row in self.audit.window(days=window_days, limit=500)]
        report = build_report(rows, self.runtime_snapshot(), window=f"{window_days}d")
        return self._normalise_report(report, window_days=window_days)

    def _local_ask_fallback(self, question: str) -> dict:
        rows = [self._normalise_row(row) for row in self.audit.window(days=7, limit=500)]
        report = build_report(rows, self.runtime_snapshot(), window="7d")
        return {
            "source": "local fallback",
            "question": question,
            "answer": local_analyst_answer(question, report, rows),
            "window": "7d",
        }

    def _update_header(self) -> None:
        snap = self.runtime_snapshot()
        live = bool(snap.get("connected", False))
        if live:
            self.query_one("#header-status", Static).update(
                Text.from_markup(f"[{PALETTE['green']}]connected[/]")
            )
        else:
            self.query_one("#header-status", Static).update(
                Text.from_markup(f"[{PALETTE['orange']}]disconnected[/]")
            )

        banner = self.query_one("#connection-banner", Static)
        if live:
            banner.update("")
            banner.display = False
        else:
            banner.update(
                Text.from_markup(
                    f" [{PALETTE['orange']}]DISCONNECTED[/] "
                    f"[{PALETTE['dim']}]Cached audit data only — connect to a live runtime for bans, blocks, and monitors[/]"
                )
            )
            banner.display = True

        mode = "observe" if snap.get("observe_only", False) else "enforce"
        mode_color = PALETTE["green"] if mode == "observe" else PALETTE["red"]
        self.query_one("#header-mode", Static).update(
            Text.from_markup(f"[{mode_color}]. {mode}[/]")
        )
        self.query_one("#header-backend", Static).update(
            Text.from_markup(f"[{PALETTE['dim']}]. {snap.get('backend', 'sqlite')}[/]")
        )
        self.query_one("#header-strictness", Static).update(
            Text.from_markup(f"[{PALETTE['dim']}]. {snap.get('strictness', 'internal')}[/]")
        )
        self.query_one("#header-clock", Static).update(
            Text(datetime.now().strftime("%I:%M:%S %p"), style=PALETTE["dim"])
        )
        link_text = "live link active" if live else "disconnected — cached data only"
        self.query_one("#footer-link-status", Static).update(
            Text(link_text, style=PALETTE["green"] if live else PALETTE["orange"])
        )

    def _sync_view(self) -> None:
        self.query_one("#body-switcher", ContentSwitcher).current = f"{self._view}-view"
        for name in ("monitor", "events", "config", "signals", "ai", "audit", "changes"):
            button = self.query_one(f"#tab-{name}", Button)
            button.remove_class("-active")
            if name == self._view:
                button.add_class("-active")
        page = self._active_page()
        page.focus_primary()
        self._sync_footer(page)

    def _sync_footer(self, page: WorkspaceView) -> None:
        self.query_one("#footer-left", Static).update(Text(page.shortcut_summary(), style=PALETTE["dim"]))
        right = page.footer_status()
        if not self.connected:
            right = f"offline mode  .  {right}"
        if self._footer_note:
            right = f"{right}  .  {self._footer_note}"
        right_color = PALETTE["very_dim"]
        if "Selected:" in right or "selected:" in right:
            right_color = PALETTE["dim"]
        elif "save" in right.lower() or "navigate" in right.lower():
            right_color = PALETTE["orange"]
        self.query_one("#footer-right", Static).update(Text(right, style=right_color))

    def _active_page(self) -> WorkspaceView:
        return self.query_one(f"#{self._view}-view", WorkspaceView)

    def _tick(self) -> None:
        self._update_header()
        if self._watcher and self._watcher.check():
            self.config = load_config(self._watcher.path)
            self._active_page().refresh_view()
            self.set_footer_status("config changed on disk")

    def _auto_refresh(self) -> None:
        page = self._active_page()
        page.refresh_view()
        self._sync_footer(page)
        if self.connected:
            self.run_worker(self._refresh_runtime(), exclusive=False)

    async def _send_command(self, name: str, args: dict) -> None:
        try:
            res = await self.client.command(name, args)
        except Exception:
            self.set_footer_status("runtime command failed")
            return

        if name == "get_runtime_snapshot":
            self._runtime_cache = res
        else:
            self.set_footer_status("runtime command sent")
            await self._refresh_runtime()
        self._update_header()
        self._active_page().refresh_view()

    async def _refresh_runtime(self) -> None:
        if not self.connected or self._refreshing_runtime:
            return
        self._refreshing_runtime = True
        try:
            try:
                self._runtime_cache = await self.client.command("get_runtime_snapshot", {})
            except Exception:
                return
            try:
                route_info = await self.client.command("get_route_overview", {})
            except Exception:
                route_info = {}
            self._route_cache = [dict(row) for row in route_info.get("routes", []) if isinstance(row, dict)]
            self._update_header()
            self._active_page().refresh_view()
        finally:
            self._refreshing_runtime = False

    async def _stream_loop(self) -> None:
        if not self.connected:
            return
        try:
            async for row in self.client.subscribe():
                if not isinstance(row, dict):
                    continue
                self._stream_rows.insert(0, self._normalise_row(row))
                del self._stream_rows[145:]
                self._active_page().refresh_view()
        except Exception:
            self.set_footer_status("stream link dropped")

    def _runtime_patch(self, changes: dict) -> dict:
        patch = {}
        thresholds = changes.get("thresholds") or {}
        runtime = changes.get("runtime") or {}
        ai = changes.get("ai") or {}
        if "flag" in thresholds:
            patch["flag_threshold"] = thresholds["flag"]
        if "throttle" in thresholds:
            patch["throttle_threshold"] = thresholds["throttle"]
        if "block" in thresholds:
            patch["block_threshold"] = thresholds["block"]
        if "observe_only" in runtime:
            patch["observe_only"] = runtime["observe_only"]
        if "mode" in ai:
            patch["ai_mode"] = ai["mode"]
        return patch

    def _normalise_row(self, row: dict) -> dict:
        out = dict(row)
        breakdown = out.get("breakdown") or {}
        if not isinstance(breakdown, dict):
            breakdown = {}
        detail = out.get("detail") or {}
        if not isinstance(detail, dict):
            detail = {}
        identity = str(out.get("identity", "") or "")
        ip = str(out.get("ip") or detail.get("ip") or "")
        if not ip and identity.startswith("ip:"):
            ip = identity.split(":", 1)[1]
        if not ip and identity:
            ip = self._lookup_identity_ip(identity)
        if identity and ip:
            self._identity_ip_cache[identity] = ip
        out["breakdown"] = breakdown
        out["detail"] = detail
        out["ip"] = ip or "-"
        out["dominant"] = self._dominant_signal(breakdown)
        out["age"] = self._age_text(out.get("created_at"))
        out["mode"] = str(out.get("mode") or ("observe" if detail.get("logged_verdict") else "enforce"))
        return out

    def _lookup_identity_ip(self, identity: str) -> str:
        cached = self._identity_ip_cache.get(identity, "")
        if cached:
            return cached

        for row in self._stream_rows:
            if str(row.get("identity", "")) != identity:
                continue
            ip = str(row.get("ip", "") or "")
            if ip and ip != "-":
                self._identity_ip_cache[identity] = ip
                return ip

        for row in self.audit.by_identity(identity, limit=12):
            detail = row.get("detail") or {}
            if not isinstance(detail, dict):
                detail = {}
            ip = str(row.get("ip", "") or detail.get("ip", "") or "")
            if ip and ip != "-":
                self._identity_ip_cache[identity] = ip
                return ip

        return ""

    def _normalise_report(self, report: dict, *, window_days: int) -> dict:
        stats = report.get("stats") or {}
        signal_list = report.get("signal_pressure") or []
        if isinstance(signal_list, list):
            signal_pressure = {
                str(item.get("signal", "")): float(item.get("score", 0.0))
                for item in signal_list
                if isinstance(item, dict)
            }
        else:
            signal_pressure = {
                str(key): float(val)
                for key, val in dict(signal_list).items()
            }
        verdicts = {
            "allow": int(stats.get("allow", report.get("allow", 0))),
            "flag": int(stats.get("flag", report.get("flagged", report.get("flag", 0)))),
            "throttle": int(stats.get("throttle", report.get("throttle", 0))),
            "block": int(stats.get("block", report.get("blocked", report.get("block", 0)))),
        }
        source = str(report.get("source", "local"))
        if source == "local":
            source = "local analysis"
        elif source == "ai":
            source = "ai analysis"
        return {
            "source": source,
            "window_days": window_days,
            "total": int(stats.get("events", report.get("total", 0))),
            "blocked": int(stats.get("blocked", stats.get("block", report.get("blocked", 0)))),
            "flagged": int(stats.get("flagged", stats.get("flag", report.get("flagged", 0)))),
            "block_rate": float(stats.get("block_rate", report.get("block_rate", 0.0))),
            "verdicts": verdicts,
            "signal_pressure": {name: round(score, 1) for name, score in signal_pressure.items()},
            "summary": str(report.get("summary", "")),
            "recommendations": [str(item) for item in report.get("recommendations", [])],
            "findings": [str(item) for item in report.get("findings", [])],
        }

    def _normalise_change(self, row: dict) -> dict:
        patch = row.get("patch", {})
        kind = str(row.get("kind", "patch"))
        created_at = row.get("created_at")
        return {
            "kind": kind,
            "patch": patch,
            "created_at": created_at,
            "age": self._age_text(created_at),
            "target": self._change_target(kind, patch),
            "summary": self._change_summary(kind, patch),
        }

    def _change_target(self, kind: str, patch) -> str:
        if isinstance(patch, dict):
            if patch.get("identity"):
                return str(patch["identity"])
            if patch.get("ip"):
                return str(patch["ip"])
            if kind == "patch_config":
                return "config"
            if patch.get("statement"):
                return "sink"
        return "-"

    def _change_summary(self, kind: str, patch) -> str:
        if not isinstance(patch, dict):
            return str(patch)

        if kind == "patch_config":
            groups: list[str] = []
            thresholds = patch.get("thresholds")
            if isinstance(thresholds, dict) and thresholds:
                vals = ", ".join(f"{key}={val}" for key, val in thresholds.items())
                groups.append(f"thresholds {vals}")
            weights = patch.get("weights")
            if isinstance(weights, dict) and weights:
                vals = ", ".join(f"{key}={val}" for key, val in weights.items())
                groups.append(f"weights {vals}")
            runtime = patch.get("runtime")
            if isinstance(runtime, dict) and runtime:
                vals = []
                if "observe_only" in runtime:
                    vals.append(f"observe={'on' if runtime['observe_only'] else 'off'}")
                if "backend" in runtime:
                    vals.append(f"backend={runtime['backend']}")
                if "redis_url" in runtime and runtime["redis_url"]:
                    vals.append("redis_url updated")
                if "monitored_window" in runtime:
                    vals.append(f"window={runtime['monitored_window']}")
                if "monitored_multiplier" in runtime:
                    vals.append(f"multiplier={runtime['monitored_multiplier']}")
                if vals:
                    groups.append("runtime " + ", ".join(vals))
            ai = patch.get("ai")
            if isinstance(ai, dict) and ai:
                vals = []
                if "enabled" in ai:
                    vals.append(f"enabled={ai['enabled']}")
                if "mode" in ai:
                    vals.append(f"mode={ai['mode']}")
                if "model" in ai:
                    vals.append(f"model={ai['model']}")
                if "base_url" in ai:
                    vals.append("base_url updated")
                if "timeout_secs" in ai:
                    vals.append(f"timeout={ai['timeout_secs']}")
                if vals:
                    groups.append("ai " + ", ".join(vals))
            meta = patch.get("meta")
            if isinstance(meta, dict) and meta:
                vals = ", ".join(f"{key}={val}" for key, val in meta.items())
                groups.append(f"profile {vals}")
            flat = {
                key: val
                for key, val in patch.items()
                if key not in {"thresholds", "weights", "runtime", "ai", "meta"}
            }
            if flat:
                groups.append(", ".join(f"{key}={val}" for key, val in flat.items()))
            return " . ".join(groups) if groups else "config updated"

        if kind == "confirm_block":
            ttl = patch.get("ttl_secs")
            return f"block confirmed for {patch.get('identity', '?')}" + (f" ({ttl}s)" if ttl else "")
        if kind == "unblock_whitelist":
            return f"unblocked and whitelisted {patch.get('identity', '?')}"
        if kind == "monitor_identity":
            bits = [f"monitored {patch.get('identity', '?')}"]
            if "requests" in patch:
                bits.append(f"for {patch['requests']} requests")
            if "multiplier" in patch:
                bits.append(f"x{patch['multiplier']}")
            return " ".join(bits)
        if kind == "unmonitor_identity":
            return f"removed monitored state for {patch.get('identity', '?')}"
        if kind == "unblock_monitor":
            bits = [f"unblocked and monitored {patch.get('identity', '?')}"]
            if "requests" in patch:
                bits.append(f"for {patch['requests']} requests")
            if "multiplier" in patch:
                bits.append(f"x{patch['multiplier']}")
            return " ".join(bits)
        if kind == "ban_ip":
            return f"banned IP {patch.get('ip', '?')}"
        if kind == "unban_ip":
            return f"unbanned IP {patch.get('ip', '?')}"
        if kind == "sink_hit":
            statement = str(patch.get("statement", "")).strip()
            if statement:
                return f"sink hit from {statement[:56]}"
            return "sink hit recorded"

        return ", ".join(f"{key}={val}" for key, val in patch.items()) or kind.replace("_", " ")

    def _dominant_signal(self, breakdown: dict) -> str:
        if not breakdown:
            return "-"
        try:
            return str(max(breakdown, key=lambda name: float(breakdown[name])))
        except Exception:
            return "-"

    def _age_text(self, created_at) -> str:
        if not created_at:
            return "-"
        text = str(created_at)
        try:
            created = datetime.fromisoformat(text.replace("Z", "+00:00"))
        except ValueError:
            try:
                created = datetime.strptime(text, "%Y-%m-%d %H:%M:%S")
            except ValueError:
                return "-"
        if created.tzinfo is None:
            created = created.replace(tzinfo=timezone.utc)
        delta = datetime.now(timezone.utc) - created
        minutes = max(0, int(delta.total_seconds() // 60))
        if minutes < 60:
            return f"{minutes}m"
        hours = minutes // 60
        if hours < 24:
            return f"{hours}h"
        days = hours // 24
        return f"{days}d"
