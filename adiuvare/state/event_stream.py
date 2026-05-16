import asyncio
import json
import os
import sys
import tempfile
import uuid
from collections import deque
from dataclasses import asdict, is_dataclass
from pathlib import Path
from typing import Any


def _event_data(event: Any) -> dict[str, Any]:
    if is_dataclass(event):
        return asdict(event)
    if isinstance(event, dict):
        return event
    return {"value": str(event)}


def _json_line(data: dict[str, Any]) -> bytes:
    return (json.dumps(data) + "\n").encode("utf-8")


def _json_text(data: Any) -> str:
    return json.dumps(_event_data(data))


def _load_json(raw: Any) -> Any:
    if isinstance(raw, bytes):
        raw = raw.decode("utf-8")
    return json.loads(str(raw))


async def _close_pubsub(pubsub: Any) -> None:
    if pubsub is None:
        return
    close = getattr(pubsub, "aclose", None) or getattr(pubsub, "close", None)
    if close is None:
        return
    out = close()
    if asyncio.iscoroutine(out):
        await out


async def _pubsub_rows(pubsub: Any):
    async for frame in pubsub.listen():
        if not isinstance(frame, dict) or frame.get("type") != "message":
            continue
        data = frame.get("data")
        if data is None:
            continue
        yield _load_json(data)


class UnixSocketEventStream:
    """Broadcast recent events and runtime commands over a local socket stream."""

    def __init__(
        self,
        name: str = "adiuvare",
        *,
        pid: int | None = None,
        sock_path: str | Path | None = None,
    ) -> None:
        self._kind = "unix" if hasattr(asyncio, "start_unix_server") else "tcp"
        if sock_path is None:
            base = Path(tempfile.gettempdir())
            tail = f"{name}.sock" if pid is None else f"{name}-{pid}.sock"
            self.path = str(base / tail)
        else:
            self.path = str(sock_path)
        self._recent = deque(maxlen=100)
        self._replay = deque(maxlen=100)
        self._clients: list[asyncio.StreamWriter] = []
        self._server = None
        self._cmd = None
        self._host = "127.0.0.1"
        self._port = 0

    async def start(self) -> None:
        """Start the local stream server and write a TCP marker when unix sockets are unavailable."""

        if self._server is not None:
            return

        path = Path(self.path)
        path.parent.mkdir(parents=True, exist_ok=True)
        if path.exists():
            path.unlink()

        if self._kind == "unix":
            self._server = await asyncio.start_unix_server(self._on_connect, self.path)
            return

        self._server = await asyncio.start_server(self._on_connect, self._host, 0)
        sock = self._server.sockets[0]
        self._port = int(sock.getsockname()[1])
        path.write_text(
            json.dumps({"mode": "tcp", "host": self._host, "port": self._port}),
            encoding="utf-8",
        )

    async def emit(self, event) -> None:
        self._recent.append(event)
        payload = self._payload(event)
        self._replay.append(payload)

        if not self._clients:
            return

        dead = []
        for writer in list(self._clients):
            try:
                writer.write(payload)
                await writer.drain()
            except (BrokenPipeError, ConnectionResetError):
                dead.append(writer)

        for writer in dead:
            if writer in self._clients:
                self._clients.remove(writer)

    def recent(self) -> list:
        return list(self._recent)

    def set_command_handler(self, handler) -> None:
        self._cmd = handler

    async def command(self, name: str, args: dict | None = None) -> dict:
        if self._cmd is None:
            raise RuntimeError("stream_command_unbound")
        return await self._cmd(name, args or {})

    async def connect(self):
        if self._kind == "unix":
            reader, writer = await asyncio.open_unix_connection(self.path)
        else:
            reader, writer = await asyncio.open_connection(self._host, self._port)
        writer.write(b'{"kind":"subscribe"}\n')
        await writer.drain()
        return reader, writer

    async def stop(self) -> None:
        for writer in list(self._clients):
            writer.close()
            try:
                await writer.wait_closed()
            except Exception:
                pass
        self._clients.clear()

        if self._server is not None:
            self._server.close()
            await self._server.wait_closed()
            self._server = None

        path = Path(self.path)
        if path.exists():
            path.unlink()

    async def _on_connect(
        self,
        reader: asyncio.StreamReader,
        writer: asyncio.StreamWriter,
    ) -> None:
        hello = await self._hello(reader)
        if hello.get("kind") == "command":
            await self._run_command(writer, hello)
            return

        self._clients.append(writer)
        try:
            for payload in self._replay:
                writer.write(payload)
            await writer.drain()
            await reader.read(1)
        except (BrokenPipeError, ConnectionResetError):
            pass
        finally:
            if writer in self._clients:
                self._clients.remove(writer)
            writer.close()
            try:
                await writer.wait_closed()
            except Exception:
                pass

    async def _hello(self, reader: asyncio.StreamReader) -> dict[str, Any]:
        try:
            line = await asyncio.wait_for(reader.readline(), timeout=0.05)
        except asyncio.TimeoutError:
            return {"kind": "subscribe"}

        if not line:
            return {"kind": "subscribe"}

        try:
            msg = json.loads(line.decode("utf-8"))
        except json.JSONDecodeError:
            return {"kind": "subscribe"}

        if isinstance(msg, dict):
            return msg
        return {"kind": "subscribe"}

    async def _run_command(self, writer: asyncio.StreamWriter, hello: dict[str, Any]) -> None:
        reply: dict[str, Any]
        if self._cmd is None:
            reply = {"ok": False, "error": "stream_command_unbound"}
        else:
            try:
                payload = await self._cmd(
                    str(hello.get("name", "")),
                    dict(hello.get("args") or {}),
                )
                reply = {"ok": True, "payload": payload}
            except Exception as exc:
                reply = {"ok": False, "error": str(exc)}

        writer.write((json.dumps(reply) + "\n").encode("utf-8"))
        await writer.drain()
        writer.close()
        try:
            await writer.wait_closed()
        except Exception:
            pass

    def _payload(self, event: Any) -> bytes:
        return _json_line(_event_data(event))


class RedisEventStream:
    """Mirror the local event stream contract on top of Redis pubsub and a replay list."""

    def __init__(self, project: str, redis_url: str) -> None:
        base = Path(tempfile.gettempdir())
        tail = f"{project}-{os.getpid()}.sock"
        self.path = str(base / tail)
        self._url = redis_url
        self._runtime = f"{project}-{os.getpid()}"
        self._events = f"adiuvare:events:{self._runtime}"
        self._replay_key = f"{self._events}:replay"
        self._cmds = f"adiuvare:cmd:{self._runtime}"
        self._client = None
        self._cmd_sub = None
        self._cmd_task: asyncio.Task | None = None
        self._cmd = None
        self._recent = deque(maxlen=100)
        self._replay = deque(maxlen=100)

    async def start(self) -> None:
        if self._client is not None:
            return

        mod = sys.modules.get("redis.asyncio")
        if mod is None:
            import redis.asyncio as mod

        self._client = mod.from_url(self._url)
        marker = Path(self.path)
        marker.parent.mkdir(parents=True, exist_ok=True)
        if marker.exists():
            marker.unlink()
        marker.write_text(
            json.dumps({"mode": "redis", "url": self._url, "runtime": self._runtime}),
            encoding="utf-8",
        )
        self._cmd_sub = self._client.pubsub()
        await self._cmd_sub.subscribe(self._cmds)
        self._cmd_task = asyncio.create_task(self._run_commands())

    async def emit(self, event) -> None:
        self._recent.append(event)
        payload = _json_text(event)
        self._replay.append(payload)

        if self._client is None:
            return

        await self._client.publish(self._events, payload)
        await self._client.lpush(self._replay_key, payload)
        await self._client.ltrim(self._replay_key, 0, 99)

    def recent(self) -> list:
        return list(self._recent)

    def set_command_handler(self, handler) -> None:
        self._cmd = handler

    async def command(self, name: str, args: dict | None = None) -> dict:
        if self._cmd is None:
            raise RuntimeError("stream_command_unbound")
        return await self._cmd(name, args or {})

    async def stop(self) -> None:
        if self._cmd_task is not None:
            self._cmd_task.cancel()
            try:
                await self._cmd_task
            except asyncio.CancelledError:
                pass
            self._cmd_task = None

        await _close_pubsub(self._cmd_sub)
        self._cmd_sub = None

        if self._client is not None:
            await self._client.aclose()
            self._client = None

        marker = Path(self.path)
        if marker.exists():
            marker.unlink()

    async def _run_commands(self) -> None:
        if self._client is None or self._cmd_sub is None:
            return

        try:
            async for frame in _pubsub_rows(self._cmd_sub):
                if not isinstance(frame, dict):
                    continue
                req_id = str(frame.get("request_id", "")).strip()
                if not req_id:
                    continue
                reply = await self._reply_frame(frame)
                await self._client.publish(self._reply_chan(req_id), json.dumps(reply))
        finally:
            await _close_pubsub(self._cmd_sub)
            self._cmd_sub = None

    async def _reply_frame(self, frame: dict[str, Any]) -> dict[str, Any]:
        if self._cmd is None:
            return {"ok": False, "error": "stream_command_unbound"}

        try:
            payload = await self._cmd(
                str(frame.get("name", "")),
                dict(frame.get("args") or {}),
            )
        except Exception as exc:
            return {"ok": False, "error": str(exc)}

        return {"ok": True, "payload": payload}

    def _reply_chan(self, req_id: str) -> str:
        return f"adiuvare:reply:{self._runtime}:{req_id}"


class EventStreamClient:
    """Talk to either the local socket stream or the Redis-backed runtime marker."""

    def __init__(self, path: str | Path | None) -> None:
        self.path = str(path) if path else None

    async def command(self, name: str, args: dict | None = None) -> dict[str, Any]:
        """Send one runtime command through whichever stream backend the marker points to."""

        meta = self._conn_meta()
        if isinstance(meta, dict) and meta.get("mode") == "redis":
            return await self._command_redis(meta, name, args)

        reader, writer = await self._open()
        try:
            frame = {"kind": "command", "name": name, "args": args or {}}
            writer.write((json.dumps(frame) + "\n").encode("utf-8"))
            await writer.drain()
            line = await asyncio.wait_for(reader.readline(), timeout=1.0)
            if not line:
                raise RuntimeError("stream_command_empty")
            reply = json.loads(line.decode("utf-8"))
            if not reply.get("ok"):
                raise RuntimeError(str(reply.get("error", "stream_command_failed")))
            return dict(reply.get("payload") or {})
        finally:
            writer.close()
            try:
                await writer.wait_closed()
            except Exception:
                pass

    async def subscribe(self):
        """Yield replay rows first, then continue with the live stream."""

        meta = self._conn_meta()
        if isinstance(meta, dict) and meta.get("mode") == "redis":
            async for row in self._subscribe_redis(meta):
                yield row
            return

        reader, writer = await self._open()
        try:
            writer.write(b'{"kind":"subscribe"}\n')
            await writer.drain()
            while True:
                line = await reader.readline()
                if not line:
                    break
                payload = json.loads(line.decode("utf-8"))
                if isinstance(payload, dict):
                    yield payload
        finally:
            writer.close()
            try:
                await writer.wait_closed()
            except Exception:
                pass

    async def _command_redis(
        self,
        meta: dict[str, Any],
        name: str,
        args: dict | None = None,
    ) -> dict[str, Any]:
        client = self._redis_client(meta)
        pubsub = client.pubsub()
        req_id = uuid.uuid4().hex
        reply_chan = f"adiuvare:reply:{meta['runtime']}:{req_id}"
        frame = {"request_id": req_id, "name": name, "args": args or {}}
        try:
            await pubsub.subscribe(reply_chan)
            await client.publish(f"adiuvare:cmd:{meta['runtime']}", json.dumps(frame))
            reply = await asyncio.wait_for(self._read_reply(pubsub), timeout=1.0)
        finally:
            await _close_pubsub(pubsub)
            await client.aclose()

        if not reply.get("ok"):
            raise RuntimeError(str(reply.get("error", "stream_command_failed")))
        return dict(reply.get("payload") or {})

    async def _subscribe_redis(self, meta: dict[str, Any]):
        client = self._redis_client(meta)
        pubsub = client.pubsub()
        replay_key = f"adiuvare:events:{meta['runtime']}:replay"
        event_chan = f"adiuvare:events:{meta['runtime']}"
        try:
            rows = await client.lrange(replay_key, 0, 99)
            for row in reversed(rows):
                data = _load_json(row)
                if isinstance(data, dict):
                    yield data

            await pubsub.subscribe(event_chan)
            async for row in _pubsub_rows(pubsub):
                if isinstance(row, dict):
                    yield row
        finally:
            await _close_pubsub(pubsub)
            await client.aclose()

    async def _read_reply(self, pubsub: Any) -> dict[str, Any]:
        async for reply in _pubsub_rows(pubsub):
            if isinstance(reply, dict):
                return reply
        raise RuntimeError("stream_command_empty")

    async def _open(self):
        meta = self._conn_meta()
        if isinstance(meta, dict) and meta.get("mode") == "redis":
            raise RuntimeError("stream_redis_uses_client")

        if not self.path:
            raise RuntimeError("stream_path_missing")

        path = Path(self.path)
        if isinstance(meta, dict) and meta.get("mode") == "tcp":
                return await asyncio.open_connection(
                    str(meta.get("host", "127.0.0.1")),
                    int(meta["port"]),
                )

        if not path.exists():
            raise RuntimeError("stream_not_started")
        return await asyncio.open_unix_connection(self.path)

    def _conn_meta(self) -> dict[str, Any] | None:
        if not self.path:
            return None

        path = Path(self.path)
        if not path.exists():
            return None

        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            return None

        if isinstance(data, dict):
            return data
        return None

    def _redis_client(self, meta: dict[str, Any]):
        mod = sys.modules.get("redis.asyncio")
        if mod is None:
            import redis.asyncio as mod
        return mod.from_url(str(meta["url"]))
