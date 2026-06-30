# Route Verification

Verified manually against a local Flask server started with `python app.py`.

## 1. Health check

```bash
curl http://127.0.0.1:5000/
```

Expected:
- HTTP 200
- `{"message": "Flask demo is running.", "ok": true}`

## 2. Public route

```bash
curl http://127.0.0.1:5000/public/
```

Expected:
- HTTP 200
- `{"message": "This route is exempt from Adiuvare inspection.", "route": "public"}`

## 3. Protected route

```bash
curl http://127.0.0.1:5000/protected/
```

Expected:
- HTTP 200
- `{"message": "This stricter route passed Adiuvare inspection.", "route": "protected", "score": <float>, "verdict": "allow"}`

## 4. Review route — benign payload

```bash
curl -X POST http://127.0.0.1:5000/review/ \
  -H "Content-Type: application/json" \
  -d '{"message": "normal search text"}'
```

Expected:
- HTTP 200
- `{"message": "Payload review route reached the Flask view.", "received": {"message": "normal search text"}, "route": "review", "score": <float>, "verdict": "allow"}`

## 5. Review route — injection probe

```bash
curl -X POST http://127.0.0.1:5000/review/ \
  -H "Content-Type: application/json" \
  -d '{"message": "'\'' OR '\''1'\''='\''1"}'
```

Expected:
- HTTP 200 or 429 depending on score
- Verdict of `flag` or `throttle`

## 6. Hard-stop route — malicious payload

```bash
curl -X POST http://127.0.0.1:5000/hard-stop/ \
  -H "Content-Type: application/json" \
  -d '{"comment": "<script>alert(1)</script> UNION SELECT password FROM users"}'
```

Expected:
- HTTP 200 or 403 depending on score
- Verdict of `flag` or `block`

## 7. Auth login — @guard.policy("auth") decorator

```bash
curl -X POST http://127.0.0.1:5000/auth/login/ \
  -H "Content-Type: application/json" \
  -d '{"username": "alice", "password": "secret"}'
```

Expected:
- HTTP 200
- `{"route": "auth-login", "score": <float>, "user": "alice", "verdict": "allow"}`

## 8. Admin action — @guard.protect() decorator

```bash
curl -X POST http://127.0.0.1:5000/admin/action/ \
  -H "Content-Type: application/json" \
  -d '{"action": "delete_user", "target": "user:99"}'
```

Expected:
- HTTP 200
- `{"accepted": true, "action": "delete_user", "route": "admin-action", "score": <float>, "verdict": "allow"}`
