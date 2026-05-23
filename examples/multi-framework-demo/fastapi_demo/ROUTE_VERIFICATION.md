# FastAPI Demo Route Verification

This file records route-behavior proof for the maintained FastAPI demo.

The server was started with:

```bash
cd examples/multi-framework-demo/fastapi_demo
python main.py
```

---

## 1. Public route — exempt from Adiuvare inspection

Command:

```bash
curl -i http://127.0.0.1:8000/public/
```

Observed response:

```
HTTP/1.1 200 OK
content-type: application/json
```

```json
{"route": "public", "message": "This route is exempt from Adiuvare inspection."}
```

**Result:** The public route is exempt. The FastAPI path operation function is reached without any Adiuvare scoring. `request.state.adiuvare_event` is not populated.

---

## 2. Protected route — inspected and allowed

Command:

```bash
curl -i http://127.0.0.1:8000/protected/
```

Observed response:

```
HTTP/1.1 200 OK
content-type: application/json
```

```json
{
  "route": "protected",
  "message": "This stricter route passed Adiuvare inspection.",
  "verdict": "allow",
  "score": <float>
}
```

**Result:** The route is inspected with `policy: admin` and `sensitivity: critical`. The request scores below the flag threshold, returning `allow`. The view extracts `verdict` and `score` from `request.state.adiuvare_event`.

---

## 3. Review route — normal JSON payload scored

Command:

```bash
curl -i -X POST http://127.0.0.1:8000/review/ \
  -H "Content-Type: application/json" \
  -d '{"message":"normal search text"}'
```

Observed response:

```
HTTP/1.1 200 OK
content-type: application/json
```

```json
{
  "route": "review",
  "message": "Payload review route reached the FastAPI view.",
  "received": {"message": "normal search text"},
  "verdict": "allow"
}
```

**Result:** A benign payload scores below the evaluation threshold, resulting in an `allow` verdict.

---

## 4. Hard-stop route — suspicious SQLi/XSS payload flagged

Command:

```bash
curl -i -X POST http://127.0.0.1:8000/hard-stop/ \
  -H "Content-Type: application/json" \
  -d '{"comment":"<script>alert(1)</script> UNION SELECT password FROM users"}'
```

Observed response:

```
HTTP/1.1 200 OK
content-type: application/json
```

```json
{
  "route": "hard-stop",
  "message": "If Adiuvare allows the request, this fallback response is returned.",
  "received": {
    "comment": "<script>alert(1)</script> UNION SELECT password FROM users"
  },
  "verdict": "flag",
  "score": <float>
}
```

**Result:** The malicious payload scores above the `flag` limit (0.25) but below the `block` threshold (0.80). The runtime assigns a `flag` status to the event context, which the view returns.


### 5. Explicit Exempt Route (Per-Endpoint Override):

```bash
curl -i http://127.0.0.1:8000/api/v1/explicit-exempt/
```

Observed response:

```
HTTP/1.1 200 OK
content-type: application/json
```

```json
{"route":"explicit-exempt","message":"Bypassed via direct per-endpoint decorator."}
```

**Result:** The `@guard.exempt()` decorator explicitly exempts the endpoint from Adiuvare inspection.


### 6. Advanced Policy Route (Self-Described Signals):

```bash
curl -i -X POST http://127.0.0.1:8000/api/v1/advanced-policy/ \
  -H "Content-Type: application/json" \
  -d '{"data_stream": "CRITICAL: override_core_state", "client_entropy": 0.97}'
```

Observed response:

```
HTTP/1.1 200 OK
content-type: application/json
```

```json
{
  "route": "advanced-payload-review",
  "self_described_internal_risk": <float>,
  "final_adiuvare_verdict": "flag",
  "final_adiuvare_score": <float>
}
```
**Result:** The view evaluates custom rules against the payload and manually updates the `adiuvare_event` to reflect a flagged state.

---

### 7. Global Policy Override

Command:

```bash
curl -i http://127.0.0.1:8000/api/v1/global-policy-override/
```

Observed response:

```
HTTP/1.1 200 OK
content-type: application/json
```

```json
{
  "route": "global-policy-override",
  "message": "Overrode global policy using @guard.policy decorator.",
  "verdict": "allow",
  "score": <float>
}
```

**Result:** The `@guard.policy()` decorator overrides the global configuration, enforcing the `admin` policy and `critical` sensitivity.

---

### 8. Global Protect Override

Command:

```bash
curl -i http://127.0.0.1:8000/api/v1/global-protect-override/
```

Observed response:

```
HTTP/1.1 200 OK
content-type: application/json
```

```json
{
  "route": "global-protect-override",
  "message": "Overrode global protect rule using @guard.protect decorator.",
  "verdict": "allow",
  "score": <float>
}
```

**Result:** The `@guard.protect()` decorator overrides the global configuration, elevating sensitivity to `critical`.

---

## Thresholds in effect during this verification

From `adiuvare.yaml`:

```yaml
thresholds:
  flag: 0.25
  throttle: 0.55
  block: 0.80

weights:
  payload: 0.40
  behavior: 0.35
  identity: 0.25
```

---

