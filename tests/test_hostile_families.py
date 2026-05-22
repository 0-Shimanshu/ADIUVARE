import pytest
from adiuvare import Guard


# ── SSTI ─────────────────────────────────────────────
@pytest.mark.parametrize("payload", [
    "{{7*7}}",
    "{{ 7 * 7 }}",           # spaced variant
    "%7B%7B7*7%7D%7D",       # URL encoded
    "{{config.__class__.__init__.__globals__}}",
    "${7*'7'}",
    "{% for x in range(10) %}{{x}}{% endfor %}",
])
def test_guard_flags_ssti_inputs(payload):
    guard = Guard()
    gate, event = guard.check_sync("u_ssti", payload=payload)
    assert event is not None
    assert event.score > 0.0


# ── NoSQL ─────────────────────────────────────────────
@pytest.mark.parametrize("payload", [
    '{"username": {"$ne": null}}',
    '{"age": {"$gt": 0}}',
    '{"$where": "this.password == this.passwordConfirm"}',
    '{"user": {"$ne": null}, "pass": {"$gt": ""}}',  # nested wrapper
    '%7B%22%24ne%22%3Anull%7D',   # URL encoded
])
def test_guard_flags_nosql_inputs(payload):
    guard = Guard()
    gate, event = guard.check_sync("u_nosql", payload=payload)
    assert event is not None
    assert event.score > 0.0


# ── LDAP ──────────────────────────────────────────────
@pytest.mark.parametrize("payload", [
    "*)(uid=*))(|(uid=*",
    "admin)(&(password=*))",
    ")(cn=*))(|(cn=*",
    "*)(objectClass=*)",
    "*\n)(uid=*",             # multiline variant
])
def test_guard_flags_ldap_inputs(payload):
    guard = Guard()
    gate, event = guard.check_sync("u_ldap", payload=payload)
    assert event is not None
    assert event.score > 0.0


# ── Benign ────────────────────────────────────────────
@pytest.mark.parametrize("payload", [
    "search for laptop under 50000",
    '{"username": "niveditha", "age": 21}',
    "render the user name in the template",
    "Use $gt for greater-than in MongoDB docs",
    "the union hall opens at six",
])
def test_guard_passes_benign_inputs(payload):
    guard = Guard()
    gate, event = guard.check_sync("u_benign", payload=payload)
    assert gate.passed is True
    assert event is not None
    assert event.breakdown["payload"] == 0.0