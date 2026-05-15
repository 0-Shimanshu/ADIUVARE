from adiuvare import Guard
from adiuvare.integrations.django import AdiuvareMiddleware


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
