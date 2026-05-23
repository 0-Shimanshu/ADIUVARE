import asyncio
import json
import sys
import tempfile
import types
from collections import defaultdict
from pathlib import Path

from adiuvare.core.models import AdiuvareEvent
from adiuvare.state.event_stream import EventStreamClient, RedisEventStream, UnixSocketEventStream


class _FakeBroker:
    def __init__(self) -> None:
        self.channels = defaultdict(list)
        self.lists = defaultdict(list)

    async def publish(self, channel: str, payload: str) -> None:
        for queue in list(self.channels[channel]):
            await queue.put({"type": "message", "data": payload})

    async def lpush(self, key: str, payload: str) -> None:
        self.lists[key].insert(0, payload)

    async def ltrim(self, key: str, low: int, high: int) -> None:
        self.lists[key] = self.lists[key][low : high + 1]

    async def lrange(self, key: str, low: int, high: int) -> list[str]:
        return list(self.lists[key][low : high + 1])


class _FakePubSub:
    def __init__(self, broker: _FakeBroker) -> None:
        self._broker = broker
        self._queue = asyncio.Queue()
        self._channels: list[str] = []

    async def subscribe(self, *channels: str) -> None:
        for channel in channels:
            self._broker.channels[channel].append(self._queue)
            self._channels.append(channel)

    async def listen(self):
        while True:
            yield await self._queue.get()

    async def aclose(self) -> None:
        for channel in self._channels:
            if self._queue in self._broker.channels[channel]:
                self._broker.channels[channel].remove(self._queue)
        self._channels.clear()


class _FakeRedisClient:
    def __init__(self, broker: _FakeBroker, seen: dict) -> None:
        self._broker = broker
        self._seen = seen

    async def publish(self, channel, payload):
        self._seen.setdefault("pub", []).append((channel, json.loads(payload)))
        await self._broker.publish(channel, payload)

    async def lpush(self, key, payload):
        self._seen.setdefault("lpush", []).append((key, json.loads(payload)))
        await self._broker.lpush(key, payload)

    async def ltrim(self, key, low, high):
        self._seen.setdefault("trim", []).append((key, low, high))
        await self._broker.ltrim(key, low, high)

    async def lrange(self, key, low, high):
        return await self._broker.lrange(key, low, high)

    def pubsub(self):
        return _FakePubSub(self._broker)

    async def aclose(self):
        self._seen["closed"] = self._seen.get("closed", 0) + 1


def _install_fake_redis(monkeypatch):
    seen = {}
    broker = _FakeBroker()
    redis_pkg = types.ModuleType("redis")
    redis_async = types.ModuleType("redis.asyncio")

    def from_url(url):
        seen.setdefault("urls", []).append(url)
        return _FakeRedisClient(broker, seen)

    redis_async.from_url = from_url
    redis_pkg.asyncio = redis_async
    monkeypatch.setitem(sys.modules, "redis", redis_pkg)
    monkeypatch.setitem(sys.modules, "redis.asyncio", redis_async)
    return seen


def test_stream_replays_recent_event_to_new_client(tmp_path):
    async def run():
        stream = UnixSocketEventStream(sock_path=tmp_path / "replay.sock")
        await stream.start()
        try:
            await stream.emit(
                AdiuvareEvent(
                    identity="u1",
                    endpoint="/login",
                    score=0.88,
                    verdict="block",
                    breakdown={"payload": 0.88},
                )
            )
            reader, writer = await stream.connect()
            try:
                line = await asyncio.wait_for(reader.readline(), timeout=0.5)
            finally:
                writer.close()
                await writer.wait_closed()

            data = json.loads(line.decode("utf-8"))
            assert data["identity"] == "u1"
            assert data["verdict"] == "block"
        finally:
            await stream.stop()

    asyncio.run(run())


def test_stream_broadcasts_live_event(tmp_path):
    async def run():
        stream = UnixSocketEventStream(sock_path=tmp_path / "live.sock")
        await stream.start()
        try:
            reader, writer = await stream.connect()
            try:
                await stream.emit(
                    AdiuvareEvent(
                        identity="u2",
                        endpoint="/pay",
                        score=0.42,
                        verdict="flag",
                        breakdown={"payload": 0.42},
                    )
                )
                line = await asyncio.wait_for(reader.readline(), timeout=0.5)
            finally:
                writer.close()
                await writer.wait_closed()

            data = json.loads(line.decode("utf-8"))
            assert data["endpoint"] == "/pay"
            assert data["verdict"] == "flag"
        finally:
            await stream.stop()

    asyncio.run(run())


def test_stream_stop_removes_socket_path(tmp_path):
    async def run():
        sock_path = tmp_path / "done.sock"
        stream = UnixSocketEventStream(sock_path=sock_path)
        await stream.start()
        assert sock_path.exists()
        await stream.stop()
        assert not sock_path.exists()

    asyncio.run(run())


def test_stream_command_handler_still_works(tmp_path):
    async def run():
        stream = UnixSocketEventStream(sock_path=tmp_path / "cmd.sock")

        async def fake_cmd(name: str, args: dict):
            return {"name": name, "args": args}

        stream.set_command_handler(fake_cmd)
        res = await stream.command("ping", {"ok": True})
        assert res == {"name": "ping", "args": {"ok": True}}

    asyncio.run(run())


def test_event_stream_client_subscribes_to_live_rows(tmp_path):
    async def run():
        stream = UnixSocketEventStream(sock_path=tmp_path / "sub.sock")
        await stream.start()
        try:
            client = EventStreamClient(stream.path)
            rows = []

            async def listen_once():
                async for row in client.subscribe():
                    rows.append(row)
                    break

            task = asyncio.create_task(listen_once())
            await asyncio.sleep(0.1)
            await stream.emit(
                AdiuvareEvent(
                    identity="u3",
                    endpoint="/sub",
                    score=0.77,
                    verdict="throttle",
                    breakdown={"payload": 0.77},
                )
            )
            await asyncio.wait_for(task, timeout=1.0)
            assert rows[0]["identity"] == "u3"
            assert rows[0]["verdict"] == "throttle"
        finally:
            await stream.stop()

    asyncio.run(run())


def test_event_stream_client_runs_remote_command(tmp_path):
    async def run():
        stream = UnixSocketEventStream(sock_path=tmp_path / "rpc.sock")

        async def fake_cmd(name: str, args: dict):
            return {"name": name, "args": args}

        stream.set_command_handler(fake_cmd)
        await stream.start()
        try:
            client = EventStreamClient(stream.path)
            res = await client.command("ping", {"ok": True})
            assert res == {"name": "ping", "args": {"ok": True}}
        finally:
            await stream.stop()

    asyncio.run(run())


def test_event_stream_client_fails_cleanly_before_start(tmp_path):
    async def run():
        client = EventStreamClient(tmp_path / "missing.sock")
        try:
            await client.command("ping", {"ok": True})
        except RuntimeError as exc:
            assert str(exc) == "stream_not_started"
        else:
            raise AssertionError("expected stream_not_started")

    asyncio.run(run())


def test_redis_stream_publishes_and_replays(monkeypatch):
    seen = _install_fake_redis(monkeypatch)

    async def run():
        stream = RedisEventStream(project="demo", redis_url="redis://127.0.0.1:6379/0")
        await stream.start()
        await stream.emit(
            AdiuvareEvent(
                identity="u9",
                endpoint="/search",
                score=0.61,
                verdict="throttle",
                breakdown={"payload": 0.61},
            )
        )
        await stream.stop()

    asyncio.run(run())

    assert seen["urls"][0] == "redis://127.0.0.1:6379/0"
    assert seen["pub"][0][0].startswith("adiuvare:events:demo-")
    assert seen["pub"][0][1]["identity"] == "u9"
    assert seen["lpush"][0][0].startswith("adiuvare:events:demo-")
    assert seen["lpush"][0][0].endswith(":replay")
    assert seen["trim"][0][1:] == (0, 99)
    assert seen["closed"] == 1


def test_redis_stream_command_handler_still_works(monkeypatch):
    _install_fake_redis(monkeypatch)

    async def run():
        stream = RedisEventStream(project="demo", redis_url="redis://127.0.0.1:6379/0")

        async def fake_cmd(name: str, args: dict):
            return {"name": name, "args": args}

        stream.set_command_handler(fake_cmd)
        res = await stream.command("ping", {"ok": True})
        assert res == {"name": "ping", "args": {"ok": True}}

    asyncio.run(run())


def test_event_stream_client_runs_redis_remote_command(monkeypatch):
    _install_fake_redis(monkeypatch)

    async def run():
        stream = RedisEventStream(project="demo", redis_url="redis://127.0.0.1:6379/0")

        async def fake_cmd(name: str, args: dict):
            return {"name": name, "args": args}

        stream.set_command_handler(fake_cmd)
        await stream.start()
        try:
            client = EventStreamClient(stream.path)
            res = await client.command("ping", {"ok": True})
            assert res == {"name": "ping", "args": {"ok": True}}
        finally:
            await stream.stop()

    asyncio.run(run())


def test_event_stream_client_subscribes_to_redis_rows(monkeypatch):
    _install_fake_redis(monkeypatch)

    async def run():
        stream = RedisEventStream(project="demo", redis_url="redis://127.0.0.1:6379/0")
        await stream.start()
        try:
            client = EventStreamClient(stream.path)
            rows = []

            async def listen_once():
                async for row in client.subscribe():
                    rows.append(row)
                    break

            task = asyncio.create_task(listen_once())
            await asyncio.sleep(0.05)
            await stream.emit(
                AdiuvareEvent(
                    identity="u4",
                    endpoint="/redis",
                    score=0.67,
                    verdict="flag",
                    breakdown={"payload": 0.67},
                )
            )
            await asyncio.wait_for(task, timeout=1.0)
            assert rows[0]["identity"] == "u4"
            assert rows[0]["endpoint"] == "/redis"
        finally:
            await stream.stop()

    asyncio.run(run())


def test_unix_event_stream_uses_tempfile_dir():
    stream = UnixSocketEventStream(name="test")
    assert Path(stream.path).parent == Path(tempfile.gettempdir())


def test_redis_event_stream_uses_tempfile_dir():
    stream = RedisEventStream(project="test", redis_url="redis://localhost")
    assert Path(stream.path).parent == Path(tempfile.gettempdir())