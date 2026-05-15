import asyncio
import json

from .sqlalchemy import _sink_mode
from . import build_http_ctx


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

        get_dict = getattr(request, "GET", {})
        request_params: dict = {}
        for key in get_dict:
            values = get_dict.getlist(key)
            multi = values if len(values) > 1 else values[0]
            request_params[key] = multi
        if body:
            try:
                body_json = json.loads(body)
                if isinstance(body_json, dict):
                    request_params.update(body_json)
                else:
                    request_params["_body"] = body
            except (json.JSONDecodeError, ValueError):
                request_params["_body"] = body
        payload = json.dumps(request_params) if request_params else None

        ctx = build_http_ctx(
            identity=identity,
            payload=payload,
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
