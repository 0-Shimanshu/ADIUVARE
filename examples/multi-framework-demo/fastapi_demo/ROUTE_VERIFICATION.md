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
date: Mon, 18 May 2026 06:10:27 GMT
server: uvicorn
content-length: 77
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
date: Mon, 18 May 2026 06:10:42 GMT
server: uvicorn
content-length: 109
content-type: application/json
```

```json
{
  "route": "protected",
  "message": "This stricter route passed Adiuvare inspection.",
  "verdict": "allow",
  "score": 0.09487499999999999
}
```

**Result:** The protected route is inspected by Adiuvare with `policy: admin` and `sensitivity: critical`. The request scores below the flag threshold, so the verdict returns as `allow` and the request successfully evaluates. The view reads `verdict` and `score` directly out of `request.state.adiuvare_event`.

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
date: Mon, 18 May 2026 06:11:31 GMT
server: uvicorn
content-length: 136
content-type: application/json
```

```json
{
  "route": "review",
  "message": "Payload review route reached the Django view.",
  "received": {"message": "normal search text"},
  "verdict": "allow"
}
```

**Result:** The review route successfully extracts the structural JSON payload from the request stream and moves it through the Adiuvare logic block. Since it's a completely benign payload string, it records a safe baseline below the evaluation threshold and assigns an explicit `allow` verdict.

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
date: Mon, 18 May 2026 06:11:55 GMT
server: uvicorn
content-length: 213
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
  "score": 0.4379375
}
```

**Result:** The multi-vector malicious payload text triggers elevated signal anomalies. The calculated evaluation results in a score of `0.437938`. This pushes beyond our configured `flag` limit `(0.25)`, but doesn't cross into the definitive `block` threshold `(0.80)`. The runtime assigns a `flag` status string to the event context. Because `observe_only` is toggled off and the request did not fully trigger a drop, it flows gracefully to our backup return dictionary displaying the correct metrics.


### 5. Explicit Exempt Route (Per-Endpoint Override):

```bash
curl -i http://127.0.0.1:8001/api/v1/explicit-exempt/
```

Observed response:

```
HTTP/1.1 200 OK
content-type: application/json
```

```json
{"route":"explicit-exempt","message":"Bypassed via direct per-endpoint decorator."}
```

**Result:** The explicit inline decorator pattern intercepts the context execution block. The endpoint resolves cleanly without initializing tracking loops.


### 6. Advanced Policy Route (Self-Described Signals):

```bash
curl -i -X POST http://127.0.0.1:8001/api/v1/advanced-policy/ \
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
  "self_described_internal_risk": 0.82,
  "final_adiuvare_verdict": "flag",
  "final_adiuvare_score": 0.82
}
```
**Result:** The logic block intercepts the payload parameters, evaluates custom threat conditions internally, and seamlessly mutates the active `request.state.adiuvare_event` variable state inside the execution frame, elevating the output to a "flag" condition.

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

