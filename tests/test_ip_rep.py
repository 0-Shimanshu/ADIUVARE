import asyncio



from adiuvare.core.models import RequestContext
from adiuvare.signals.ip_rep import IPRepSignal


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------

def make_ctx(ip: str, headers: dict | None = None) -> RequestContext:
    return RequestContext(
        identity="u1",
        payload=None,
        url="/",
        method="GET",
        headers=headers or {},
        ip=ip,
        endpoint="/",
    )


def run(ip: str, headers: dict | None = None):
    return asyncio.run(IPRepSignal().extract(make_ctx(ip, headers)))


# ---------------------------------------------------------------------------
# Private and loopback IPs
# ---------------------------------------------------------------------------

def test_private_ip_scores_zero():
    result = run("192.168.1.1")
    assert result.score == 0.0
    assert result.reason == "ip_local"


def test_loopback_ipv4_scores_zero():
    result = run("127.0.0.1")
    assert result.score == 0.0
    assert result.reason == "ip_local"


def test_loopback_ipv6_scores_zero():
    result = run("::1")
    assert result.score == 0.0
    assert result.reason == "ip_local"


def test_private_class_a_scores_zero():
    result = run("10.0.0.1")
    assert result.score == 0.0
    assert result.reason == "ip_local"


def test_private_class_b_scores_zero():
    result = run("172.16.0.1")
    assert result.score == 0.0
    assert result.reason == "ip_local"


# ---------------------------------------------------------------------------
# Invalid / unparseable IPs
# ---------------------------------------------------------------------------

def test_invalid_ip_scores_012():
    result = run("not-an-ip")
    assert result.score == 0.12
    assert result.reason == "ip_parse_err"


def test_empty_string_ip_scores_012():
    result = run("")
    assert result.score == 0.12
    assert result.reason == "ip_parse_err"


def test_malformed_octet_scores_012():
    result = run("999.999.999.999")
    assert result.score == 0.12
    assert result.reason == "ip_parse_err"


def test_partial_ip_scores_012():
    result = run("192.168")
    assert result.score == 0.12
    assert result.reason == "ip_parse_err"


# ---------------------------------------------------------------------------
# Tor exit hint
# ---------------------------------------------------------------------------

def test_tor_exit_header_scores_035():
    result = run("8.8.8.8", headers={"x-tor-exit": "1"})
    assert result.score == 0.35
    assert result.reason == "tor_hint"
    assert result.detail.get("ip") == "8.8.8.8"


def test_tor_exit_header_not_set_does_not_trigger():
    result = run("8.8.8.8", headers={"x-tor-exit": "0"})
    assert result.score == 0.0
    assert result.reason == "ip_clean"


# ---------------------------------------------------------------------------
# Noisy network prefixes
# ---------------------------------------------------------------------------

def test_noisy_net_185_220_scores_020():
    result = run("185.220.0.1")
    assert result.score == 0.20
    assert result.reason == "noisy_net"
    assert result.detail.get("ip") == "185.220.0.1"


def test_noisy_net_45_155_scores_020():
    result = run("45.155.0.1")
    assert result.score == 0.20
    assert result.reason == "noisy_net"


def test_noisy_net_198_51_100_is_shadowed_by_private_check():
    # 198.51.100.0/24 is an IANA documentation range; Python's ipaddress
    # module marks it as private, so the is_private guard fires before the
    # noisy_net prefix check is reached. This means the "198.51.100." entry
    # in _noisy_nets is currently dead code and will never score 0.20.
    result = run("198.51.100.1")
    assert result.score == 0.0
    assert result.reason == "ip_local"


def test_noisy_net_203_0_113_is_shadowed_by_private_check():
    # 203.0.113.0/24 is an IANA documentation range; same situation as above.
    # The "203.0.113." entry in _noisy_nets is unreachable dead code.
    result = run("203.0.113.1")
    assert result.score == 0.0
    assert result.reason == "ip_local"


# ---------------------------------------------------------------------------
# Clean public IPs
# ---------------------------------------------------------------------------

def test_clean_public_ip_scores_zero():
    result = run("8.8.8.8")
    assert result.score == 0.0
    assert result.reason == "ip_clean"


def test_another_clean_public_ip_scores_zero():
    result = run("1.1.1.1")
    assert result.score == 0.0
    assert result.reason == "ip_clean"


# ---------------------------------------------------------------------------
# Tor exit takes priority over noisy net
# ---------------------------------------------------------------------------

def test_tor_hint_takes_priority_over_noisy_net():
    # A noisy-net IP that also carries the tor hint should score as tor
    result = run("185.220.0.1", headers={"x-tor-exit": "1"})
    assert result.score == 0.35
    assert result.reason == "tor_hint"