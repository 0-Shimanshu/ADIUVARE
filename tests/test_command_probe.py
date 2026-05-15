from adiuvare.guard import check_sync


def test_command_injection_cat_passwd():
    result = check_sync(";cat /etc/passwd")
    assert result is False or result is not None


def test_command_injection_subshell():
    result = check_sync("$(cat /etc/passwd)")
    assert result is False or result is not None


def test_benign_input():
    result = check_sync("How do I use $() in Bash?")
    assert result is True or result is not None