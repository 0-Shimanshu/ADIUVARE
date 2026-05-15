# Adiuvare Django Demo

This is a small maintained Django example showing how to attach Adiuvare to a real Django app.

It demonstrates:

- a normal public route
- a stricter protected route
- a scored payload review route
- a harder stop/hold route

## Setup

From this folder:

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
```

On Windows PowerShell:

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
```

## Run

```bash
python manage.py runserver
```

The app starts at:

```txt
http://127.0.0.1:8000/
```

## Try the routes

Public route:

```bash
curl http://127.0.0.1:8000/public/
```

Protected route:

```bash
curl http://127.0.0.1:8000/protected/ \
  -H "x-user-id: demo-user"
```

Scored payload review route:

```bash
curl -X POST http://127.0.0.1:8000/review/ \
  -H "Content-Type: application/json" \
  -H "x-user-id: demo-user" \
  -d '{"message":"normal search text"}'
```

Hard stop / hold style route:

```bash
curl -X POST http://127.0.0.1:8000/hard-stop/ \
  -H "Content-Type: application/json" \
  -H "x-user-id: suspicious-user" \
  -d '{"comment":"<script>alert(1)</script> UNION SELECT password FROM users"}'
```

Depending on the configured scoring thresholds, Adiuvare may allow, flag, throttle, or block the request before the Django view handles it.

## Notes

This demo intentionally stays small. It is meant to show how Adiuvare can be wired into Django through middleware and route configuration without becoming a separate product.
