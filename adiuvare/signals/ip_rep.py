import ipaddress

from ..core.models import RequestContext, SignalResult
from .base import SoftSignal
from ..config.schema import AdiuvareConfig

_noisy_nets = (
    "185.220.",
    "45.155.",
    "198.51.100.",
    "203.0.113.",
)


class IPRepSignal(SoftSignal):
    name = "ip_rep"
    weight = 0.05

    def __init__(self, cfg: AdiuvareConfig | None = None) -> None:
        self._trusted_proxies: set[str] = (
            set(cfg.runtime.trusted_proxies) if cfg else set()
        )

    async def extract(self, ctx: RequestContext) -> SignalResult:
        try:
            ip = ipaddress.ip_address(ctx.ip)
        except ValueError:
            return SignalResult(score=0.12, reason="ip_parse_err")

        if ip.is_loopback or ip.is_private:
            return SignalResult(score=0.0, reason="ip_local")

        raw = str(ip)
        if ctx.headers.get("x-tor-exit") == "1":
            if ctx.ip in self._trusted_proxies:
                # The actual Tor exit node IP is in X-Forwarded-For, not ctx.ip.
                # ctx.ip here is the trusted proxy — we report the forwarded IP
                # so the detail reflects the real client, not the proxy itself.
                client_ip = ctx.headers.get("x-forwarded-for", raw).split(",")[0].strip()
                return SignalResult(score=0.35, reason="tor_hint", detail={"ip": client_ip})

        for prefix in _noisy_nets:
            if raw.startswith(prefix):
                return SignalResult(score=0.20, reason="noisy_net", detail={"ip": raw})

        return SignalResult(score=0.0, reason="ip_clean")
