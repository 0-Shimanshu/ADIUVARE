from ..core.models import SignalResult

_weights = {
    "payload": 0.40,
    "behavior": 0.30,
    "identity": 0.15,
    "context": 0.10,
    "ip_rep": 0.05,
}

_total_w = sum(_weights.values())
_weights = {k: v / _total_w for k, v in _weights.items()}


def compute_score(sig_res: dict[str, SignalResult], snap=None) -> tuple[float, dict[str, float]]:
    breakdown: dict[str, float] = {}
    total = 0.0
    active = 0

    weights = dict(_weights)
    if snap:
        snap_weights = {
            "payload": snap.payload_weight,
            "behavior": snap.behavior_weight,
            "identity": snap.identity_weight,
        }

        for k, v in snap_weights.items():
            if v < 0:
                raise ValueError(f"Weight for '{k}' must be non-negative, got {v}")

        total_snap = sum(snap_weights.values())
        if total_snap <= 0:
            raise ValueError("All weights sum to zero - cannot normalize.")

        weights.update(snap_weights)
        total_w = sum(weights.values())
        weights = {k: v / total_w for k, v in weights.items()}

    for name, res in sig_res.items():
        weight = weights.get(name, 0.0)
        part = res.score * weight
        breakdown[name] = part
        total += part
        if res.score > 0.0:
            active += 1

    if active > 1:
        total += 0.01

    return min(total, 1.0), breakdown
