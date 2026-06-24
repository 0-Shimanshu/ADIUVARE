from dataclasses import dataclass

from limits import parse

from ..core.models import RequestContext
from ..state.identity_store import IdentityStore

trackA_limit = "200/minute"
_trackA_obj = parse(trackA_limit)
_wl = None
_hard_sigs = []


@dataclass
class GateResult:
    passed: bool
    hold: bool = False
    status_code: int = 200
    block_reason: str | None = None


def configure_trackA(*, wl=None, hard_sigs=None) -> None:
    global _wl, _hard_sigs
    _wl = wl
    _hard_sigs = list(hard_sigs or [])


def trackA_cap() -> int:
    return int(getattr(_trackA_obj, "amount", 200))


def run_trackA(ctx: RequestContext, id_store: IdentityStore) -> GateResult:
    if _wl and _wl.allows(ctx.identity):
        return GateResult(passed=True)

    if _wl and _wl.ip_blocked(ctx.ip):
        return GateResult(
            passed=False,
            status_code=403,
            block_reason="banned_ip",
        )

    if ctx.endpoint.startswith("/.git") or ctx.endpoint.startswith("/_decoy"):
        return GateResult(
            passed=False,
            status_code=403,
            block_reason="decoy_path",
        )

    for sig in _hard_sigs:
        if sig.check(ctx):
            if getattr(sig, "action", "block") == "hold":
                return GateResult(
                    passed=False,
                    hold=True,
                    status_code=202,
                    block_reason=sig.name,
                )
            return GateResult(
                passed=False,
                status_code=403,
                block_reason=sig.name,
            )

    if ctx.endpoint.startswith("/admin") and ctx.method == "POST":
        return GateResult(
            passed=False,
            hold=True,
            status_code=202,
            block_reason="trackA_hold",
        )

    _seen, _blocked = id_store.bump_and_maybe_block(ctx.identity, trackA_cap())
    if _blocked:
        reason = "identity_blocked" if _seen <= trackA_cap() else "rate_limit_hit"
        return GateResult(
            passed=False,
            status_code=429,
            block_reason=reason,
        )

    return GateResult(passed=True)