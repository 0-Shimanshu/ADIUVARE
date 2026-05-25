from adiuvare.core.models import ConfigSnapshot, SignalResult
from adiuvare.core.scorer import compute_score
from adiuvare.core.verdict import compute_verdict


def test_score_uses_hardcoded_weights():
    score, breakdown = compute_score(
        {
            "payload": SignalResult(score=0.7, reason="sql_hit"),
            "behavior": SignalResult(score=0.3, reason="odd_ua"),
        }
    )

    assert round(score, 3) == 0.395
    assert round(breakdown["payload"], 3) == 0.28


def test_verdict_maps_score_ranges():
    assert compute_verdict(0.10) == "allow"
    assert compute_verdict(0.30) == "flag"
    assert compute_verdict(0.60) == "throttle"
    assert compute_verdict(0.90) == "block"


def test_score_can_use_snapshot_weights():
    snap = ConfigSnapshot(
        payload_weight=0.50,
        behavior_weight=0.30,
        identity_weight=0.20,
        flag_threshold=0.25,
        throttle_threshold=0.55,
        block_threshold=0.80,
    )
    score, breakdown = compute_score(
        {
            "payload": SignalResult(score=0.7, reason="sql_hit"),
            "behavior": SignalResult(score=0.3, reason="odd_ua"),
        },
        snap,
    )

    assert round(score, 3) == 0.41
    assert round(breakdown["payload"], 3) == 0.318


def test_verdict_gets_identity_nudge_inline():
    snap = ConfigSnapshot(
        payload_weight=0.40,
        behavior_weight=0.35,
        identity_weight=0.25,
        flag_threshold=0.25,
        throttle_threshold=0.55,
        block_threshold=0.80,
    )
    assert compute_verdict(0.50, snap, identity_risk=0.70) == "throttle"
