# Quickstart

This gets Adiuvare attached to a FastAPI app quickly and shows where the first
results show up. If you just want to prove "this works in a real app," this is
the shortest path.

## 1. Install

Adiuvare is installable from source. Install it directly from GitHub into your virtual environment::

```bash
python -m pip install "git+https://github.com/0-Shimanshu/ADIUVARE.git"
```

If you also want the TUI:

```bash
python -m pip install "adiuvare[tui] @ git+https://github.com/0-Shimanshu/ADIUVARE.git"
```

If you want the Redis backend too:

```bash
python -m pip install "adiuvare[redis] @ git+https://github.com/0-Shimanshu/ADIUVARE.git"
```

## 2. Create `adiuvare.yaml`

Use the plain terminal init flow:

```bash
adv init --no-tui
```

Typical setup session:

```text
Framework? [fastapi / flask / django] (fastapi):
Instances? [single / multi] (single):
Strictness? [public / internal / critical] (internal):
Mode? [observe / enforce] (observe):
Enable AI? [yes / no] (no):
AI model (llama3):
AI API key (leave blank if none):
Save path [adiuvare.yaml] (adiuvare.yaml):
wrote config: adiuvare.yaml
```

If you installed the TUI extra, you can use the setup wizard instead:

```bash
adv init
```

## 3. Check the starter file

A normal starter file looks like this:

```yaml
thresholds:
  flag: 0.45
  throttle: 0.6
  block: 0.8

weights:
  payload: 0.4
  behavior: 0.25
  identity: 0.2

runtime:
  backend: sqlite
  observe_only: false

ai:
  enabled: false
  mode: off
  model: llama3
  base_url: http://127.0.0.1:11434

meta:
  framework: fastapi
  instances: single
  strictness: internal
```

You do not need to tune everything yet. The generated file already gives you a
working starting point.

## 4. Attach Adiuvare to FastAPI

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

If you prefer the one-liner:

```python
guard = Guard.auto(app, config_path="adiuvare.yaml")
```

That shortcut is fine for FastAPI. Flask can use it too. Django should stay on
the explicit `guard.use(..., framework="django")` path for now.

## 5. Run the app

Use your normal ASGI server:

```bash
uvicorn main:app --reload
```

Once the app is running, Adiuvare starts writing audit rows and exposing the
runtime surface used by the CLI and TUI.

## 6. Send a few requests

Clean request:

```bash
curl http://127.0.0.1:8000/health
```

```text
{"ok":true}
```

Stricter route:

```bash
curl -X POST http://127.0.0.1:8000/admin/login
```

A harmless call still looks normal:

```text
{"ok":true}
```

If a request hits a stronger verdict, you may see:

```text
{"detail":"throttled"}
```

or:

```text
{"detail":"blocked"}
```

## 7. Inspect what happened

Quick runtime check:

```bash
adv status
```

Typical output once the app is live:

```text
config: H:\ADIUVARE\adiuvare.yaml
runtime: connected
socket: C:\Users\me\AppData\Local\Temp\adiuvare.sock
backend: sqlite
framework: fastapi
instances: single
observe_only: False
ai_mode: off
banned_ips: 0
recent_events: 2
```

Recent audit rows:

```bash
adv logs --tail 10
```

```text
allow    user:1 /health
allow    user:1 /admin/login
```

Small local summary:

```bash
adv report
```

```text
# Adiuvare report

- rows: 2
- allow: 2
- flag: 0
- throttle: 0
- block: 0

## busiest identities
- user:1: 2
```

If the TUI extra is installed:

```bash
adv
```

## `trackA` and `trackB`

`trackA` is the fast gate. It handles banned IPs, hard-signal hits, and other
early deny or hold cases.

`trackB` is the richer scoring path. It looks at payload, behavior, identity,
context, IP hints, and optional AI. That is where `allow`, `flag`, `throttle`,
and `block` usually get shaped.

## Related

- [Configuration](configuration.md)
- [FastAPI](integrations/fastapi.md)
- [CLI](operator/cli.md)
- [TUI](operator/tui.md)
