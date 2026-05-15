from flask import Flask, jsonify, request

from adiuvare import Guard
from adiuvare.state.identity_store import ThreadSafeIdentityStore


def test_flask_middleware_allows_clean_request():
    app = Flask(__name__)
    guard = Guard()
    guard.use(app, framework="flask")

    @app.get("/ping")
    def ping():
        assert request.environ.get("adiuvare.event") is not None
        return jsonify(ok=True)

    client = app.test_client()
    res = client.get("/ping", headers={"User-Agent": "Mozilla/5.0", "x-user-id": "u1"})
    assert res.status_code == 200
    assert res.get_json() == {"ok": True}


def test_flask_middleware_blocks_when_identity_is_blocked():
    app = Flask(__name__)
    guard = Guard()
    guard._id_store.set_blocked("u1", 60)
    guard.use(app, framework="flask")

    @app.get("/ping")
    def ping():
        return jsonify(ok=True)

    client = app.test_client()
    res = client.get("/ping", headers={"User-Agent": "Mozilla/5.0", "x-user-id": "u1"})
    assert res.status_code == 429


def test_guard_from_config_builds_flask_guard(tmp_path):
    cfg_path = tmp_path / "adiuvare.yaml"
    cfg_path.write_text("runtime:\n  observe_only: true\n")

    app = Flask(__name__)
    guard = Guard.from_config(cfg_path)
    guard.use(app, framework="flask")

    @app.get("/ping")
    def ping():
        return jsonify(ok=True)

    client = app.test_client()
    res = client.get("/ping", headers={"User-Agent": "Mozilla/5.0", "x-user-id": "u2"})
    assert res.status_code == 200
    assert guard.config.runtime.observe_only is True


def test_flask_blocks_banned_forwarded_ip():
    app = Flask(__name__)
    guard = Guard()
    guard.whitelist.ban_ip("203.0.113.4")
    guard.use(app, framework="flask")

    @app.get("/ping")
    def ping():
        return jsonify(ok=True)

    client = app.test_client()
    res = client.get(
        "/ping",
        headers={
            "User-Agent": "Mozilla/5.0",
            "x-user-id": "u3",
            "x-forwarded-for": "203.0.113.4",
        },
    )
    assert res.status_code == 403


def test_flask_use_swaps_in_threadsafe_store():
    app = Flask(__name__)
    guard = Guard()
    guard.use(app, framework="flask")
    assert isinstance(guard._id_store, ThreadSafeIdentityStore)


def test_flask_query_sqli_does_not_stay_open():
    app = Flask(__name__)
    guard = Guard()
    guard.use(app, framework="flask")

    @app.get("/search")
    def search():
        return jsonify(ok=True)

    client = app.test_client()
    res = client.get(
        "/search",
        query_string={"q": "' UNION SELECT password FROM users--"},
        headers={"User-Agent": "Mozilla/5.0", "x-user-id": "u4"},
    )
    assert res.status_code in {403, 429}


def test_flask_body_sqli_does_not_stay_open():
    app = Flask(__name__)
    guard = Guard()
    guard.use(app, framework="flask")

    @app.post("/billing")
    def billing():
        return jsonify(ok=True)

    client = app.test_client()
    res = client.post(
        "/billing",
        data=b"select * from users where id = '' or 1=1",
        content_type="text/plain",
        headers={"User-Agent": "curl/8.0", "x-user-id": "u5"},
    )
    assert res.status_code in {403, 429}


def test_flask_route_cfg_can_skip_trackB():
    app = Flask(__name__)
    guard = Guard()
    guard.configure_routes({"/billing": {"trackB": False}})
    guard.use(app, framework="flask")

    @app.post("/billing")
    def billing():
        return jsonify(ok=True)

    client = app.test_client()
    res = client.post(
        "/billing",
        data=b"select * from users where id = '' or 1=1",
        content_type="text/plain",
        headers={"User-Agent": "curl/8.0", "x-user-id": "u6"},
    )
    assert res.status_code == 200


def test_flask_payload_merging(monkeypatch):
    import json
    app = Flask(__name__)
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
    guard.use(app, framework="flask")

    @app.post("/merge")
    def merge():
        return jsonify(ok=True)

    client = app.test_client()
    res = client.post(
        "/merge?tag=a&tag=b&empty=&name=query_name",
        json={"body_key": "body_val", "name": "body_name"},
        headers={"User-Agent": "test", "x-user-id": "u1"},
    )
    assert res.status_code == 200
    assert captured_payload is not None
    payload_dict = json.loads(captured_payload)
    assert payload_dict["tag"] == ["a", "b"]
    assert payload_dict["empty"] == ""
    assert payload_dict["name"] == "body_name"
    assert payload_dict["body_key"] == "body_val"
    assert set(payload_dict.keys()) == {"tag", "empty", "name", "body_key"}


def test_flask_payload_raw_body(monkeypatch):
    import json
    app = Flask(__name__)
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
    guard.use(app, framework="flask")

    @app.post("/raw")
    def raw():
        return jsonify(ok=True)

    client = app.test_client()
    res = client.post(
        "/raw",
        data=b"select * from users where id = '' or 1=1",
        content_type="text/plain",
        headers={"User-Agent": "curl/8.0", "x-user-id": "u1"},
    )
    assert res.status_code == 200
    assert captured_payload is not None
    payload_dict = json.loads(captured_payload)
    assert payload_dict["_body"] == "select * from users where id = '' or 1=1"
