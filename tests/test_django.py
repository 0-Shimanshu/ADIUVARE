from adiuvare import Guard
from adiuvare.integrations.django import AdiuvareMiddleware


class DummyReq:
    def __init__(self, path, method="GET", body=b"", query="", headers=None):
        self.path = path
        self.method = method
        self.body = body
        self.headers = headers or {}
        self.META = {"REMOTE_ADDR": "127.0.0.1", "QUERY_STRING": query}


class DummyRes:
    def __init__(self, status: int) -> None:
        self.status_code = status


def test_django_middleware_allows_clean_request():
    guard = Guard()
    mw = AdiuvareMiddleware(lambda req: DummyRes(200), guard)
    req = DummyReq("/ping", headers={"User-Agent": "Mozilla/5.0", "x-user-id": "u1"})
    res = mw(req)
    assert res.status_code == 200
    assert req.adiuvare_event is not None


def test_django_middleware_blocks_banned_identity():
    guard = Guard()
    guard._id_store.set_blocked("u1", 60)
    mw = AdiuvareMiddleware(lambda req: DummyRes(200), guard)
    req = DummyReq("/ping", headers={"User-Agent": "Mozilla/5.0", "x-user-id": "u1"})
    res = mw(req)
    assert res.status_code == 429


def test_django_query_sqli_does_not_stay_open():
    guard = Guard()
    mw = AdiuvareMiddleware(lambda req: DummyRes(200), guard)
    req = DummyReq(
        "/search",
        headers={"User-Agent": "Mozilla/5.0", "x-user-id": "u2"},
        query="q=' UNION SELECT password FROM users--",
    )
    res = mw(req)
    assert res.status_code in {403, 429}


def test_django_body_sqli_does_not_stay_open():
    guard = Guard()
    mw = AdiuvareMiddleware(lambda req: DummyRes(200), guard)
    req = DummyReq(
        "/billing",
        method="POST",
        body=b"select * from users where id = '' or 1=1",
        headers={"User-Agent": "curl/8.0", "x-user-id": "u3"},
    )
    res = mw(req)
    assert res.status_code in {403, 429}


def test_django_drop_table_body_is_blocked():
    guard = Guard()
    mw = AdiuvareMiddleware(lambda req: DummyRes(200), guard)
    req = DummyReq(
        "/billing",
        method="POST",
        body=b"DROP TABLE users",
        headers={"User-Agent": "Mozilla/5.0", "x-user-id": "u90"},
    )
    res = mw(req)
    assert res.status_code in {403, 429}


def test_django_clean_post_body_is_allowed():
    guard = Guard()
    mw = AdiuvareMiddleware(lambda req: DummyRes(200), guard)
    req = DummyReq(
        "/submit",
        method="POST",
        body=b"name=Alice&message=hello+world",
        headers={"User-Agent": "Mozilla/5.0", "x-user-id": "u91"},
    )
    res = mw(req)
    assert res.status_code == 200


def test_django_route_cfg_can_skip_trackB():
    guard = Guard()
    guard.configure_routes({"/billing": {"trackB": False}})
    mw = AdiuvareMiddleware(lambda req: DummyRes(200), guard)
    req = DummyReq(
        "/billing",
        method="POST",
        body=b"select * from users where id = '' or 1=1",
        headers={"User-Agent": "curl/8.0", "x-user-id": "u4"},
    )
    res = mw(req)
    assert res.status_code == 200


def _capture_middleware_payload(monkeypatch, mw, req) -> str | None:
    captured = None

    async def fake_inspect(ctx, **kwargs):
        nonlocal captured
        captured = ctx.payload
        return type('Gate', (), {'passed': True, 'status_code': 200, 'block_reason': ''}), None

    monkeypatch.setattr(mw._guard, "inspect", fake_inspect)
    mw(req)
    return captured


def test_django_payload_merging_exact_shape(monkeypatch):
    mw = AdiuvareMiddleware(lambda req: DummyRes(200), Guard())
    
    query_str = "tag=a&tag=b&empty=&name=query_name"
    body_str = '{"body_key": "body_val", "name": "body_name"}'
    
    req = DummyReq("/merge", method="POST", query=query_str, body=body_str.encode())
    payload = _capture_middleware_payload(monkeypatch, mw, req)

    assert isinstance(payload, str)
    assert payload == body_str + "\n" + "a b  query_name"


def test_django_payload_query_only(monkeypatch):
    mw = AdiuvareMiddleware(lambda req: DummyRes(200), Guard())
    req = DummyReq("/items", method="GET", query="status=active&limit=10", body=b"")
    
    payload = _capture_middleware_payload(monkeypatch, mw, req)
    assert isinstance(payload, str)
    assert payload == "active 10"


def test_django_payload_blank_query_omission(monkeypatch):
    mw = AdiuvareMiddleware(lambda req: DummyRes(200), Guard())
    body_str = "select * from users where id = '' or 1=1"
    
    req_a = DummyReq("/raw", method="POST", query="", body=body_str.encode())
    payload_a = _capture_middleware_payload(monkeypatch, mw, req_a)
    assert payload_a == body_str

    req_b = DummyReq("/raw", method="POST", query="a=&b=", body=body_str.encode())
    payload_b = _capture_middleware_payload(monkeypatch, mw, req_b)
    assert payload_b == body_str


def test_django_payload_empty_request_fallback(monkeypatch):
    mw = AdiuvareMiddleware(lambda req: DummyRes(200), Guard())
    req = DummyReq("/ping", method="GET", query="", body=b"")
    
    payload = _capture_middleware_payload(monkeypatch, mw, req)
    assert payload is None


def test_django_payload_encoded_query_normalization(monkeypatch):
    mw = AdiuvareMiddleware(lambda req: DummyRes(200), Guard())
    req = DummyReq("/search", method="GET", query="name=hello%27world&city=New%20York", body=b"")
    
    payload = _capture_middleware_payload(monkeypatch, mw, req)
    assert isinstance(payload, str)
    assert payload == "hello'world New York"


def test_django_payload_raw_body(monkeypatch):
    mw = AdiuvareMiddleware(lambda req: DummyRes(200), Guard())
    sql_text = "select * from users where id = '' or 1=1"
    req = DummyReq("/raw", method="POST", body=sql_text.encode())
    
    payload = _capture_middleware_payload(monkeypatch, mw, req)
    assert payload == sql_text