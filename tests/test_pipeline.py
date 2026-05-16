import asyncio

from adiuvare.core.models import RequestContext
from adiuvare.core.pipeline import Pipeline
from adiuvare.state.identity_store import IdentityStore


def test_pipeline_runs_end_to_end():
    ctx = RequestContext(
        identity="u1",
        payload="select * from users",
        url="/login",
        method="POST",
        headers={"User-Agent": "Mozilla/5.0"},
        ip="127.0.0.1",
        endpoint="/login",
    )

    gate, out = asyncio.run(Pipeline(IdentityStore()).process(ctx))
    assert gate.passed is True
    assert out is not None
    assert out.verdict == "flag"


def test_pipeline_stops_when_gate_fails():
    store = IdentityStore()
    store.block("u1")

    ctx = RequestContext(
        identity="u1",
        payload="select * from users",
        url="/login",
        method="POST",
        headers={"User-Agent": "Mozilla/5.0"},
        ip="127.0.0.1",
        endpoint="/login",
    )

    gate, out = asyncio.run(Pipeline(store).process(ctx))
    assert gate.passed is False
    assert out is None


def test_pipeline_picks_up_suspicious_user_agent():
    ctx = RequestContext(
        identity="u1",
        payload=None,
        url="/",
        method="GET",
        headers={"User-Agent": "curl/8.0"},
        ip="127.0.0.1",
        endpoint="/",
    )

    gate, out = asyncio.run(Pipeline(IdentityStore()).process(ctx))
    assert gate.passed is True
    assert out is not None
    assert out.score > 0.0


def test_pipeline_marks_missing_user_agent_as_suspicious():
    ctx = RequestContext(
        identity="u1",
        payload=None,
        url="/",
        method="GET",
        headers={},
        ip="127.0.0.1",
        endpoint="/",
    )

    gate, out = asyncio.run(Pipeline(IdentityStore()).process(ctx))
    assert gate.passed is True
    assert out is not None
    assert out.score > 0.0


def test_pipeline_writes_score_back_to_identity_store():
    store = IdentityStore()
    ctx = RequestContext(
        identity="u1",
        payload="select * from users",
        url="/login",
        method="POST",
        headers={"User-Agent": "Mozilla/5.0"},
        ip="127.0.0.1",
        endpoint="/login",
    )

    gate, out = asyncio.run(Pipeline(store).process(ctx))
    assert gate.passed is True
    assert out is not None
    assert store.get("u1").score_ewma == out.score


def test_pipeline_repeats_pick_up_identity_state():
    store = IdentityStore()
    ctx = RequestContext(
        identity="u1",
        payload="select * from users",
        url="/login",
        method="POST",
        headers={"User-Agent": "Mozilla/5.0"},
        ip="127.0.0.1",
        endpoint="/login",
    )

    _, first = asyncio.run(Pipeline(store).process(ctx))
    _, second = asyncio.run(Pipeline(store).process(ctx))
    assert first is not None
    assert second is not None
    assert second.score > first.score
    assert store.get("u1").score_ewma < second.score


def test_pipeline_clean_payload_produces_allow_verdict():
    ctx = RequestContext(
        identity="u1",
        payload="hello world",
        url="/greet",
        method="POST",
        headers={"User-Agent": "Mozilla/5.0"},
        ip="127.0.0.1",
        endpoint="/greet",
    )

    gate, out = asyncio.run(Pipeline(IdentityStore()).process(ctx))
    assert gate.passed is True
    assert out is not None
    assert out.verdict == "allow"


def test_pipeline_high_confidence_sqli_produces_non_allow_verdict():
    ctx = RequestContext(
        identity="u1",
        payload="DROP TABLE users",
        url="/billing",
        method="POST",
        headers={"User-Agent": "Mozilla/5.0"},
        ip="127.0.0.1",
        endpoint="/billing",
    )

    gate, out = asyncio.run(Pipeline(IdentityStore()).process(ctx))
    assert gate.passed is True
    assert out is not None
    assert out.verdict in {"throttle", "block"}


def test_pipeline_monitored_identity_gets_multiplier_and_consumes_window():
    monitored_store = IdentityStore()
    plain_store = IdentityStore()
    monitored_win = monitored_store.get("u1")
    monitored_win.score_ewma = 0.4
    monitored_store.update("u1", monitored_win)
    plain_win = plain_store.get("u1")
    plain_win.score_ewma = 0.4
    plain_store.update("u1", plain_win)
    monitored_store.set_monitored("u1", requests=2, multiplier=1.5)
    ctx = RequestContext(
        identity="u1",
        payload="select * from users",
        url="/login",
        method="POST",
        headers={"User-Agent": "Mozilla/5.0"},
        ip="127.0.0.1",
        endpoint="/login",
    )

    _, monitored_first = asyncio.run(Pipeline(monitored_store).process(ctx))
    _, plain_first = asyncio.run(Pipeline(plain_store).process(ctx))
    _, monitored_second = asyncio.run(Pipeline(monitored_store).process(ctx))

    assert monitored_first is not None
    assert plain_first is not None
    assert monitored_second is not None
    assert monitored_first.score > plain_first.score
    assert monitored_store.get("u1").monitored_remaining == 0
    assert monitored_store.get("u1").monitored_multiplier == 1.0
