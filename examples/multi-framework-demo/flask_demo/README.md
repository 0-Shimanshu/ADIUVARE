# Adiuvare Flask Demo

This is a maintained Flask example showing how to use Adiuvare inside a real
Flask app. It is intended as a practical reference for users who want to
understand how to attach Adiuvare to Flask, configure route-level policies, and
verify behavior end-to-end.

The central Flask integration documentation links here.

## What this demo covers

| Route | Method | Guard posture | Purpose |
| --- | --- | --- | --- |
| `/` | GET | `configure_routes` exempt | Health check |
| `/public/` | GET | `configure_routes` exempt | Public route, never scored |
| `/protected/` | GET | `configure_routes` admin policy | Stricter protected route |
| `/review/` | POST | `configure_routes` search policy | Scored payload review |
| `/hard-stop/` | POST | `configure_routes` critical sensitivity | Hard stop / hold path |
| `/auth/login/` | POST | `@guard.policy("auth")` | Auth policy via decorator |
| `/admin/action/` | POST | `@guard.protect(sensitivity="critical", ai_mode="assist")` | Critical posture via decorator |

The demo shows both ways to attach guard posture: a shared `configure_routes`
table for most routes, and per-route `@guard.policy()` / `@guard.protect()`
decorators for routes where the posture needs to be explicit at the call site.

## Setup

```bash
cd examples/multi-framework-demo/flask_demo
python -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
```

On Windows PowerShell:

```powershell
cd examples/multi-framework-demo/flask_demo
python -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
```

## Start the server

```bash
python app.py
```

The server starts on `http://127.0.0.1:5000`.

## Try the routes

```bash
# 1. Health check — always exempt
curl http://127.0.0.1:5000/

# 2. Public route — exempt
curl http://127.0.0.1:5000/public/

# 3. Protected route — admin policy, critical sensitivity
curl http://127.0.0.1:5000/protected/

# 4. Clean search payload — expect allow
curl -X POST http://127.0.0.1:5000/review/ \
  -H "Content-Type: application/json" \
  -d '{"message": "normal search text"}'

# 5. Injection probe — expect flag or throttle
curl -X POST http://127.0.0.1:5000/review/ \
  -H "Content-Type: application/json" \
  -d '{"message": "'\'' OR '\''1'\''='\''1"}'

# 6. Hard-stop with malicious payload — expect flag or block
curl -X POST http://127.0.0.1:5000/hard-stop/ \
  -H "Content-Type: application/json" \
  -d '{"comment": "<script>alert(1)</script> UNION SELECT password FROM users"}'

# 7. Auth login — @guard.policy("auth") decorator
curl -X POST http://127.0.0.1:5000/auth/login/ \
  -H "Content-Type: application/json" \
  -d '{"username": "alice", "password": "secret"}'

# 8. Admin action — @guard.protect(sensitivity="critical") decorator
curl -X POST http://127.0.0.1:5000/admin/action/ \
  -H "Content-Type: application/json" \
  -d '{"action": "delete_user", "target": "user:99"}'
```

## Inspect the operator tooling

Once the server is running, use the `adv` CLI in a second terminal:

```bash
adv status
adv logs --tail 10
adv report
```

Open the full TUI (requires `pip install ".[tui]"`):

```bash
adv
```

## Route verification record

See [ROUTE_VERIFICATION.md](ROUTE_VERIFICATION.md) for recorded curl commands
and observed outputs.

## Config note

The demo uses:

```yaml
ai:
  enabled: false
  mode: "off"
```

The quotes around `"off"` are intentional. Without them, YAML parsers read
`off` as boolean `false`, which breaks mode comparison.
