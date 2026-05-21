import adiuvare.signals.behavior as behavior
import asyncio

from adiuvare.signals.behavior import BehaviorSignal
from adiuvare.state.identity_store import IdentityStore

from adiuvare.core.gate import configure_trackA, run_trackA
from adiuvare.core.models import RequestContext
from adiuvare.state.whitelist import WhitelistStore

def _make_ctx(identity: str = "u1") -> RequestContext:
    return RequestContext(
        identity=identity, payload=None, url="/", method="GET",
        headers={"User-Agent": "Mozilla/5.0"}, ip="1.2.3.4", endpoint="/",
    )

def test_behavior_falls_back_without_ua_parser(monkeypatch):
    monkeypatch.setattr(behavior, "_load_ua_parser", lambda: None)
    sig = BehaviorSignal(IdentityStore())

    assert sig.ua_score("curl/8.0") == 0.45


def test_behavior_flags_headless_without_ua_parser(monkeypatch):
    monkeypatch.setattr(behavior, "_load_ua_parser", lambda: None)
    sig = BehaviorSignal(IdentityStore())

    assert sig.ua_score("Mozilla/5.0 HeadlessChrome/124.0") == 0.65


def test_behavior_falls_back_when_parser_breaks(monkeypatch):
    class BrokenParser:
        @staticmethod
        def ParseUserAgent(_ua: str):
            raise RuntimeError("parser broke")

    monkeypatch.setattr(behavior, "_load_ua_parser", lambda: BrokenParser)
    sig = BehaviorSignal(IdentityStore())

    assert sig.ua_score("curl/8.0") == 0.45

def test_seen_increments_once_per_request():
    """gate.py and BehaviorSignal must not both call bump() — seen should equal N after N requests."""
    store = IdentityStore()
    sig = BehaviorSignal(store)
    wl = WhitelistStore()
    configure_trackA(wl=wl, hard_sigs=[])

    N = 10
    for _ in range(N):
        ctx = _make_ctx()
        run_trackA(ctx, store)
        asyncio.run(sig.extract(ctx))

    assert store.get("u1").seen == N, (
        f"Expected seen=={N} but got {store.get('u1').seen}. "
        "BehaviorSignal.score_trackA() must read seen without calling bump()."
    )
    configure_trackA(wl=None, hard_sigs=[])