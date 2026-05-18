# Django

Django has a smaller integration than FastAPI or Flask, but it still gives you
the same core request path: fast gate, scored inspection, route-aware config,
and direct block or throttle outcomes.

Use the explicit Django attach path here. `Guard.auto(...)` is not the right
shortcut for Django at the moment.

## Working example

A maintained Django demo is available here:

```text
examples/multi-framework-demo/django_demo/
```

This is a real Django app you can run locally. It is useful if you want to see
how Adiuvare is wired into Django end-to-end, not just read API-level docs.

The demo covers:

- public/exempt route
- protected route with verdict and score in the response
- scored review route that reads a JSON body
- suspicious payload route that demonstrates flagging
- route-level `guard.configure_routes(...)` usage
- request and output verification using curl

To run it:

```bash
cd examples/multi-framework-demo/django_demo
python -m pip install -r requirements.txt
python manage.py check
python manage.py runserver 127.0.0.1:8000
```

The demo README and `ROUTE_VERIFICATION.md` have full curl commands and
expected outputs for every route.

## Quick example

```python
from adiuvare import Guard
from adiuvare.integrations.django import AdiuvareMiddleware

guard = Guard.from_config("adiuvare.yaml")


def adiuvare_middleware(get_response):
    return AdiuvareMiddleware(get_response, guard)
```

Add that wrapper to your Django middleware stack where you want request
inspection to happen.

```python
# settings.py
MIDDLEWARE = [
    "myapp.middleware.adiuvare_middleware",
]
```

## What the adapter reads

For each request, the Django adapter pulls:

- request body text
- `QUERY_STRING`
- request headers
- `REMOTE_ADDR`
- the path as the route lookup key

Then it:

1. builds a `RequestContext`
2. applies `trackA`
3. runs `trackB`
4. either returns a small direct response or continues to the view

Blocked response shape:

```text
status_code: 403
data: {"detail": "blocked"}
```

Throttled response shape:

```text
status_code: 429
data: {"detail": "throttled"}
```

## Route config

The cleanest current path in Django is programmatic route config.

```python
guard.configure_routes(
    {
        "/health": {"exempt": True},
        "/public/": {"exempt": True},
        "/admin/login": {
            "policy": "admin",
            "sensitivity": "critical",
            "trackB": True,
        },
        "/search": {
            "policy": "search",
            "sensitivity": "internal",
            "trackB": True,
        },
    }
)
```

That keeps route posture easy to reason about even when your Django URL and
view shape does not make decorators the best control point.

## Accessing the Adiuvare event in a view

After inspection, the middleware attaches the event to the request object:

```python
def my_view(request):
    event = getattr(request, "adiuvare_event", None)
    return JsonResponse(
        {
            "verdict": getattr(event, "verdict", None),
            "score": getattr(event, "score", None),
        }
    )
```

## Query and body scanning

Like the other adapters, Django combines body text and query-string text into
one payload context. That means a hostile query string can influence the same
payload scoring path as a hostile POST body.

## Operator flow

```bash
adv status
adv logs --tail 20
adv
```

Typical connected status:

```text
config: /my-api/adiuvare.yaml
runtime: connected
backend: sqlite
framework: django
instances: single
observe_only: False
ai_mode: off
banned_ips: 0
recent_events: 3
```

## Current boundaries

Compared with FastAPI and Flask, the Django integration is:

- smaller
- more path-config oriented
- less decorator-driven

That does not make it unusable. It just means the cleanest Django story today
is middleware attach, programmatic route config, and CLI or TUI for operator
visibility.

## Related

- [Working demo](../../examples/multi-framework-demo/django_demo/README.md)
- [Route verification](../../examples/multi-framework-demo/django_demo/ROUTE_VERIFICATION.md)
- [Configuration](../configuration.md)
- [Route policies](../extending/route-policies.md)
- [Guard API](../api/guard.md)
