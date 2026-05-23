# Adiuvare FastAPI Demo

This is a maintained FastAPI example showing how to use Adiuvare inside a real
FastAPI app. It is intended as a practical reference for users who want to
understand how to attach Adiuvare to FastAPI through middleware, configure
route-level policies, and verify behavior end-to-end.

The [central docs page](../../../docs/integrations/fastapi.md) links here.

## What this demo covers

| Route | Method | Purpose | Expected behavior |
|---|---|---|---|
| `/` | GET | Health check | Exempt — basic liveness check |
| `/public/` | GET | Public route | Exempt from Adiuvare inspection |
| `/protected/` | GET | Protected route | Inspected and allowed; verdict + score in response |
| `/review/` | POST | Payload review route | JSON body read and scored; result in response |
| `/hard-stop/` | POST | Suspicious payload route | Demonstrates flagged malicious-looking input |
| `/api/v1/explicit-exempt/` | GET | Per-endpoint control | Explicit override using inline `@guard.exempt()` decorator |
| `/api/v1/advanced-policy/` | POST | Self-described signal | Business rules alter active tracking wrapper variables |
| `/api/v1/global-policy-override/` | GET | Policy override | Global policy overridden with inline `@guard.policy("admin")` |
| `/api/v1/global-protect-override/` | GET | Protect override | Global config overridden with inline `@guard.protect(sensitivity="critical")` |


## Setup

From the FastAPI demo folder:

```bash
cd examples/multi-framework-demo/fastapi_demo
python -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
```

On Windows PowerShell:

```powershell
cd examples/multi-framework-demo/fastapi_demo
python -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
```

## Start the server

```bash
python main.py
```

## Route behavior verification

Run these commands while the server is running at `127.0.0.1:8000`.

### 1. Public route — exempt from inspection

```bash
curl -i http://127.0.0.1:8000/public/
```

Expected response body:

```json
{"route": "public", "message": "This route is exempt from Adiuvare inspection."}
```

The public route is exempt. The FastAPI path operation function is reached without any Adiuvare scoring. `request.state.adiuvare_event` is not set.

### 2. Protected route — inspected and allowed

```bash
curl -i http://127.0.0.1:8000/protected/
```

Expected response body:

```json
{
  "route": "protected",
  "message": "This stricter route passed Adiuvare inspection.",
  "verdict": "allow",
  "score": <float>
}
```

The protected route is inspected by Adiuvare with `policy: admin` and `sensitivity: critical`. The request scores below the flag threshold, returning `allow`. The view extracts `verdict` and `score` from `request.state.adiuvare_event`.

### 3. Review route — normal JSON payload scored

```bash
curl -i -X POST http://127.0.0.1:8000/review/ \
  -H "Content-Type: application/json" \
  -d '{"message":"normal search text"}'
```

Expected response body:

```json
{
  "route": "review",
  "message": "Payload review route reached the FastAPI view.",
  "received": {"message": "normal search text"},
  "verdict": "allow"
}
```

The review route processes the JSON payload. A benign payload scores below the evaluation threshold, resulting in an `allow` verdict.

### 4. Hard-stop route — suspicious SQLi/XSS payload flagged

```bash
curl -i -X POST http://127.0.0.1:8000/hard-stop/ \
  -H "Content-Type: application/json" \
  -d '{"comment":"<script>alert(1)</script> UNION SELECT password FROM users"}'
```

Expected response body:

```json
{
  "route": "hard-stop",
  "message": "If Adiuvare allows the request, this fallback response is returned.",
  "received": {"comment": "<script>alert(1)</script> UNION SELECT password FROM users"},
  "verdict": "flag",
  "score": <float>
}
```

The malicious payload triggers elevated signal anomalies, scoring above the `flag` limit (0.25) but below the `block` threshold (0.80). The runtime assigns a `flag` status to the event context, which the view then returns.

### 5. Explicit Exempt Route (Per-Endpoint Override):

```bash
curl -i http://127.0.0.1:8000/api/v1/explicit-exempt/
```

Expected Response Body:

```json
{"route":"explicit-exempt","message":"Bypassed via direct per-endpoint decorator."}
```

The `@guard.exempt()` decorator explicitly exempts the endpoint from Adiuvare inspection.

### 6. Advanced Policy Route (Self-Described Signals):

```bash
curl -i -X POST http://127.0.0.1:8000/api/v1/advanced-policy/ \
  -H "Content-Type: application/json" \
  -d '{"data_stream": "SYSTEM_OVERRIDE_CALL", "client_entropy": 0.98}'
```

Expected Response Body:
```json
{
  "route": "advanced-payload-review",
  "self_described_internal_risk": <float>,
  "final_adiuvare_verdict": "flag",
  "final_adiuvare_score": <float>
}
```

The view evaluates custom rules against the payload and manually updates the `request.state.adiuvare_event` to reflect a flagged state.

### 7. Global Policy Override

```bash
curl -i http://127.0.0.1:8000/api/v1/global-policy-override/
```

Expected Response Body:

```json
{
  "route": "global-policy-override",
  "message": "Overrode global policy using @guard.policy decorator.",
  "verdict": "allow",
  "score": <float>
}
```

The `@guard.policy("admin", ...)` decorator overrides the global configuration, enforcing the `admin` policy and `critical` sensitivity.

### 8. Global Protect Override

```bash
curl -i http://127.0.0.1:8000/api/v1/global-protect-override/
```

Expected Response Body:

```json
{
  "route": "global-protect-override",
  "message": "Overrode global protect rule using @guard.protect decorator.",
  "verdict": "allow",
  "score": <float>
}
```

The `@guard.protect(sensitivity="critical", ...)` decorator overrides the global configuration, elevating sensitivity to `critical`.

## Config note

The demo uses:

```yaml
ai:
  enabled: false
  mode: "off"
```

The quotes around `"off"` are intentional. Without them, YAML parsers read
`off` as boolean `false`, which breaks mode comparison.

## Inspect the operator tooling

Once the server is running, you can use the `adv` CLI in a second terminal:

```bash
adv status
adv logs --tail 10
```

## Route verification record

See [ROUTE_VERIFICATION.md](ROUTE_VERIFICATION.md) for recorded curl commands
and observed outputs.
