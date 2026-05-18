import asyncio
import inspect

from adiuvare import Guard
from adiuvare.policies import BUILTIN_POLICIES
from adiuvare.state.event_stream import RedisEventStream


def test_guard_uses_redis_stream_from_config(tmp_path):
    cfg_path = tmp_path / "adiuvare.yaml"
    cfg_path.write_text(
        """
runtime:
  backend: redis
  redis_url: redis://127.0.0.1:6379/0
"""
    )

    guard = Guard.from_config(cfg_path)
    assert isinstance(guard.event_stream, RedisEventStream)


def test_guard_builds_ai_signal_from_config(tmp_path):
    cfg_path = tmp_path / "adiuvare.yaml"
    cfg_path.write_text(
        """
ai:
  enabled: true
  mode: assist
  model: mistral
  base_url: http://127.0.0.1:9000
  api_key: demo-key
  timeout_secs: 9
"""
    )

    guard = Guard.from_config(cfg_path)
    ai_sig = guard.pipeline._ai_sig
    assert ai_sig._model == "mistral"
    assert ai_sig._url == "http://127.0.0.1:9000/api/generate"
    assert ai_sig._api_key == "demo-key"
    assert ai_sig._timeout == 9.0


def test_guard_startbgtasks_restores_state(tmp_path):
    cfg_path = tmp_path / "adiuvare.yaml"
    state_path = tmp_path / "state.db"
    audit_path = tmp_path / "audit.db"
    cfg_path.write_text(
        f"""
runtime:
  audit_db_path: {audit_path.as_posix()}
  state_db_path: {state_path.as_posix()}
"""
    )

    first = Guard.from_config(cfg_path)
    first._id_store.bump("u1")
    first._id_store.set_monitored("u1", requests=8, multiplier=1.4)
    first.checkpoint()

    guard = Guard.from_config(cfg_path)

    async def run():
        await guard.startbgtasks()
        try:
            assert guard._id_store.get("u1").seen == 1
            assert guard._id_store.get("u1").monitored_remaining == 8
            assert guard._id_store.get("u1").monitored_multiplier == 1.4
            assert guard._bg_task is not None
        finally:
            await guard.shutdown()

    asyncio.run(run())


def test_guard_check_uses_route_cfg():
    guard = Guard()

    async def run():
        gate, event = await guard.check(
            "u1",
            payload="select * from users where id = '' or 1=1",
            context={"path": "/sdk", "route_cfg": {"trackB": False, "sensitivity": "critical"}},
        )
        assert gate.passed is True
        assert event is None

    asyncio.run(run())


def test_guard_check_sync_returns_event():
    guard = Guard()
    gate, event = guard.check_sync("u2", payload="hello")
    assert gate.passed is True
    assert event is not None


def test_guard_check_detects_shell_probe_via_pipe():
    guard = Guard()
    gate, event = guard.check_sync("u3", payload="search | bash")
    assert gate.passed is True
    assert event is not None
    assert event.score > 0.0


def test_route_decorators_preserve_sync_handler_shape():
    guard = Guard.__new__(Guard)
    guard.policies = dict(BUILTIN_POLICIES)

    def handler():
        return "ok"

    decorated = [
        guard.exempt()(handler),
        guard.protect()(handler),
        guard.policy("admin")(handler),
    ]

    for wrapped in decorated:
        assert inspect.iscoroutinefunction(wrapped) is False
        assert wrapped() == "ok"


def test_route_decorators_preserve_async_handler_shape():
    guard = Guard.__new__(Guard)
    guard.policies = dict(BUILTIN_POLICIES)

    async def handler():
        return "ok"

    decorated = [
        guard.exempt()(handler),
        guard.protect()(handler),
        guard.policy("admin")(handler),
    ]

    async def run():
        for wrapped in decorated:
            assert inspect.iscoroutinefunction(wrapped) is True
            assert await wrapped() == "ok"

    asyncio.run(run())
