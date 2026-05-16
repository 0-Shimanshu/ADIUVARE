import asyncio
import time
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient

from adiuvare import Guard
from adiuvare.core.models import AdiuvareEvent, RequestContext, SignalResult
from adiuvare.signals.ai import AISignal
from adiuvare.signals.base import SoftSignal


class SlowSignal(SoftSignal):
    name = "slow"
    weight = 0.10

    async def extract(self, ctx: RequestContext) -> SignalResult:
        await asyncio.sleep(0.2)
        return SignalResult(score=0.0, reason="slow_clean")


def test_fastapi_middleware_allows_clean_request():
    app = FastAPI()
    guard = Guard()
    guard.use(app, framework="fastapi")

    @app.get("/ping")
    async def ping():
        return {"ok": True}

    client = TestClient(app)
    res = client.get("/ping", headers={"User-Agent": "Mozilla/5.0", "x-user-id": "u1"})
    assert res.status_code == 200
    assert res.json() == {"ok": True}


def test_fastapi_middleware_blocks_when_identity_is_blocked():
    app = FastAPI()
    guard = Guard()
    guard._id_store.set_blocked("u1", 60)
    guard.use(app, framework="fastapi")

    @app.get("/ping")
    async def ping():
        return {"ok": True}

    client = TestClient(app)
    res = client.get("/ping", headers={"User-Agent": "Mozilla/5.0", "x-user-id": "u1"})
    assert res.status_code == 429


def test_fastapi_runs_trackB_in_background():
    app = FastAPI()
    guard = Guard(soft_signals=[SlowSignal()])
    seen = []

    @guard.hooks.on_event
    def _take(event):
        seen.append(event.verdict)

    guard.use(app, framework="fastapi")

    @app.get("/ping")
    async def ping():
        return {"ok": True}

    client = TestClient(app)
    started = time.perf_counter()
    res = client.get("/ping", headers={"User-Agent": "Mozilla/5.0", "x-user-id": "u2"})
    elapsed = time.perf_counter() - started

    assert res.status_code == 200
    assert elapsed < 0.18
    assert seen == []
    time.sleep(0.3)
    assert seen == ["allow"]


def test_fastapi_lazy_starts_runtime_when_hooks_are_skipped(tmp_path):
    cfg = tmp_path / "adiuvare.yaml"
    cfg.write_text(
        "\n".join(
            [
                "runtime:",
                f"  audit_db_path: '{(tmp_path / 'audit.db').as_posix()}'",
                f"  state_db_path: '{(tmp_path / 'state.db').as_posix()}'",
            ]
        ),
        encoding="utf-8",
    )

    app = FastAPI()
    guard = Guard(config_path=str(cfg), soft_signals=[SlowSignal()])
    guard.use(app, framework="fastapi")

    @app.get("/ping")
    async def ping():
        return {"ok": True}

    client = TestClient(app)
    res = client.get("/ping", headers={"User-Agent": "Mozilla/5.0", "x-user-id": "u2"})
    assert res.status_code == 200
    assert guard._bg_started is True
    assert Path(guard.event_stream.path).exists()


def test_fastapi_background_trackB_writes_audit_and_stream(monkeypatch):
    app = FastAPI()
    guard = Guard()
    seen = {"audit": [], "stream": []}
    event = AdiuvareEvent(
        identity="u5",
        endpoint="/ping",
        score=0.0,
        verdict="allow",
        breakdown={},
        detail={},
    )

    async def fake_trackB(_ctx):
        return event

    async def fake_emit(item):
        seen["stream"].append(item.verdict)

    def fake_write(item):
        seen["audit"].append(item.verdict)

    monkeypatch.setattr(guard._pipeline, "trackB", fake_trackB)
    monkeypatch.setattr(guard.event_stream, "emit", fake_emit)
    monkeypatch.setattr(guard._audit, "write", fake_write)
    guard.use(app, framework="fastapi")

    @app.get("/ping")
    async def ping():
        return {"ok": True}

    client = TestClient(app)
    res = client.get("/ping", headers={"User-Agent": "Mozilla/5.0", "x-user-id": "u5"})
    assert res.status_code == 200

    stop = time.time() + 0.3
    while time.time() < stop and (not seen["audit"] or not seen["stream"]):
        time.sleep(0.01)

    assert seen["audit"] == ["allow"]
    assert seen["stream"] == ["allow"]


def test_fastapi_returns_hold_for_admin_post():
    app = FastAPI()
    guard = Guard()
    guard.use(app, framework="fastapi")

    @app.post("/admin/login")
    async def login():
        return {"ok": True}

    client = TestClient(app)
    res = client.post(
        "/admin/login",
        content="user=demo",
        headers={"User-Agent": "Mozilla/5.0", "x-user-id": "u3"},
    )
    assert res.status_code == 202


def test_fastapi_blocks_banned_forwarded_ip():
    app = FastAPI()
    guard = Guard()
    guard.whitelist.ban_ip("203.0.113.4")
    guard.use(app, framework="fastapi")

    @app.get("/ping")
    async def ping():
        return {"ok": True}

    client = TestClient(app)
    res = client.get(
        "/ping",
        headers={
            "User-Agent": "Mozilla/5.0",
            "x-user-id": "u6",
            "x-forwarded-for": "203.0.113.4",
        },
    )
    assert res.status_code == 403


def test_fastapi_query_sqli_does_not_stay_open():
    app = FastAPI()
    guard = Guard()
    guard.use(app, framework="fastapi")

    @app.get("/search")
    async def search():
        return {"ok": True}

    client = TestClient(app)
    res = client.get(
        "/search",
        params={"q": "' UNION SELECT password FROM users--"},
        headers={"User-Agent": "Mozilla/5.0", "x-user-id": "u7"},
    )
    assert res.status_code in {403, 429}


def test_fastapi_body_sqli_does_not_stay_open():
    app = FastAPI()
    guard = Guard()
    guard.use(app, framework="fastapi")

    @app.post("/billing")
    async def billing():
        return {"ok": True}

    client = TestClient(app)
    res = client.post(
        "/billing",
        content="select * from users where id = '' or 1=1",
        headers={"User-Agent": "curl/8.0", "x-user-id": "u8"},
    )
    assert res.status_code in {403, 429}


def test_guard_auto_attaches_fastapi():
    app = FastAPI()
    guard = Guard.auto(app)

    @app.get("/ping")
    async def ping():
        return {"ok": True}

    client = TestClient(app)
    res = client.get("/ping", headers={"User-Agent": "Mozilla/5.0", "x-user-id": "u4"})
    assert res.status_code == 200
    assert guard.pipeline is not None


def test_fastapi_drop_table_body_is_blocked():
    app = FastAPI()
    guard = Guard()
    guard.use(app, framework="fastapi")

    @app.post("/billing")
    async def billing():
        return {"ok": True}

    client = TestClient(app)
    res = client.post(
        "/billing",
        content="DROP TABLE users",
        headers={"User-Agent": "Mozilla/5.0", "x-user-id": "u90"},
    )
    assert res.status_code in {403, 429}


def test_fastapi_clean_post_body_is_allowed():
    app = FastAPI()
    guard = Guard()
    guard.use(app, framework="fastapi")

    @app.post("/submit")
    async def submit():
        return {"ok": True}

    client = TestClient(app)
    res = client.post(
        "/submit",
        content="name=Alice&message=hello+world",
        headers={"User-Agent": "Mozilla/5.0", "x-user-id": "u91"},
    )
    assert res.status_code == 200


def test_fastapi_route_ai_mode_override_is_used():
    app = FastAPI()
    guard = Guard()

    async def fake_review(_ctx, _score):
        return SignalResult(
            score=0.0,
            reason="ai_malicious",
            detail={"verdict": "malicious", "confidence": 0.95},
        )

    guard._pipeline._ai_sig = AISignal(caller=lambda *_: None)
    guard._pipeline._ai_sig.review = fake_review
    guard.use(app, framework="fastapi")

    @app.post("/review")
    @guard.protect(ai_mode="critical")
    async def review():
        return {"ok": True}

    client = TestClient(app)
    res = client.post(
        "/review",
        content="hello there",
        headers={"User-Agent": "Mozilla/5.0", "x-user-id": "u9"},
    )
    assert res.status_code == 403
