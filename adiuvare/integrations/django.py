import asyncio

from .sqlalchemy import _sink_mode
from . import build_http_ctx, ctx_payload


class JsonResponse:
    def __init__(self, data: dict, status: int = 200) -> None:
        self.data = data
        self.status_code = status


class AdiuvareMiddleware:
    def __init__(self, get_response, guard) -> None:
        self._get_response = get_response
        self._guard = guard

    def __call__(self, request):
        raw = getattr(request, "body", b"")
        if callable(raw):
            raw = raw()
        if isinstance(raw, bytes):
            body = raw.decode(errors="replace")
        else:
            body = raw or None

        headers = dict(getattr(request, "headers", {}))
        meta = getattr(request, "META", {})
        path = getattr(request, "path", "/")
        method = getattr(request, "method", "GET")
        identity = headers.get("x-user-id", meta.get("REMOTE_USER", "anon"))
        ip = meta.get("REMOTE_ADDR", "127.0.0.1")
        route_cfg = self._guard.routecfg(path)
        if route_cfg.get("exempt"):
            return self._get_response(request)

        ctx = build_http_ctx(
            identity=identity,
            payload=ctx_payload(body, meta.get("QUERY_STRING", "")),
            url=path,
            method=method,
            headers=headers,
            ip=ip,
            endpoint=path,
            snapshot=self._guard.routesnap(route_cfg),
        )
        ctx.sensitivity = str(route_cfg.get("sensitivity", "internal"))
        gate, event = asyncio.run(
            self._guard.inspect(ctx, trackB=bool(route_cfg.get("trackB", True)))
        )
        if not gate.passed:
            return JsonResponse({"detail": gate.block_reason or "blocked"}, status=gate.status_code)

        if event is not None:
            if event.verdict == "block":
                return JsonResponse({"detail": "blocked"}, status=403)
            if event.verdict == "throttle":
                return JsonResponse({"detail": "throttled"}, status=429)

        request.adiuvare_event = event
        token = _sink_mode.set(str(route_cfg.get("sink_mode", "off")))
        try:
            return self._get_response(request)
        finally:
            _sink_mode.reset(token)
