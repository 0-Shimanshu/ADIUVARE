from adiuvare.signals.patterns import check_sql, check_xss


def test_scan_returns_highest_confidence_when_multiple_patterns_match():
    hit, conf, label = check_sql("SELECT * FROM users UNION SELECT null,null--")
    assert hit is True
    assert label == "union_select"
    assert conf == 0.92


def test_scan_returns_drop_table_over_select_from():
    hit, conf, label = check_sql("SELECT * FROM users; DROP TABLE users--")
    assert hit is True
    assert label == "drop_table"
    assert conf == 0.95


def test_scan_single_match_still_works():
    hit, conf, label = check_sql("DROP TABLE users")
    assert hit is True
    assert label == "drop_table"
    assert conf == 0.95


def test_scan_no_match_returns_clean():
    hit, conf, label = check_sql("hello world")
    assert hit is False
    assert conf == 0.0
    assert label == ""


def test_scan_xss_returns_highest_when_multiple_match():
    hit, conf, label = check_xss("<script onload=alert(1)>")
    assert hit is True
    assert label == "script_tag"
    assert conf >= 0.72
