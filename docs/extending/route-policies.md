# Route Policies

Route policy is how you set posture per endpoint. It controls sensitivity, AI
mode, whether `trackB` runs, and how strict the SQL sink should be near
execution.

## Quick example

```python
from adiuvare import Guard

guard = Guard.from_config("adiuvare.yaml")
guard.configure_routes(
    {
        "/billing": {"ai_mode": "assist", "sink_mode": "inline"},
        "/health": {"exempt": True},
    }
)

print(guard.route_cfg["/billing"]["ai_mode"])
print(guard.route_cfg["/health"]["exempt"])
```

```text
assist
True
```

That is the whole idea: route config lets one endpoint stay lightweight while
another gets a stricter path.

## Built-in policies

You can use four built-in policy names today:

| policy | sensitivity | ai_mode | trackB | sink_mode |
| --- | --- | --- | --- | --- |
| `payment` | `critical` | `assist` | `True` | `inline` |
| `auth` | `critical` | `off` | `True` | `inline` |
| `admin` | `critical` | `critical` | `True` | `inline` |
| `search` | `public` | `off` | `True` | `off` |

Example:

```python
@app.post("/payments/charge")
@guard.policy("payment")
async def charge():
    return {"ok": True}
```

Use built-ins when you want readable app code and a small shared vocabulary for
common route families.

## protect()

Use `protect()` when you want the exact posture visible right on the route.

```python
@app.post("/review")
@guard.protect(
    sensitivity="critical",
    ai_mode="assist",
    trackB=True,
    sink_mode="inline",
)
async def review():
    return {"ok": True}
```

This is the better fit when the route is unusual or the built-in names are too
broad.

Decorator helpers do not change the route function's sync/async shape. A
normal synchronous Flask view remains synchronous, and an async FastAPI or Flask
view remains awaitable.

```python
@app.get("/health")
@guard.exempt()
def flask_health():
    return {"ok": True}


@app.post("/payments/charge")
@guard.policy("payment")
async def charge():
    return {"ok": True}
```

## RoutePolicy

`RoutePolicy` is the dataclass behind the decorator helpers.

```python
from adiuvare.policies import RoutePolicy

RoutePolicy(
    sensitivity="critical",
    ai_mode="assist",
    trackB=True,
    sink_mode="inline",
)
```

The useful fields are:

| field | values |
| --- | --- |
| `sensitivity` | `public`, `internal`, `critical` |
| `ai_mode` | `off`, `assist`, `critical`, `async` |
| `trackB` | `True`, `False` |
| `sink_mode` | `off`, `async`, `inline` |

`public` is the lighter posture. `internal` is the normal default.
`critical` is the stricter route path.

If a route sets its own `ai_mode`, that route-level value wins over the global
default from `adiuvare.yaml`.

You can also derive one policy from another:

```python
from adiuvare.policies import RoutePolicy

base = RoutePolicy(sensitivity="critical", ai_mode="assist", sink_mode="inline")
search_variant = base.with_overrides(sensitivity="public", ai_mode="off")

print(base.sensitivity, base.ai_mode)
print(search_variant.sensitivity, search_variant.ai_mode)
```

```text
critical assist
public off
```

## exempt()

Use `exempt()` for tiny routes that should stay out of the normal inspection
path.

```python
@app.get("/health")
@guard.exempt()
async def health():
    return {"ok": True}
```

Good candidates:

- health checks
- liveness probes
- low-value operational endpoints

## configure_routes()

If decorators are awkward, use `configure_routes()` and keep everything in one
shared table.

```python
guard.configure_routes(
    {
        "/internal/report": {"policy": "admin"},
        "/public/search": {"policy": "search"},
        "/billing": {"ai_mode": "assist", "sink_mode": "inline"},
        "/health": {"exempt": True},
    }
)
```

This works well when:

- your framework setup makes decorators clumsy
- you want route posture in one place
- routes are generated dynamically

## Global defaults and route overrides

The Config screen and `adiuvare.yaml` set global defaults. Route policy is
where you override those defaults for a specific endpoint.

That matters most for AI:

- global AI mode is the baseline
- route `ai_mode` can narrow or raise it per endpoint

The TUI Signals screen can show route posture, but it does not currently edit
per-route policy for you.

## Good habits

- use built-ins for common categories
- use `protect()` when a route really is special
- exempt only tiny routes that do not need the normal path
- keep one shared route-config table if your app gets large

## Related

- [FastAPI](../integrations/fastapi.md)
- [Custom signals](custom-signals.md)
- [Models API](../api/models.md)
