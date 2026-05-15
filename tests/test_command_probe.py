from adiuvare.guard import Guard


def test_command_probe_semicolon_blocked():
    guard = Guard()

    result = guard.check_sync(
        identity="test-user",
        payload=";cat /etc/passwd"
    )

    
    assert result.blocked is True


def test_command_probe_dollar_blocked():
    guard = Guard()

    result = guard.check_sync(
        identity="test-user",
        payload="$(cat /etc/passwd)"
    )

    assert result.blocked is True


def test_benign_case_not_blocked():
    guard = Guard()

    result = guard.check_sync(
        identity="test-user",
        payload="How do I use $() in Bash?"
    )

    assert result.blocked is False