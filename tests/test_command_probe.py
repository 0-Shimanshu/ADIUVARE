from adiuvare.guard import Guard


def test_command_probe_semicolon_detected():
    guard = Guard()

    gate, event = guard.check_sync(
        identity="test-user",
        payload=";cat /etc/passwd"
    )

    assert gate.passed is True
    assert event is not None
    assert event.score > 0.35
    assert "payload" in event.breakdown
    assert event.breakdown["payload"] > 0.0


def test_command_probe_dollar_detected():
    guard = Guard()

    gate, event = guard.check_sync(
        identity="test-user",
        payload="$(cat /etc/passwd)"
    )

    assert gate.passed is True
    assert event is not None
    assert event.score > 0.35
    assert "payload" in event.breakdown
    assert event.breakdown["payload"] > 0.0


def test_benign_case_stays_clean():
    guard = Guard()

    gate, event = guard.check_sync(
        identity="test-user",
        payload="How do I use $() in Bash?"
    )

    assert gate.passed is True
    assert event is not None
    assert event.score < 0.3