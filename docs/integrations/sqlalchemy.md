# SQLAlchemy Sink Hooks

Adiuvare can inspect SQL statements close to the sink. This is not the main
request middleware path. It is the extra layer that runs near real SQL
execution when you want a last checkpoint there too.

## Install

The SQLAlchemy sink integration requires SQLAlchemy. Install it via the `sink`
extra:

```bash
# from GitHub (before PyPI publish)
pip install "adiuvare[sink] @ git+https://github.com/0-Shimanshu/ADIUVARE.git"

# local development
pip install -e ".[sink]"

# once published to PyPI
pip install "adiuvare[sink]"
```

## Quick example

```python
from sqlalchemy import create_engine

from adiuvare import Guard
from adiuvare.integrations.sqlalchemy import attach_sink

guard = Guard.from_config("adiuvare.yaml")
engine = create_engine("sqlite:///app.db")

attach_sink(engine, guard)
```

That registers a `before_cursor_execute` listener and lets route sink mode
decide whether a suspicious statement should be ignored, recorded, or blocked
inline.

## What the hook looks at

Today the hook:

1. normalizes the SQL text
2. tries libinjection SQLi detection first
3. falls back to Adiuvare's SQL pattern checks when libinjection stays quiet

That makes it useful for both strong detector hits and softer SQL patterns that
still look suspicious.

## sink_mode

Route sink mode controls how the SQL hook behaves.

| mode | meaning |
| --- | --- |
| `off` | do nothing at the sink |
| `async` | record the detection and raise identity risk without throwing inline |
| `inline` | raise `AdiuvareBlockError("blocked_at_sink")` |

## Typical route pairing

```python
from fastapi import FastAPI
from sqlalchemy import create_engine

from adiuvare import Guard
from adiuvare.integrations.sqlalchemy import AdiuvareBlockError, attach_sink

app = FastAPI()
guard = Guard.from_config("adiuvare.yaml")
guard.use(app, framework="fastapi")

engine = create_engine("sqlite:///app.db")
attach_sink(engine, guard)


@app.post("/admin/query")
@guard.protect(sensitivity="critical", sink_mode="inline")
async def admin_query():
    try:
        with engine.begin() as conn:
            conn.exec_driver_sql("select * from users")
    except AdiuvareBlockError:
        return {"detail": "blocked_at_sink"}
    return {"ok": True}
```

Request middleware still runs first. The SQL hook is the last close-to-execution
check.

## What gets recorded

When the sink check fires, Guard records:

- the original SQL statement
- the normalized SQL statement
- confidence
- fingerprint when available

That data is useful for debugging, identity-risk elevation, and explaining why
the sink blocked or escalated.

## What this does not replace

The sink hook is useful. It is not a substitute for:

- parameterized queries
- proper ORM usage
- normal application security review

Think of it as one more layer near the risky operation.

## Related

- [FastAPI](fastapi.md)
- [Flask](flask.md)
- [Guard API](../api/guard.md)
