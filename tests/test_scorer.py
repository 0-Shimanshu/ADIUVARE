import pytest
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

    assert score == pytest.approx(0.38, rel=1e-3)
    assert breakdown["payload"] == pytest.approx(0.28, rel=1e-3)


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

    assert score == pytest.approx(0.393, rel=1e-3)


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

def test_identity_heavy_detection():
    score, breakdown = compute_score(
        {
            "identity": SignalResult(score=1.0, reason="known_bad_actor"),
            "ip_rep": SignalResult(score=0.8, reason="blacklisted_ip"),
        }
    )
    assert score > 0.15
    assert breakdown["identity"] > 0.10

def test_negative_weight_raises():
    snap = ConfigSnapshot(
        payload_weight=-0.5, behavior_weight=0.5, identity_weight=0.0,
        flag_threshold=0.25, throttle_threshold=0.55, block_threshold=0.80,
    )
    with pytest.raises(ValueError, match="non-negative"):
        compute_score({"payload": SignalResult(score=0.7, reason="sql_hit")}, snap)

def test_all_zero_weights_raises():
    snap = ConfigSnapshot(
        payload_weight=0.0, behavior_weight=0.0, identity_weight=0.0,
        flag_threshold=0.25, throttle_threshold=0.55, block_threshold=0.80,
    )
    with pytest.raises(ValueError, match="sum to zero"):
        compute_score({"payload": SignalResult(score=0.7, reason="sql_hit")}, snap)