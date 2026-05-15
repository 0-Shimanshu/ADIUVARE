import re

from ..core.models import RequestContext, SignalResult
from ..vendor import detect_sqli, detect_xss, normalize
from .base import SoftSignal
from .patterns import check_cmd, check_nosql, check_path, check_sql, check_ssti, check_xss

# ── Discussion-context detection ────────────────────────────────────────────
# We want to recognise harmless explanatory / tutorial / Q&A text that
# happens to contain SQL or HTML strings literally, so the payload signal
# can back off without weakening its real-attack coverage.

_DISCUSSION_STARTERS = re.compile(
    r"""(?i)^\s*(
        how\s+(do|can|would|should|does|to|about)\b |
        what\s+(is|does|are|about|'s)\b |
        can\s+(someone|anyone|you|i|we)\b |
        why\s+(is|does|are|do)\b |
        where\s+(is|are|can|do)\b |
        when\s+(is|are|can|do|should)\b |
        who\s+(is|are|can)\b |
        is\s+(it|there|this|that)\b |
        does\s+(anyone|someone|this|that|it)\b |
        please\b.*\? |
        help\b.*\b(?:with|me|understand)\b
    )""",
    re.VERBOSE,
)

_DISCUSSION_EDUCATORS = re.compile(
    r"""(?i)\b(
        tutori(?:al|als)\b |
        document(?:ation)?\b |
        docs?\b |
        (?:for|as\s+an)\s+example\b |
        literally\b |
        \bi\s+mean\b |
        explain(?:ing|ation)?\b |
        (?:in|my|the)\s+docs?\b |
        question\b |
        (?:does|what\s+does)\s+this\s+mean\b
    )""",
    re.VERBOSE,
)

# Natural-language sentence heuristics: real payloads are terse and
# mechanical; explanatory text looks like a sentence (multiple words,
# proper casing, ends with sentence punctuation).
_SENTENCE_LIKE = re.compile(r"^[A-Z].{20,}[.?!]$")

# Detect quoted/cited risky strings — e.g. `SELECT * FROM users` or
# "SELECT * FROM users" — which suggests citation, not execution.
_INLINE_QUOTED = re.compile(r"[`\"']\s*([^`\"']{3,80})\s*[`\"']")


def _count_attack_families(sql_lib, sql_pat, xss_lib, xss_pat,
                            path_pat, cmd_pat, ssti_pat, nosql_pat) -> int:
    """Return how many distinct attack families fired (library hit or pattern hit)."""
    families = 0
    if sql_lib.get("hit") or sql_pat[0]:
        families += 1
    if xss_lib.get("hit") or xss_pat[0]:
        families += 1
    if path_pat[0]:
        families += 1
    if cmd_pat[0]:
        families += 1
    if ssti_pat[0]:
        families += 1
    if nosql_pat[0]:
        families += 1
    return families


def _discussion_penalty(text: str, family_count: int) -> float:
    """Return a multiplier in (0.0, 1.0] to apply when the text looks like
    discussion / Q&A rather than an attack payload.

    Returns 1.0 when no discussion markers are present (no penalty).
    Returns a lower multiplier when strong discussion signals exist.
    Multiple attack families override the penalty (real attacks often
    combine techniques; discussion text rarely does).
    """
    if family_count >= 2:
        return 1.0  # multiple families → near-certain attack, don't penalise

    signals = 0
    weight = 0.0

    if _DISCUSSION_STARTERS.search(text):
        signals += 1
        weight += 0.35

    if _DISCUSSION_EDUCATORS.search(text):
        signals += 1
        weight += 0.30

    if _SENTENCE_LIKE.match(text):
        signals += 1
        weight += 0.20

    # Inline-quoted text is only a discussion signal when other
    # natural-language markers are already present — otherwise
    # quoted strings in real payloads (e.g. ' OR 'a'='a) would
    # incorrectly trigger the penalty.
    if signals > 0 and _INLINE_QUOTED.search(text):
        signals += 1
        weight += 0.15

    if signals == 0:
        return 1.0

    # Cap at 0.65 reduction — we never zero out the score entirely
    multiplier = 1.0 - min(weight, 0.65)
    return max(multiplier, 0.35)


# ── PayloadSignal ───────────────────────────────────────────────────────────

class PayloadSignal(SoftSignal):
    name = "payload"
    weight = 0.40

    async def extract(self, ctx: RequestContext) -> SignalResult:
        if not ctx.payload:
            return SignalResult(score=0.0, reason="no_payload")

        raw = ctx.payload
        text = normalize(raw)
        sql_lib = detect_sqli(text)
        xss_lib = detect_xss(text)
        sql_pat = check_sql(text)
        if raw != text:
            raw_sql = check_sql(raw)
            if raw_sql[0] and raw_sql[1] > sql_pat[1]:
                sql_pat = raw_sql
        xss_pat = check_xss(text)
        path_pat = check_path(text)
        cmd_pat = check_cmd(text)
        ssti_pat = check_ssti(text)
        nosql_pat = check_nosql(text)

        hits: list[tuple[float, str]] = []
        if sql_lib["hit"]:
            hits.append((max(sql_lib["conf"], 0.82), sql_lib["fp"] or "sql_lib"))
        if sql_pat[0]:
            hits.append((sql_pat[1], sql_pat[2]))
        if xss_lib["hit"]:
            hits.append((max(xss_lib["conf"] * 0.80, 0.62), "xss_lib"))
        if xss_pat[0]:
            hits.append((xss_pat[1], xss_pat[2]))
        if path_pat[0]:
            hits.append((path_pat[1], path_pat[2]))
        if cmd_pat[0]:
            hits.append((cmd_pat[1], cmd_pat[2]))
        if ssti_pat[0]:
            hits.append((ssti_pat[1], ssti_pat[2]))
        if nosql_pat[0]:
            hits.append((nosql_pat[1], nosql_pat[2]))

        if not hits:
            return SignalResult(score=0.0, reason="clean")

        top = max(hits, key=lambda item: item[0])
        score = top[0]
        if len(hits) > 1:
            avg = sum(item[0] for item in hits) / len(hits)
            score = min(1.0, (top[0] * 0.75) + (avg * 0.25))

        family_count = _count_attack_families(
            sql_lib, sql_pat, xss_lib, xss_pat,
            path_pat, cmd_pat, ssti_pat, nosql_pat,
        )
        penalty = _discussion_penalty(raw, family_count)
        if penalty < 1.0:
            score = round(score * penalty, 3)
            # If penalty dropped score to near-zero, report it clearly
            if score < 0.15:
                return SignalResult(
                    score=score,
                    reason="discussion_context",
                    detail={
                        "original_hit": top[1],
                        "penalty": penalty,
                    },
                )

        detail = {
            "sql_fp": sql_lib.get("fp", ""),
            "sql_pat": sql_pat[2],
            "xss_pat": xss_pat[2],
            "path_pat": path_pat[2],
            "cmd_pat": cmd_pat[2],
            "ssti_pat": ssti_pat[2],
            "nosql_pat": nosql_pat[2],
        }
        if penalty < 1.0:
            detail["discussion_penalty"] = penalty
        return SignalResult(score=score, reason=top[1], detail=detail)
