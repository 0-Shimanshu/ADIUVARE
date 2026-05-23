# Guard API

`Guard` is the main public entry point of the library. If you only learn one
Adiuvare object, make it this one.

## Quick example

```python
from fastapi import FastAPI

from adiuvare import Guard

app = FastAPI()

guard = Guard.from_config("adiuvare.yaml")
guard.use(app, framework="fastapi")


@app.get("/health")
@guard.exempt()
async def health():
    return {"ok": True}


@app.post("/admin/login")
@guard.policy("admin")
async def admin_login():
    return {"ok": True}
```

That is the normal flow: load config, attach the framework adapter, exempt the
tiny route, and give the higher-risk route a stricter posture.

## Guard()

```python
Guard(
    preset: str = "balanced",
    config_path: str | Path | None = None,
    soft_signals: list | None = None,
    hard_signals: list | None = None,
)
```

| param | description |
| --- | --- |
| `preset` | base preset before file config is merged |
| `config_path` | path to `adiuvare.yaml`; if omitted, config discovery is used |
| `soft_signals` | replace the default soft-signal list |
| `hard_signals` | add synchronous `trackA` hard checks |

Example:

```python
from adiuvare import Guard

guard = Guard(config_path="adiuvare.yaml")
```

With discovery:

```python
from adiuvare import Guard

guard = Guard()
print(guard.config.meta.framework)
print(guard.config.runtime.backend)
```

```text
fastapi
sqlite
```

## Guard.from_config()

```python
Guard.from_config(
    config_path: str | Path,
    preset: str = "balanced",
    soft_signals: list | None = None,
    hard_signals: list | None = None,
)
```

This is the normal file-based constructor most users should start with.

```python
from adiuvare import Guard

guard = Guard.from_config("adiuvare.yaml")
print(guard.config.runtime.backend)
```

```text
sqlite
```

## Guard.auto()

```python
Guard.auto(
    app: Any,
    preset: str = "balanced",
    config_path: str | Path | None = None,
    soft_signals: list | None = None,
    hard_signals: list | None = None,
)
```

This creates the `Guard` and attaches it in one step.

```python
from fastapi import FastAPI

from adiuvare import Guard

app = FastAPI()
guard = Guard.auto(app, config_path="adiuvare.yaml")
```

If `config_path` is omitted, it uses the same discovery rules as
`load_config()`.

`Guard.auto(...)` is the safe short path for:

- FastAPI
- Flask

For Django, prefer `Guard.from_config(...)` plus `guard.use(..., framework="django")`.
`Guard.auto(...)` does not currently do real Django detection.

## use()

```python
guard.use(app: Any, framework: str = "fastapi") -> None
```

Use this when you want the framework attach step to stay explicit.

You do not need to pass `framework="fastapi"` unless you want the call to stay
visually explicit. `fastapi` is the default.

Supported values today:

- `fastapi`
- `flask`
- `django`

```python
from fastapi import FastAPI

from adiuvare import Guard

app = FastAPI()
guard = Guard.from_config("adiuvare.yaml")
guard.use(app, framework="fastapi")
```

Passing an unsupported framework string raises `ValueError`.

## Route helpers

### policy()

```python
guard.policy(name: str, **overrides)
```

Built-in policy names:

- `payment`
- `auth`
- `admin`
- `search`

```python
@app.post("/payments/charge")
@guard.policy("payment")
async def charge():
    return {"ok": True}
```

Route decorators preserve the original handler shape. If the decorated handler
is synchronous, the wrapper is synchronous. If the handler is async, the wrapper
is async.

```python
@app.get("/health")
@guard.exempt()
def flask_health():
    return {"ok": True}


@app.post("/review")
@guard.protect(sensitivity="critical")
async def async_review():
    return {"ok": True}
```

### protect()

```python
guard.protect(
    sensitivity: str = "internal",
    ai_mode: str = "off",
    trackB: bool = True,
    sink_mode: str = "off",
)
```

Use this when you want the route posture spelled out directly.

```python
@app.post("/review")
@guard.protect(
    sensitivity="critical",
    ai_mode="assist",
    trackB=True,
    sink_mode="inline",
)
async def review():
    return {"ok": True}
```

### exempt()

```python
guard.exempt()
```

```python
@app.get("/health")
@guard.exempt()
async def health():
    return {"ok": True}
```

### configure_routes()

```python
guard.configure_routes(routes: dict[str, Any])
```

Use this when decorators are awkward or when you want route posture in one
shared table.

```python
guard.configure_routes(
    {
        "/admin/login": {"policy": "admin"},
        "/health": {"exempt": True},
        "/search": {"policy": "search"},
    }
)
```

## check()

```python
await guard.check(
    identity: str,
    payload: dict | str | None = None,
    context: dict[str, Any] | None = None,
)
```

This is the async manual inspection path for jobs, workers, tests, and internal
tools.

`identity` is the identity string used for rate and state tracking. `payload`
can be a `dict`, a `str`, or `None`. `context` can include keys such as `path`,
`endpoint`, `url`, `method`, `headers`, `ip`, `sensitivity`, and `route_cfg`.

It returns `(gate, event)`.

```python
gate, event = await guard.check(
    "worker:invoice",
    payload={"sql": "select * from users where id = '' or 1=1"},
    context={"path": "/jobs/invoice", "method": "INTERNAL"},
)

print(gate.passed)
print(event.verdict if event else None)
```

```text
True
throttle
```

## check_sync()

```python
guard.check_sync(
    identity: str,
    payload: dict | str | None = None,
    context: dict[str, Any] | None = None,
)
```

This is the synchronous wrapper around `check()`.

```python
gate, event = guard.check_sync(
    "cron:nightly",
    payload="hello world",
    context={"path": "/cron/nightly"},
)

print(gate.passed)
print(event.verdict if event else None)
```

```text
True
allow
```

## hooks

`guard.hooks` is the simplest way to react to runtime decisions without writing
your own stream client.

Observe scored events:

```python
@guard.hooks.on_event
def on_event(event):
    print(event.verdict, event.identity, event.endpoint)
```

```text
allow user:42 /health
```

Observe early gate blocks:

```python
@guard.hooks.on_block
def on_block(gate):
    print(gate.status_code, gate.block_reason)
```

```text
403 banned_ip
```

## whitelist

`guard.whitelist` exposes the whitelist store.

Common uses:

- add a trusted identity
- ban a hostile IP
- remove an IP ban

```python
guard.whitelist.add("trusted:worker")
guard.whitelist.ban_ip("203.0.113.4")
guard.whitelist.unban_ip("203.0.113.4")
```

## Advanced runtime methods

### startbgtasks()

```python
await guard.startbgtasks()
```

Starts state restore, stream start, and the checkpoint loop.

### ensure_started()

```python
await guard.ensure_started()
```

This is the lazy-start helper used when the host startup path did not start the
runtime first.

### shutdown()

```python
await guard.shutdown()
```

Stops background tasks, checkpoints state, and stops the stream.

### checkpoint()

```python
guard.checkpoint()
```

Persists identity and local operator state immediately.

### runtimesnapshot()

```python
snap = guard.runtimesnapshot()
print(snap["backend"])
print(snap["banned_ip_count"])
print(snap["monitored_identity_count"])
print(snap["recent_events"])
```

```text
sqlite
0
0
0
```

The snapshot also carries fields such as:

- `ai_mode`
- `observe_only`
- thresholds
- configurable weights
- route overview

## Related

- [Config API](config.md)
- [Models API](models.md)
- [Signals API](signals.md)
- [Custom signals](../extending/custom-signals.md)
