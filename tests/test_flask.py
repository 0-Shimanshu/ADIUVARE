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


def test_flask_drop_table_body_is_blocked():
    app = Flask(__name__)
    guard = Guard()
    guard.use(app, framework="flask")

    @app.post("/billing")
    def billing():
        return jsonify(ok=True)

    client = app.test_client()
    res = client.post(
        "/billing",
        data=b"DROP TABLE users",
        content_type="text/plain",
        headers={"User-Agent": "Mozilla/5.0", "x-user-id": "u90"},
    )
    assert res.status_code in {403, 429}


def test_flask_clean_post_body_is_allowed():
    app = Flask(__name__)
    guard = Guard()
    guard.use(app, framework="flask")

    @app.post("/submit")
    def submit():
        return jsonify(ok=True)

    client = app.test_client()
    res = client.post(
        "/submit",
        data=b"name=Alice&message=hello+world",
        content_type="text/plain",
        headers={"User-Agent": "Mozilla/5.0", "x-user-id": "u91"},
    )
    assert res.status_code == 200


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


def _capture_flask_payload(monkeypatch, guard, client_call_func) -> str | None:
    captured = None

    async def fake_inspect(ctx, **kwargs):
        nonlocal captured
        captured = ctx.payload
        return type("Gate", (), {"passed": True, "status_code": 200, "block_reason": ""}), None

    monkeypatch.setattr(guard, "inspect", fake_inspect)
    client_call_func()
    return captured


def test_flask_payload_merging_exact_shape(monkeypatch):
    app = Flask(__name__)
    guard = Guard()
    guard.use(app, framework="flask")

    @app.post("/merge")
    def merge_view():
        return jsonify(ok=True)

    client = app.test_client()
    body = '{"body_key": "body_val", "name": "body_name"}'

    payload = _capture_flask_payload(
        monkeypatch, guard,
        lambda: client.post(
            "/merge?tag=a&tag=b&empty=&name=query_name",
            data=body,
            headers={"x-user-id": "u1", "Content-Type": "application/json"},
        ),
    )

    assert payload == body + "\n" + "a b  query_name"


def test_flask_payload_raw_body(monkeypatch):
    app = Flask(__name__)
    guard = Guard()
    guard.use(app, framework="flask")

    @app.post("/raw")
    def raw_view():
        return jsonify(ok=True)

    client = app.test_client()
    sql_text = "select * from users where id = '' or 1=1"

    payload = _capture_flask_payload(
        monkeypatch, guard,
        lambda: client.post(
            "/raw",
            data=sql_text.encode(),
            content_type="text/plain",
            headers={"x-user-id": "u1"},
        ),
    )

    assert payload == sql_text


def test_flask_payload_query_only(monkeypatch):
    app = Flask(__name__)
    guard = Guard()
    guard.use(app, framework="flask")

    @app.get("/items")
    def items_view():
        return jsonify(ok=True)

    client = app.test_client()

    payload = _capture_flask_payload(
        monkeypatch, guard,
        lambda: client.get(
            "/items?status=active&limit=10",
            headers={"User-Agent": "Mozilla/5.0", "x-user-id": "u1"},
        ),
    )

    assert payload == "active 10"


def test_flask_payload_encoded_query_normalization(monkeypatch):
    app = Flask(__name__)
    guard = Guard()
    guard.use(app, framework="flask")

    @app.get("/search")
    def search_view():
        return jsonify(ok=True)

    client = app.test_client()

    payload = _capture_flask_payload(
        monkeypatch, guard,
        lambda: client.get(
            "/search?name=hello%27world&city=New%20York",
            headers={"User-Agent": "Mozilla/5.0", "x-user-id": "u1"},
        ),
    )

    assert payload == "hello'world New York"


def test_flask_payload_blank_query_omission(monkeypatch):
    app = Flask(__name__)
    guard = Guard()
    guard.use(app, framework="flask")

    @app.post("/raw")
    def raw_view():
        return jsonify(ok=True)

    client = app.test_client()
    body = "select * from users where id = '' or 1=1"

    payload_a = _capture_flask_payload(
        monkeypatch, guard,
        lambda: client.post(
            "/raw",
            data=body.encode(),
            content_type="text/plain",
            headers={"x-user-id": "u1"},
        ),
    )
    assert payload_a == body

    payload_b = _capture_flask_payload(
        monkeypatch, guard,
        lambda: client.post(
            "/raw?a=&b=",
            data=body.encode(),
            content_type="text/plain",
            headers={"x-user-id": "u1"},
        ),
    )
    assert payload_b == body


def test_flask_payload_bare_request(monkeypatch):
    app = Flask(__name__)
    guard = Guard()
    guard.use(app, framework="flask")

    @app.get("/ping")
    def ping():
        return jsonify(ok=True)

    client = app.test_client()

    payload = _capture_flask_payload(
        monkeypatch, guard,
        lambda: client.get(
            "/ping",
            headers={"User-Agent": "Mozilla/5.0", "x-user-id": "u1"},
        ),
    )

    assert payload is None


def test_flask_exempt_decorator_preserves_sync_route_handler():
    app = Flask(__name__)
    guard = Guard()
    guard.use(app, framework="flask")

    @app.get("/health")
    @guard.exempt()
    def health():
        return jsonify(ok=True)

    client = app.test_client()
    res = client.get("/health", headers={"User-Agent": "Mozilla/5.0", "x-user-id": "u92"})

    assert res.status_code == 200
    assert res.get_json() == {"ok": True}


def test_flask_protect_decorator_preserves_sync_route_handler():
    app = Flask(__name__)
    guard = Guard()
    guard.use(app, framework="flask")

    @app.get("/profile")
    @guard.protect(sensitivity="critical", trackB=False)
    def profile():
        return jsonify(ok=True)

    client = app.test_client()
    res = client.get("/profile", headers={"User-Agent": "Mozilla/5.0", "x-user-id": "u93"})

    assert res.status_code == 200
    assert res.get_json() == {"ok": True}


def test_flask_policy_decorator_preserves_sync_route_handler():
    app = Flask(__name__)
    guard = Guard()
    guard.use(app, framework="flask")

    @app.get("/admin")
    @guard.policy("admin", trackB=False)
    def admin():
        return jsonify(ok=True)

    client = app.test_client()
    res = client.get("/admin", headers={"User-Agent": "Mozilla/5.0", "x-user-id": "u94"})

    assert res.status_code == 200
    assert res.get_json() == {"ok": True}