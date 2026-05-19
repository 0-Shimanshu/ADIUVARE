from functools import lru_cache

from ..core.gate import trackA_cap
from ..core.models import RequestContext, SignalResult
from ..state.identity_store import IdentityStore
from .base import SoftSignal


@lru_cache(maxsize=1)
def _load_ua_parser():
    try:
        from ua_parser import user_agent_parser
    except Exception:
        return None
    return user_agent_parser


class BehaviorSignal(SoftSignal):
    name = "behavior"
    weight = 0.35

    def __init__(self, id_store: IdentityStore) -> None:
        self._id_store = id_store

    def score_trackA(self, identity: str) -> float:
        seen = self._id_store.get(identity).seen
        if seen > max(25, trackA_cap() // 8):
            return 0.55
        return 0.0

    def ua_score(self, ua: str | None) -> float:
        if not ua:
            return 0.35

        low = ua.lower()
        if "headlesschrome" in low or "phantomjs" in low:
            return 0.65

        parser = _load_ua_parser()
        if parser is not None:
            try:
                parsed = parser.ParseUserAgent(ua)
            except Exception:
                parsed = {}
            ua_name = str(parsed.get("family") or "").lower()
            if "headlesschrome" in ua_name or "phantomjs" in ua_name:
                return 0.65

        bad = {
            "python-requests",
            "curl",
            "wget",
            "httpie",
            "go-http-client",
        }
        if any(item in low for item in bad):
            return 0.45
        return 0.0

    async def extract(self, ctx: RequestContext) -> SignalResult:
        rscore = self.score_trackA(ctx.identity)
        uscore = self.ua_score(ctx.headers.get("User-Agent"))
        final = (rscore * 0.55) + (uscore * 0.45)

        if final == 0.0:
            return SignalResult(score=0.0, reason="behavior_clean")

        return SignalResult(score=final, reason="behavior_flag")
