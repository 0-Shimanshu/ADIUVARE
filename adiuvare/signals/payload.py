import re

from ..core.models import RequestContext, SignalResult
from ..vendor import detect_sqli, detect_xss, normalize
from .base import SoftSignal
from .patterns import check_cmd, check_nosql, check_path, check_sql, check_ssti, check_xss

def _is_discussion_style_sql(text: str) -> bool:
    low = " ".join(text.lower().split())

    discussion = any(
        p in low
        for p in (
            "how do i",
            "how to",
            "example of",
            "example query",
            "in a tutorial",
            "in docs",
            "documentation",
        )
    )

    dangerous = any(
        p in low
        for p in (
            "drop table",
            "union select",
            "sleep(",
            "benchmark(",
            "curl ",
            "wget ",
            "<script",
            "javascript:",
        )
    )

    return (
        discussion
        and "select * from users" in low
        and not dangerous
    )

_LDAP_PAT = re.compile(
    r"\*\)\s*\(\s*(?:uid|cn|mail)\s*=\s*\*?\s*\)\s*\)\s*\(\|\s*\(\s*(?:uid|cn|mail)\s*=",
    re.IGNORECASE,
)


def check_ldap(text: str) -> tuple[bool, float, str]:
    low = text.lower()
    if "))(|(" not in low:
        return (False, 0.0, "")
    if all(f"({attr}=" not in low for attr in ("uid", "cn", "mail")):
        return (False, 0.0, "")
    if _LDAP_PAT.search(text):
        return (True, 0.82, "ldap_injection")
    return (False, 0.0, "")


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
        ldap_pat = check_ldap(text)
        if raw != text:
            raw_ldap = check_ldap(raw)
            if raw_ldap[0] and raw_ldap[1] > ldap_pat[1]:
                ldap_pat = raw_ldap

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
        if ldap_pat[0]:
            hits.append((ldap_pat[1], ldap_pat[2]))

        if _is_discussion_style_sql(text):
            hits = [h for h in hits if h[1] != "select_from"]

        if not hits:
            return SignalResult(score=0.0, reason="clean")

        top = max(hits, key=lambda item: item[0])
        score = top[0]
        if len(hits) > 1:
            avg = sum(item[0] for item in hits) / len(hits)
            score = min(1.0, (top[0] * 0.75) + (avg * 0.25))

        detail = {
            "sql_fp": sql_lib.get("fp", ""),
            "sql_pat": sql_pat[2],
            "xss_pat": xss_pat[2],
            "path_pat": path_pat[2],
            "cmd_pat": cmd_pat[2],
            "ssti_pat": ssti_pat[2],
            "nosql_pat": nosql_pat[2],
            "ldap_pat": ldap_pat[2],
        }
        return SignalResult(score=score, reason=top[1], detail=detail)
