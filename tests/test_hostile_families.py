"""
Regression tests for broader hostile input families through the real guard path.
Covers: SSTI, NoSQL injection, and LDAP probe strings.
Issue: #10
"""

from adiuvare import Guard


# ── SSTI (Server Side Template Injection) ────────────────────────────────────

def test_guard_flags_ssti_basic_expression():
    guard = Guard()
    gate, event = guard.check_sync(
        "u1",
        payload="{{7*7}}",
    )
    assert event is not None
    assert event.score > 0.0


def test_guard_flags_ssti_jinja_style():
    guard = Guard()
    gate, event = guard.check_sync(
        "u2",
        payload="{{ config.__class__.__init__.__globals__ }}",
    )
    assert event is not None
    assert event.score > 0.0


def test_guard_flags_ssti_nested_expression():
    guard = Guard()
    gate, event = guard.check_sync(
        "u3",
        payload="${{7*'7'}}",
    )
    assert event is not None
    assert event.score > 0.0


# ── NoSQL Injection ───────────────────────────────────────────────────────────

def test_guard_flags_nosql_ne_operator():
    guard = Guard()
    gate, event = guard.check_sync(
        "u4",
        payload='{"username": {"$ne": null}}',
    )
    assert event is not None
    assert event.score > 0.0


def test_guard_flags_nosql_gt_operator():
    guard = Guard()
    gate, event = guard.check_sync(
        "u5",
        payload='{"age": {"$gt": 0}}',
    )
    assert event is not None
    assert event.score > 0.0


def test_guard_flags_nosql_where_operator():
    guard = Guard()
    gate, event = guard.check_sync(
        "u6",
        payload='{"$where": "this.password == this.passwordConfirm"}',
    )
    assert event is not None
    assert event.score > 0.0


# ── LDAP Probe Strings ────────────────────────────────────────────────────────

def test_guard_flags_ldap_wildcard_probe():
    guard = Guard()
    gate, event = guard.check_sync(
        "u7",
        payload="*)(uid=*))(|(uid=*",
    )
    assert event is not None
    assert event.score > 0.0


def test_guard_flags_ldap_injection_bypass():
    guard = Guard()
    gate, event = guard.check_sync(
        "u8",
        payload="admin)(&(password=*))",
    )
    assert event is not None
    assert event.score > 0.0


def test_guard_flags_ldap_blind_probe():
    guard = Guard()
    gate, event = guard.check_sync(
        "u9",
        payload=")(cn=*))(|(cn=*",
    )
    assert event is not None
    assert event.score > 0.0


# ── Benign Comparisons ────────────────────────────────────────────────────────

def test_guard_passes_normal_search_query():
    guard = Guard()
    gate, event = guard.check_sync(
        "u10",
        payload="search for laptop under 50000",
    )
    assert gate.passed is True
    assert event is not None
    assert event.breakdown["payload"] == 0.0


def test_guard_passes_normal_json_payload():
    guard = Guard()
    gate, event = guard.check_sync(
        "u11",
        payload='{"username": "niveditha", "age": 21}',
    )
    assert gate.passed is True
    assert event is not None
    assert event.breakdown["payload"] == 0.0


def test_guard_passes_plain_template_mention():
    guard = Guard()
    gate, event = guard.check_sync(
        "u12",
        payload="render the user name in the template",
    )
    assert gate.passed is True
    assert event is not None
    assert event.breakdown["payload"] == 0.0