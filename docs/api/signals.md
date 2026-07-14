# Signals API

Signals are Adiuvare's public extension surface for custom scoring and custom
fast-gate checks. If built-in payload, behavior, identity, context, and IP
hints are not enough for your app, this is where you extend the runtime.

## Hard signal or soft signal?

`HardSignal` runs synchronously in `trackA` and stops a request immediately
on match. `SoftSignal` runs in `trackB`, can do I/O, and contributes a score
instead of a hard stop.

See [Custom signals](../extending/custom-signals.md#hard-signal-or-soft-signal)
for the full comparison table, when to use each, and verification examples.

## Quick example

```python
import asyncio

from adiuvare.core.models import RequestContext, SignalResult
from adiuvare.signals import SoftSignal


class SuspiciousAgentSignal(SoftSignal):
    name = "agent_hint"
    weight = 0.15

    async def extract(self, ctx: RequestContext) -> SignalResult:
        agent = ctx.headers.get("user-agent", "").lower()
        if "sqlmap" in agent:
            return SignalResult(score=0.35, reason="sqlmap_ua")
        return SignalResult(score=0.0, reason="clean")


ctx = RequestContext(
    identity="u1",
    payload=None,
    url="/search",
    method="GET",
    headers={"user-agent": "sqlmap/1.8"},
    ip="127.0.0.1",
    endpoint="/search",
)

res = asyncio.run(SuspiciousAgentSignal().extract(ctx))
print(res.score)
print(res.reason)
```

```text
0.35
sqlmap_ua
```

## Public imports

```python
from adiuvare.signals import (
    AdiuvareStartupError,
    HardSignal,
    PayloadSignal,
    SoftSignal,
    validate_hard_signal,
)
from adiuvare.core.models import RequestContext, SignalResult
```

## SoftSignal

```python
class SoftSignal:
    name: str = "unnamed"
    weight: float = 0.10

    async def extract(self, ctx: RequestContext) -> SignalResult:
        ...
```

Use a soft signal when you want to add score without forcing an immediate
block.

The fields you will care about most are:

- `name` for the stable label shown in breakdowns
- `weight` for how much this signal family should matter

`extract()` receives a `RequestContext` and returns a `SignalResult`.

Most custom signals only read a small part of the context:

- `ctx.identity`
- `ctx.payload`
- `ctx.headers`
- `ctx.endpoint`
- `ctx.method`
- `ctx.ip`
- `ctx.sensitivity`
- `ctx.snapshot`

Example registration:

```python
from adiuvare import Guard
from adiuvare.core.models import SignalResult
from adiuvare.signals import SoftSignal


class LoudSignal(SoftSignal):
    name = "payload"
    weight = 0.90

    async def extract(self, ctx):
        return SignalResult(score=0.9, reason="loud_hit")


guard = Guard(soft_signals=[LoudSignal()])
gate, event = guard.check_sync(
    "u1",
    payload="hello world",
    context={"path": "/", "method": "GET"},
)

print(gate.passed)
print(round(event.score, 2) if event else None)
```

```text
True
0.9
```

## HardSignal

```python
class HardSignal:
    name: str = "unnamed"
    action: str = "block"

    def check(self, ctx: RequestContext) -> bool:
        ...
```

Use a hard signal when the request should stop in `trackA` before the slower
scoring path matters.

`action` is normally:

- `block`
- `hold`

`check()` must stay synchronous and fast. It runs on every request before
scoring starts, so any I/O here adds latency to the entire pipeline.
`validate_hard_signal()` enforces this at startup — async implementations
raise `AdiuvareStartupError`.

Example:

```python
from adiuvare import Guard
from adiuvare.signals import HardSignal


class HoldReviewSignal(HardSignal):
    name = "hold_review"
    action = "hold"

    def check(self, ctx):
        return ctx.endpoint == "/review"


guard = Guard(hard_signals=[HoldReviewSignal()])
gate, event = guard.check_sync(
    "u1",
    context={"path": "/review", "endpoint": "/review", "method": "POST"},
)

print(gate.passed)
print(gate.hold)
print(event)
```

```text
False
True
None
```

## validate_hard_signal()

```python
validate_hard_signal(sig: HardSignal) -> None
```

This rejects async hard-signal implementations.

```python
from adiuvare.signals import AdiuvareStartupError, HardSignal, validate_hard_signal


class BadHardSignal(HardSignal):
    async def check(self, ctx):
        return True


try:
    validate_hard_signal(BadHardSignal())
except AdiuvareStartupError as exc:
    print(str(exc))
```

```text
BadHardSignal.check() must stay sync in track a
```

## PayloadSignal

```python
from adiuvare.signals import PayloadSignal
```

`PayloadSignal` is the built-in soft signal for payload scanning. You normally
import it when you are replacing the default `soft_signals=[...]` list but
still want the built-in payload scanner in your custom stack.

Today it combines:

- libinjection SQLi checks
- libinjection XSS checks
- Adiuvare SQL pattern checks
- XSS pattern checks
- path traversal pattern checks

Example:

```python
import asyncio

from adiuvare.core.models import RequestContext
from adiuvare.signals import PayloadSignal

ctx = RequestContext(
    identity="u1",
    payload="' OR 'a'='a",
    url="/search",
    method="POST",
    headers={},
    ip="127.0.0.1",
    endpoint="/search",
)

res = asyncio.run(PayloadSignal().extract(ctx))
print(round(res.score, 2))
print(res.reason)
```

```text
0.88
sql_boolean_tautology
```

## SignalResult

```python
SignalResult(
    score: float,
    reason: str,
    detail: dict[str, Any] = {},
    exception: Exception | None = None,
)
```

This is the object `SoftSignal.extract(...)` returns.

| field | meaning |
| --- | --- |
| `score` | how much risk the signal contributes |
| `reason` | short label for the branch that fired |
| `detail` | optional structured metadata |
| `exception` | optional captured exception |

Example:

```python
from adiuvare.core.models import SignalResult

res = SignalResult(
    score=0.42,
    reason="tenant_header",
    detail={"header": "x-tenant", "value": "red-team"},
)

print(res.score)
print(res.reason)
print(res.detail["header"])
```

```text
0.42
tenant_header
x-tenant
```

## Built-in signal families

The default Guard path ships with five built-in soft-signal families:

- `payload`
- `behavior`
- `identity`
- `context`
- `ip_rep`

Only `PayloadSignal` is exported as a public class today because it is the one
most people reuse directly.

## Related

- [Built-in signals](../signals.md)
- [Custom signals](../extending/custom-signals.md)
- [Guard API](guard.md)
- [Models API](models.md)
