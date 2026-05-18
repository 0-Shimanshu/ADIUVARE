# Flask

Flask is a good fit when you want the same request-scoring model inside a WSGI
app. The integration wraps `app.wsgi_app` and bridges the synchronous request
path into Adiuvare's runtime.

## Quick example

```python
from flask import Flask

from adiuvare import Guard

app = Flask(__name__)

guard = Guard.from_config("adiuvare.yaml")
guard.use(app, framework="flask")


@app.get("/health")
@guard.exempt()
def health():
    return {"ok": True}


@app.post("/auth/login")
@guard.policy("auth")
def auth_login():
    return {"ok": True}
```

Flask can also use `Guard.auto(app, config_path="adiuvare.yaml")`. The explicit
form is still easier to read when you want the framework choice spelled out in
the code.

## What is different in Flask

The host app stays synchronous, but the middleware still:

- reads the body from Werkzeug
- reads query-string values
- prefers `x-forwarded-for` before `remote_addr`
- builds a `RequestContext`
- bridges into the Guard inspection path

Flask also uses the thread-safe identity-store path internally, which matters
in a WSGI environment.

Route decorators preserve the original Flask view shape. Normal synchronous
Flask views stay synchronous, while async views stay async.

## Route helpers

Built-in policy:

```python
@app.post("/auth/login")
@guard.policy("auth")
def auth_login():
    return {"ok": True}
```

Explicit posture:

```python
@app.post("/billing")
@guard.protect(
    sensitivity="critical",
    ai_mode="assist",
    sink_mode="inline",
)
def billing():
    return {"ok": True}
```

Exempt route:

```python
@app.get("/health")
@guard.exempt()
def health():
    return {"ok": True}
```

Async views are supported too when your Flask app is configured for them:

```python
@app.get("/status")
@guard.exempt()
async def status():
    return {"ok": True}
```

## Query and body scanning

Flask combines body text and query-string text into the payload context, so
both of these can matter:

```bash
curl "http://127.0.0.1:5000/search?q=hello"
curl "http://127.0.0.1:5000/search?q=' OR 'a'='a"
```

Typical stronger responses:

```text
{"detail":"throttled"}
```

or:

```text
{"detail":"blocked"}
```

## SQLAlchemy pairing

Flask apps often hit SQLAlchemy directly, so this is a common pairing:

```python
from flask import Flask
from sqlalchemy import create_engine

from adiuvare import Guard
from adiuvare.integrations.sqlalchemy import attach_sink

app = Flask(__name__)
guard = Guard.from_config("adiuvare.yaml")
guard.use(app, framework="flask")

engine = create_engine("sqlite:///app.db")
attach_sink(engine, guard)
```

Request-local sink mode still decides whether the hook is:

- `off`
- `async`
- `inline`

## Operator flow

```bash
adv status
adv logs --tail 20
adv
```

Typical connected status:

```text
config: H:\ADIUVARE\adiuvare.yaml
runtime: connected
socket: C:\Users\me\AppData\Local\Temp\adiuvare.sock
backend: sqlite
framework: flask
instances: single
observe_only: False
ai_mode: off
banned_ips: 0
recent_events: 3
```

## Related

- [Quickstart](../quickstart.md)
- [SQLAlchemy sink hooks](sqlalchemy.md)
- [Route policies](../extending/route-policies.md)
