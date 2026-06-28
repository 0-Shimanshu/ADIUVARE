from contextvars import ContextVar

from ..signals.patterns import check_sql
from ..vendor import detect_sqli, normalize

_sink_mode: ContextVar[str] = ContextVar("adiuvare_sink_mode", default="async")


class AdiuvareBlockError(Exception):
    pass


def check_statement(
    guard,
    statement: str,
    *,
    sink_mode: str = "async",
    identity: str | None = None,
) -> None:
    cleaned = normalize(statement)
    res = detect_sqli(cleaned)
    if not res["hit"]:
        pat = check_sql(cleaned)
        if not pat[0]:
            return
        res = {"hit": True, "conf": pat[1], "fp": pat[2]}

    guard.record_sink_detection(
        statement=statement,
        normalised=cleaned,
        confidence=res["conf"],
        fingerprint=res.get("fp", ""),
    )

    if sink_mode == "inline":
        raise AdiuvareBlockError("blocked_at_sink")

    guard.elevate_identity_from_sink(identity)


def attach_sink(engine, guard) -> None:
    
    from sqlalchemy import event

    if getattr(engine, "_adiuvare_guard", None) is guard:
        return

    engine._adiuvare_guard = guard

    @event.listens_for(engine, "before_cursor_execute")
    def _watch(conn, cursor, statement, params, ctx, many):
        mode = _sink_mode.get()
        if mode == "off":
            return

        check_statement(guard, statement, sink_mode=mode)
