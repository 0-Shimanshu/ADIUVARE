# Adiuvare Django Demo

This is a maintained Django example showing how to use Adiuvare inside a real
Django app. It is intended as a practical reference for users who want to
understand how to attach Adiuvare to Django through middleware, configure
route-level policies, and verify behavior end-to-end.

The [central docs page](../../../docs/integrations/django.md) links here.

## What this demo covers

| Route | Method | Purpose | Expected behavior |
|---|---|---|---|
| `/` | GET | Health check | Exempt — basic liveness check |
| `/public/` | GET | Public route | Exempt from Adiuvare inspection |
| `/protected/` | GET | Protected route | Inspected and allowed; verdict + score in response |
| `/review/` | POST | Payload review route | JSON body read and scored; result in response |
| `/hard-stop/` | POST | Suspicious payload route | Demonstrates flagged malicious-looking input |

## Setup

From the Django demo folder:

```bash
cd examples/multi-framework-demo/django_demo
python -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
```

On Windows PowerShell:

```powershell
cd examples/multi-framework-demo/django_demo
python -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
```

## Run checks

```bash
python manage.py check
```

Expected output:

```text
System check identified no issues (0 silenced).
```

## Start the server

```bash
python manage.py runserver 127.0.0.1:8000
```

## How Adiuvare is wired into Django

### 1. Guard is created from config

In `django_demo/middleware.py`, a `Guard` is loaded from `adiuvare.yaml`:

```python
from pathlib import Path
from adiuvare import Guard
from adiuvare.integrations.django import AdiuvareMiddleware

BASE_DIR = Path(__file__).resolve().parent.parent

guard = Guard.from_config(BASE_DIR / "adiuvare.yaml")
```

### 2. Route behavior is configured

```python
guard.configure_routes(
    {
        "/": {"exempt": True},
        "/public/": {"exempt": True},
        "/protected/": {
            "policy": "admin",
            "sensitivity": "critical",
            "trackB": True,
        },
        "/review/": {
            "policy": "search",
            "sensitivity": "internal",
            "trackB": True,
        },
        "/hard-stop/": {
            "sensitivity": "critical",
            "trackB": True,
        },
    }
)
```

### 3. Guard is attached as Django middleware

```python
def adiuvare_middleware(get_response):
    base_middleware = AdiuvareMiddleware(get_response, guard)

    def middleware(request):
        response = base_middleware(request)
        return response

    return middleware
```

### 4. Middleware is registered in settings

```python
# django_demo/settings.py
MIDDLEWARE = [
    "django_demo.middleware.adiuvare_middleware",
]
```

### 5. The event is read in views

After inspection, `AdiuvareMiddleware` attaches the event to the request:

```python
def protected(request):
    event = getattr(request, "adiuvare_event", None)
    return JsonResponse(
        {
            "route": "protected",
            "message": "This stricter route passed Adiuvare inspection.",
            "verdict": getattr(event, "verdict", None),
            "score": getattr(event, "score", None),
        }
    )
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

This proves the route-level exemption works. The view is reached without any
Adiuvare scoring.

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
  "score": 0.09487499999999999
}
```

This proves the route is inspected and that the verdict and score reach the
Django view through `request.adiuvare_event`.

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
  "message": "Payload review route reached the Django view.",
  "received": {"message": "normal search text"},
  "verdict": "allow"
}
```

This proves JSON request bodies are read, passed through Adiuvare scoring, and
that clean payloads are allowed through to the view.

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
  "score": 0.4379375
}
```

This proves that a suspicious SQLi/XSS-style payload is detected and scored
above the flag threshold. Depending on configured thresholds, Adiuvare may
allow, flag, throttle, or block the request before the Django view handles it.

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

## Files to inspect

```text
adiuvare.yaml               — scoring thresholds, weights, runtime backend
django_demo/middleware.py   — Guard init, route config, middleware factory
django_demo/settings.py     — MIDDLEWARE list
django_demo/urls.py         — URL-to-view mapping
demo/views.py               — views that read request.adiuvare_event
```

## Route verification record

See [ROUTE_VERIFICATION.md](ROUTE_VERIFICATION.md) for recorded curl commands
and observed outputs.
