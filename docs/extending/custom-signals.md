# Custom Signals

Custom signals are how you teach Adiuvare about rules that only make sense in
your app. Use a soft signal when you want to add score, and a hard signal when
you want to stop a request immediately.

## Hard signal or soft signal?

This is the first decision to make before writing any code. Getting it wrong
means rewriting later.

| | `HardSignal` | `SoftSignal` |
| --- | --- | --- |
| Runs in | `trackA` — fast gate | `trackB` — scored pipeline |
| Returns | `True` to stop, `False` to pass | a `SignalResult` with a score |
| Must be synchronous | **yes** — no I/O, no `await` | no — async and I/O are fine |
| Skips the rest of the pipeline on match | **yes** — `trackB` never runs | no — score is combined with others |
| Produces intermediate verdicts (`flag`, `throttle`) | no — only stops or passes | yes, indirectly through the score |

**Use `HardSignal` when:**

- the check is binary — the request either matches a known-bad pattern or it
  does not
- you want the request stopped immediately, before any scoring happens
- the check can be done with in-process data only (a set lookup, a string
  comparison, a header check)

Good examples: banned IP, revoked token, blocked path prefix, required header
missing.

**Use `SoftSignal` when:**

- the result is a degree of risk, not a hard yes or no
- the check needs I/O (a cache read, a database query, an external API call)
- you want the signal to combine with others before a verdict is reached

Good examples: suspicious user-agent, payload pattern density, per-identity
rate pressure, route-family heuristics.

**If you find yourself wanting to do I/O inside `check()`, stop — that is a
soft signal.**

### Why hard signals must stay synchronous and fast

`trackA` runs before scoring, before async work, and before your handler ever
sees the request. Every millisecond added to a hard signal is paid on every
request. `validate_hard_signal()` will raise `AdiuvareStartupError` at startup
if your `check()` is async, so the rule is also enforced at boot time.

Keep hard signals to in-process checks only: membership tests, string
comparisons, integer comparisons. If you need external state, cache it at
startup or write a soft signal instead.

### How to verify a signal through the real guard path

Unit-testing a signal's logic in isolation is a good start, but always run it
through `guard.check_sync(...)` before opening a PR. That exercises the full
`trackA → trackB` path and confirms the signal fires — and produces the right
verdict — under real conditions.

Set up a guard with your signal(s) registered first. For example, a hard
signal that blocks a private path prefix, and a soft signal that flags a
known scanner user-agent:

```python
from adiuvare import Guard
from adiuvare.signals.base import HardSignal, SoftSignal
from adiuvare.core.models import SignalResult

class PrivatePathSignal(HardSignal):
    name = "private_path"
    action = "block"

    def check(self, ctx):
        return ctx.endpoint.startswith("/_internal")

class SuspiciousHeaderSignal(SoftSignal):
    name = "header_hint"
    weight = 0.10

    async def extract(self, ctx):
        agent = ctx.headers.get("user-agent", "")
        if "sqlmap" in agent.lower():
            return SignalResult(score=0.25, reason="sqlmap_ua")
        return SignalResult(score=0.0, reason="clean")

guard = Guard.from_config(
    "adiuvare.yaml",
    hard_signals=[PrivatePathSignal()],
    soft_signals=[SuspiciousHeaderSignal()],
)
```

For a hard signal:

```python
gate, event = guard.check_sync(
    "test:probe",
    context={"path": "/_internal/jobs", "endpoint": "/_internal/jobs", "method": "GET"},
)
assert not gate.passed
assert gate.block_reason == "private_path"
assert event is None  # trackB was skipped
```

For a soft signal:

```python
gate, event = guard.check_sync(
    "test:probe",
    context={"path": "/search", "method": "GET", "headers": {"user-agent": "sqlmap/1.8"}},
)
# gate.passed may still be True if score did not cross the block threshold,
# but the event should show the signal fired
assert event is not None
assert event.detail["signal_reasons"]["header_hint"] == "sqlmap_ua"
```

## Quick example

```python
from adiuvare import Guard
from adiuvare.core.models import SignalResult
from adiuvare.signals import SoftSignal


class SuspiciousHeaderSignal(SoftSignal):
    name = "header_hint"
    weight = 0.10

    async def extract(self, ctx):
        agent = ctx.headers.get("user-agent", "")
        if "sqlmap" in agent.lower():
            return SignalResult(score=0.25, reason="sqlmap_ua")
        return SignalResult(score=0.0, reason="clean")


guard = Guard.from_config("adiuvare.yaml", soft_signals=[SuspiciousHeaderSignal()])
gate, event = guard.check_sync(
    "user:42",
    context={"path": "/search", "method": "GET", "headers": {"user-agent": "sqlmap/1.8"}},
)

print(gate.passed)
print(event.detail["signal_reasons"]["header_hint"] if event else None)
```

```text
True
sqlmap_ua
```

The request still passed `trackA`, but the scored event kept your custom reason
for later review.

## SoftSignal

Use `SoftSignal` when you want to add risk without forcing a block. Good uses
include hostile client fingerprints, tenant-specific headers, or route-family
heuristics that should influence scoring.

```python
class SoftSignal:
    name: str = "unnamed"
    weight: float = 0.10

    async def extract(self, ctx: RequestContext) -> SignalResult:
        ...
```

`name` is the label that shows up in signal breakdowns. Keep it short and
stable. `weight` controls how much the signal family matters in the final
score.

`extract()` receives a `RequestContext` and returns a `SignalResult`. Most
custom signals read a small subset of the context:

- `ctx.identity`
- `ctx.payload`
- `ctx.headers`
- `ctx.endpoint`
- `ctx.method`
- `ctx.ip`
- `ctx.sensitivity`
- `ctx.snapshot`

Return `score=0.0` for the quiet path. Use `reason` for the short label you
want preserved in event detail.

### SignalResult

```python
SignalResult(
    score: float,
    reason: str,
    detail: dict[str, Any] = {},
    exception: Exception | None = None,
)
```

You will usually set `score`, `reason`, and sometimes `detail`. The runtime
will preserve those fields in the event.

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

## HardSignal

Use `HardSignal` when a request should stop in `trackA` before the slower
scoring path matters.

```python
class HardSignal:
    name: str = "unnamed"
    action: str = "block"

    def check(self, ctx: RequestContext) -> bool:
        ...
```

`action` is usually `"block"` or `"hold"`. `check()` must stay synchronous and
fast. It should return `True` only for the cases you want to stop immediately.

Example:

```python
from adiuvare import Guard
from adiuvare.signals import HardSignal


class PrivatePathSignal(HardSignal):
    name = "private_path"
    action = "block"

    def check(self, ctx):
        return ctx.endpoint.startswith("/_internal")


guard = Guard.from_config("adiuvare.yaml", hard_signals=[PrivatePathSignal()])
gate, event = guard.check_sync(
    "user:42",
    context={"path": "/_internal/jobs", "endpoint": "/_internal/jobs", "method": "GET"},
)

print(gate.passed)
print(gate.block_reason)
print(event)
```

```text
False
private_path
None
```

There is no scored event here because the fast gate stopped the request first.

### validate_hard_signal()

```python
validate_hard_signal(sig: HardSignal) -> None
```

Use this when you want to verify that a hard signal is valid before wiring it
into `Guard`.

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

> Hard signals run in `trackA`. Keep them synchronous and deterministic.

## Registering signals

### Guard.from_config()

```python
guard = Guard.from_config(
    "adiuvare.yaml",
    soft_signals=[SuspiciousHeaderSignal()],
)
```

Passing `soft_signals=[...]` replaces the default soft-signal list with your
own.

### PayloadSignal

If you still want Adiuvare's built-in payload scanner in that custom list, add
`PayloadSignal()` explicitly.

```python
from adiuvare.signals import PayloadSignal

guard = Guard.from_config(
    "adiuvare.yaml",
    soft_signals=[PayloadSignal(), SuspiciousHeaderSignal()],
)
```

### hard_signals

```python
guard = Guard.from_config(
    "adiuvare.yaml",
    hard_signals=[PrivatePathSignal()],
)
```

## Good habits

- keep `name` short and stable
- keep `reason` short and readable
- return `score=0.0` when the signal is quiet
- use hard signals only for cases you really want to stop immediately
- keep hard signals fast

## Related

- [Built-in signals](../signals.md)
- [Signals API](../api/signals.md)
- [Route policies](route-policies.md)
- [Guard API](../api/guard.md)
