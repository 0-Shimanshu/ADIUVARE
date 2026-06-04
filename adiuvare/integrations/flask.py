import asyncio
import json

from werkzeug.wrappers import Request, Response

from .sqlalchemy import _sink_mode
from . import build_http_ctx, ctx_payload


class AdiuvareMiddleware:
    def __init__(self, app, guard, flask_app=None) -> None:
        self._app = app
        self._guard = guard
        self._flask = flask_app

    def __call__(self, environ, start_response):
        req = Request(environ)
        raw_ip = req.headers.get("x-forwarded-for", "")
        ip = raw_ip.split(",", 1)[0].strip() or req.remote_addr or "127.0.0.1"
        route_cfg = self._route_cfg(req)
        if route_cfg.get("exempt"):
            return self._app(environ, start_response)

        body_text = req.get_data(as_text=True)
        query_text = req.query_string.decode("utf-8") if req.query_string else ""
        payload = ctx_payload(body_text, query_text)

        ctx = build_http_ctx(
            identity=req.headers.get("x-user-id", req.remote_addr or "anon"),
            payload=payload,
            url=req.path,
            method=req.method,
            headers=dict(req.headers),
            ip=ip,
            endpoint=req.path,
            snapshot=self._guard.routesnap(route_cfg),
        )
        ctx.sensitivity = str(route_cfg.get("sensitivity", "internal"))

        gate, event = asyncio.run(
            self._guard.inspect(ctx, trackB=bool(route_cfg.get("trackB", True)))
        )
        if not gate.passed:
            res = Response(
                json.dumps({"detail": gate.block_reason or "blocked"}),
                status=gate.status_code,
                content_type="application/json",
            )
            return res(environ, start_response)

        if event is not None:
            if event.verdict == "block":
                res = Response(
                    json.dumps({"detail": "blocked"}),
                    status=403,
                    content_type="application/json",
                )
                return res(environ, start_response)
            if event.verdict == "throttle":
                res = Response(
                    json.dumps({"detail": "throttled"}),
                    status=429,
                    content_type="application/json",
                )
                return res(environ, start_response)

        environ["adiuvare.event"] = event
        token = _sink_mode.set(str(route_cfg.get("sink_mode", "off")))
        try:
            return self._app(environ, start_response)
        finally:
            _sink_mode.reset(token)

    def _route_cfg(self, req: Request) -> dict:
        view = None
        if self._flask is not None:
            try:
                endpoint, _ = self._flask.url_map.bind_to_environ(req.environ).match()
                view = self._flask.view_functions.get(endpoint)
            except Exception:
                view = None
        return self._guard.routecfg(req.path, view)