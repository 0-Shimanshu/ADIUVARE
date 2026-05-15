<p align="center">
  <img src="docs/assets/adiuvare-logo.png" alt="Adiuvare logo" width="520" />
</p>

<h1 align="center">Adiuvare</h1>

<p align="center">
  Score and stop risky API requests before they reach your FastAPI, Flask, or Django handlers.
</p>

<p align="center">
  Stateful request inspection, adaptive scoring, runtime controls, and local audit visibility - without shipping traffic into a separate platform first.
</p>

<p align="center">
  <img src="https://img.shields.io/badge/python-3.11%2B-blue.svg" alt="Python 3.11+" />
  <img src="https://img.shields.io/badge/frameworks-fastapi%20%7C%20flask%20%7C%20django-blue.svg" alt="FastAPI Flask Django" />
  <img src="https://img.shields.io/badge/license-Apache%202.0-green.svg" alt="Apache 2.0" />
</p>

Adiuvare is an in-process security layer for Python APIs. It sits inside your
app, inspects requests before your handlers run, and combines fast hard checks
with a softer scored review pipeline.

That lets you reject obviously hostile traffic early, keep inspecting the
requests that still pass, and leave a local audit trail behind every decision.
The same runtime can then be inspected locally through the `adv` CLI and the
 TUI.

It is a good fit when you want middleware-level protection, request scoring,
operator controls, and runtime visibility in one place, with SQLite by default
and Redis available when you need a different backend.

## What problem it solves

Most teams start with request filters that look simple and feel reasonable:

```python
if "<script>" in body:
    block()

if requests_per_minute > 100:
    block()
```

That approach breaks down quickly.

- A legitimate request can get blocked just because it contains suspicious text.
- Slight formatting changes can slip past brittle pattern checks.
- A trusted identity and a brand-new identity get treated the same way if the
  current request looks similar.

Adiuvare is built around a different idea: score risk, do not just match a
rule.

## Risk scoring, not rule filters

Instead of reacting to one signal in isolation, Adiuvare combines multiple
signals into a running risk score.

That score is built through a fast hard gate and a softer scored pipeline.

- `trackA` handles obvious blocks, allowlists, bans, and early exits.
- `trackB` scores the requests that still pass using payload, behavior,
  identity, context, IP reputation, and optional AI review.

That gives you proportional decisions instead of one hard reaction to every
signal.

- A slightly unusual request can be flagged instead of blocked.
- A monitored identity can be kept under tighter watch for the next few
  requests instead of being treated as permanently bad.
- A clearly hostile request can still be blocked quickly.

Every decision also leaves a local audit trail behind it, which is what makes
the CLI and TUI useful instead of decorative.

## Installation

Adiuvare is installable from source today. Install it into the same virtual
environment your app uses.

```bash
python -m pip install .
```

With the TUI:

```bash
python -m pip install ".[tui]"
```

With Redis support:

```bash
python -m pip install ".[redis]"
```

With both:

```bash
python -m pip install ".[tui,redis]"
```

After install, the `adv` command is available in that environment.

```bash
adv status
```

```text
config: H:\my-api\adiuvare.yaml
runtime: offline
framework: fastapi
instances: single
observe_only: False
ai_mode: off
audit_db: .adiuvare/audit.db
```

If you are evaluating the source tree without installing it yet, you can still
run `python -m adiuvare.cli status` or `python -m adiuvare.cli init --no-tui` from the repository
root.

More detail: [docs/installation.md](docs/installation.md)

## License

Adiuvare is released under the Apache License 2.0.

See [LICENSE](LICENSE) for details.

## Quick start

Generate a config:

```bash
adv init --no-tui
```

Then attach the guard to your app:

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

Check the runtime:

```bash
adv status
adv logs --tail 5
```

Open the TUI:

```bash
adv
```

## What it looks like

<p align="center">
  <img src="docs/assets/tui/events.png" alt="Adiuvare monitor screen showing recent requests, runtime status, and signal pressure" width="900" />
</p>

The runtime can be inspected locally through the built-in TUI.

Current screens include:

- Monitor
- Events
- Config
- Signals
- AI
- Audit
- Changes

The full operator walkthrough lives in [docs/operator/tui.md](docs/operator/tui.md).

## Common usage

Protect higher-risk routes:

```python
@app.post("/payments/charge")
@guard.policy("payment")
async def charge():
    return {"ok": True}


@app.get("/products")
@guard.policy("public_search", ai_mode="assist")
async def products():
    return {"ok": True}
```

Or do a quick manual check in code before wiring a full integration:

```python
gate, event = guard.check_sync(
    identity="user:4821",
    payload="q=<script>alert(1)</script>",
    context={"path": "/search", "method": "GET"},
)
```

Use the CLI for quick checks:

```bash
adv logs --tail 3
adv report
adv ban-ip 203.0.113.4
adv unban-ip 203.0.113.4
```

```text
allow    user:4821 /api/products
flag     api:key-9f3a /api/search
throttle user:3141 /api/comments
```

## How it works

```text
incoming request
  -> trackA fast gate
  -> trackB signal scoring
  -> verdict: allow | flag | throttle | block
  -> audit row + runtime visibility
```

The flow is simple on purpose. Adiuvare is trying to help you decide what to do
with a request before your app spends more time on it.

## Configuration

Most runtime behavior can be adjusted through `adiuvare.yaml`.

```yaml
runtime:
  backend: sqlite
  observe_only: false

thresholds:
  flag: 0.25
  throttle: 0.55
  block: 0.80

weights:
  payload: 0.40
  behavior: 0.35
  identity: 0.25

ai:
  enabled: false
  mode: off
  model: llama3
  base_url: http://127.0.0.1:11434
```

| Key | Default | What it controls |
|---|---|---|
| `runtime.backend` | `sqlite` | Local storage backend. `redis` is supported too. |
| `runtime.observe_only` | `false` | Log decisions without enforcing them. |
| `thresholds.block` | `0.80` | Score at which requests are blocked. |
| `runtime.monitored_window` | `20` | How many requests a monitored identity stays elevated. |
| `runtime.monitored_multiplier` | `1.2` | Score multiplier for monitored identities. |
| `ai.mode` | `off` | `off`, `assist`, or `critical`. |
| `ai.timeout_secs` | `5.0` | Timeout for request-time AI calls. |

Full reference: [docs/configuration.md](docs/configuration.md)

## Current scope

Adiuvare is in a good place for:

- FastAPI, Flask, and Django adapters
- request payload, behavior, identity, context, and IP reputation scoring
- local audit history and operator actions
- Redis-backed single-runtime use
- bounded AI-assisted review and analysis

There are still edges around distributed shared state and disconnected TUI
semantics. Those are documented plainly in [docs/limitations.md](docs/limitations.md).

## Docs

- [Quickstart](docs/quickstart.md)
- [Configuration](docs/configuration.md)
- [CLI](docs/operator/cli.md)
- [TUI](docs/operator/tui.md)
- [AI](docs/ai.md)
- [Guard API](docs/api/guard.md)
- [FastAPI](docs/integrations/fastapi.md)
- [Flask](docs/integrations/flask.md)
- [Django](docs/integrations/django.md)
