# Django Demo Route Verification

This file records route-behavior proof for the maintained Django demo.

The server was started with:

```bash
cd examples/multi-framework-demo/django_demo
python manage.py runserver 127.0.0.1:8000
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
Content-Type: application/json
```

```json
{"route": "public", "message": "This route is exempt from Adiuvare inspection."}
```

**Result:** The public route is exempt. The Django view is reached without any
Adiuvare scoring. `request.adiuvare_event` is not set.

---

## 2. Protected route — inspected and allowed

Command:

```bash
curl -i http://127.0.0.1:8000/protected/
```

Observed response:

```
HTTP/1.1 200 OK
Content-Type: application/json
```

```json
{
  "route": "protected",
  "message": "This stricter route passed Adiuvare inspection.",
  "verdict": "allow",
  "score": 0.09487499999999999
}
```

**Result:** The protected route is inspected by Adiuvare with `policy: admin`
and `sensitivity: critical`. The request scores below the flag threshold, so
the verdict is `allow` and the request reaches the Django view. The view reads
`verdict` and `score` from `request.adiuvare_event`.

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
Content-Type: application/json
```

```json
{
  "route": "review",
  "message": "Payload review route reached the Django view.",
  "received": {"message": "normal search text"},
  "verdict": "allow"
}
```

**Result:** The review route reads the JSON request body and passes it through
Adiuvare scoring. A clean payload scores below the flag threshold. The view is
reached, the received payload is echoed back, and the verdict is `allow`.

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
Content-Type: application/json
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

**Result:** The suspicious payload (combined XSS + SQL injection pattern) is
detected and scored at `0.4379375`, which is above the `flag` threshold
(`0.25`) but below the `block` threshold (`0.80`). Adiuvare flags the request.
Because the demo uses `observe_only: false` and the score is below `block`,
the view is still reached and echoes back the received payload with the
`flag` verdict.

To force a block, raise the payload weight or lower `thresholds.block` in
`adiuvare.yaml` and rerun the command.

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

## Summary

| Route | Method | Payload | Verdict | Score | HTTP status |
|---|---|---|---|---|---|
| `/public/` | GET | — | exempt | — | 200 |
| `/protected/` | GET | — | allow | 0.0949 | 200 |
| `/review/` | POST | normal text | allow | — | 200 |
| `/hard-stop/` | POST | XSS + SQLi | flag | 0.4379 | 200 |
