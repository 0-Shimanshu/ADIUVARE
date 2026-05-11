import asyncio

from adiuvare.core.models import ConfigSnapshot
from adiuvare.core.policy_engine import reach_verdict
from adiuvare.core.models import RequestContext
from adiuvare.signals.payload import PayloadSignal


async def _score(text: str) -> float:
    ctx = RequestContext(
        identity="u1",
        payload=text,
        url="/form",
        method="POST",
        headers={},
        ip="127.0.0.1",
        endpoint="/form",
    )
    res = await PayloadSignal().extract(ctx)
    return res.score


def test_benign_matrix_stays_clean():
    cases = [
        "please select an option",
        "drop by later if you can",
        "the union hall opens at six",
        "javascript is disabled in this browser",
        "we benchmarked the service last week",
        "How does $(HOME) expansion work in Bash?",
        "render {{ user.name }} in the template",
        "Use $gt for greater-than filters in Mongo docs",
    ]

    for text in cases:
        score = asyncio.run(_score(text))
        assert score == 0.0, text


def test_mid_conf_payload_does_not_slip_below_flag_floor():
    score = asyncio.run(_score("../../etc/passwd"))
    snap = ConfigSnapshot(
        payload_weight=0.4,
        behavior_weight=0.35,
        identity_weight=0.25,
        flag_threshold=0.25,
        throttle_threshold=0.55,
        block_threshold=0.8,
    )
    out = reach_verdict(0.05, snap=snap, payload_risk=score)
    assert out.logged == "flag"
