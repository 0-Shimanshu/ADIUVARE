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

def test_django_payload_merging(monkeypatch):
    guard = Guard()
    captured_payload = None

    async def fake_inspect(ctx, **kwargs):
        nonlocal captured_payload
        captured_payload = ctx.payload
        return type('Gate', (), {'passed': True, 'status_code': 200, 'block_reason': ''}), None

    monkeypatch.setattr(guard, "inspect", fake_inspect)
    mw = AdiuvareMiddleware(lambda req: DummyRes(200), guard)

    query_str = "tag=a&tag=b&empty=&name=query_name"
    req = DummyReq(
        "/merge",
        method="POST",
        query=query_str,
        body=b'{"body_key": "body_val", "name": "body_name"}'
    )
    mw(req)
    assert isinstance(captured_payload, str)
    assert '"body_key": "body_val"' in captured_payload
    assert '"name": "body_name"' in captured_payload
    assert "a" in captured_payload
    assert "b" in captured_payload
    assert "query_name" in captured_payload


def test_django_payload_raw_body(monkeypatch):
    guard = Guard()
    captured_payload = None
    async def fake_inspect(ctx, **kwargs):
        nonlocal captured_payload
        captured_payload = ctx.payload
        return type('Gate', (), {'passed': True, 'status_code': 200, 'block_reason': ''}), None

    monkeypatch.setattr(guard, "inspect", fake_inspect)
    mw = AdiuvareMiddleware(lambda req: DummyRes(200), guard)

    sql_text = "select * from users where id = '' or 1=1"
    req = DummyReq(
        "/raw",
        method="POST",
        body=sql_text.encode(),
    )
    mw(req)
    assert isinstance(captured_payload, str)
    assert sql_text in captured_payload