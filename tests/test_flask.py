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
