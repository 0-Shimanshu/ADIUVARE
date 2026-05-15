from urllib.parse import parse_qs

from adiuvare import Guard
from adiuvare.integrations.django import AdiuvareMiddleware


class _SimpleQueryDict(dict):
    def getlist(self, key):
        return self.get(key, [])


class DummyReq:
    def __init__(
        self,
        path: str,
        method: str = "GET",
        body: bytes = b"",
        headers=None,
        ip: str = "127.0.0.1",
        query: str = "",
    ):
        self.path = path
        self.method = method
        self.body = body
        self.headers = headers or {}
        self.META = {"REMOTE_ADDR": ip, "QUERY_STRING": query}
        self.GET = _SimpleQueryDict(parse_qs(query, keep_blank_values=True))


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
    import json
    guard = Guard()

    captured_payload = None

    class FakeGate:
        passed = True
        status_code = 200
        block_reason = ""

    async def fake_inspect(ctx, **kwargs):
        nonlocal captured_payload
        captured_payload = ctx.payload
        return FakeGate(), None

    monkeypatch.setattr(guard, "inspect", fake_inspect)
    mw = AdiuvareMiddleware(lambda req: DummyRes(200), guard)

    req = DummyReq("/merge", method="POST", body=b'{"body_key": "body_val", "name": "body_name"}')

    class FakeQueryDict(dict):
        def getlist(self, key):
            val = self.get(key, [])
            return val if isinstance(val, list) else [val]

    req.GET = FakeQueryDict({"tag": ["a", "b"], "empty": "", "name": "query_name"})

    res = mw(req)
    assert res.status_code == 200
    assert captured_payload is not None
    payload_dict = json.loads(captured_payload)
    assert payload_dict["tag"] == ["a", "b"]
    assert payload_dict["empty"] == ""
    assert payload_dict["name"] == "body_name"
    assert payload_dict["body_key"] == "body_val"
    assert set(payload_dict.keys()) == {"tag", "empty", "name", "body_key"}


def test_django_payload_raw_body(monkeypatch):
    import json
    guard = Guard()

    captured_payload = None

    class FakeGate:
        passed = True
        status_code = 200
        block_reason = ""

    async def fake_inspect(ctx, **kwargs):
        nonlocal captured_payload
        captured_payload = ctx.payload
        return FakeGate(), None

    monkeypatch.setattr(guard, "inspect", fake_inspect)
    mw = AdiuvareMiddleware(lambda req: DummyRes(200), guard)

    req = DummyReq(
        "/raw",
        method="POST",
        body=b"select * from users where id = '' or 1=1",
    )

    res = mw(req)
    assert res.status_code == 200
    assert captured_payload is not None
    payload_dict = json.loads(captured_payload)
    assert payload_dict["_body"] == "select * from users where id = '' or 1=1"
