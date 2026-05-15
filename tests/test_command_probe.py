from adiuvare.guard import Guard


def test_command_probe_semicolon_blocked():
    guard = Guard()

    gate, event = guard.check_sync(
        identity="test-user",
        payload=";cat /etc/passwd"
    )

    assert gate.passed is False
    assert event is not None


def test_command_probe_dollar_blocked():
    guard = Guard()

    gate, event = guard.check_sync(
        identity="test-user",
        payload="$(cat /etc/passwd)"
    )

    assert gate.passed is False
    assert event is not None


def test_benign_case_not_blocked():
    guard = Guard()

    gate, event = guard.check_sync(
        identity="test-user",
        payload="How do I use $() in Bash?"
    )

    assert gate.passed is True
    assert event is not None