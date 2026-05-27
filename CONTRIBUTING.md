# Contributing to Adiuvare

Thanks for taking an interest in Adiuvare. We want contributions to feel approachable, but we also want the project to stay focused and internally consistent. This guide is here to help you land changes that fit the repo cleanly.

## Scope

Adiuvare is an in-process request security library for Python APIs. It combines:

- a fast `trackA` gate for obvious early exits
- a scored `trackB` pipeline for softer request review
- local operator surfaces through the CLI and Textual TUI

Good contribution areas:

- new hard or soft signals
- tests for scoring, integrations, persistence, and operator flows
- TUI and CLI improvements
- docs, examples, and integration guides
- bug fixes and runtime polish
- route-policy and configuration improvements that match the current design

Changes we usually do not want:

- a browser dashboard that duplicates the TUI
- large architecture pivots without prior discussion
- changes that pretend distributed shared state is solved when it is not
- framework-specific sprawl that goes far beyond the current FastAPI, Flask, and Django support
- hidden product-scope changes mixed into a bug fix PR

If your idea changes the shape of the project, open an issue or discussion before writing a large patch.

If your issue or PR is mainly about the TUI, include screenshots or a short screen capture. Visual changes are much easier to review when we can compare the intended result with the actual screen state.

## Setup

Adiuvare currently installs from source. Use Python 3.11 or newer.

```bash
git clone https://github.com/YOUR_USERNAME/adiuvare.git
cd adiuvare
python -m venv .venv
```

Activate the environment:

```bash
source .venv/bin/activate
```

On Windows PowerShell:

```powershell
.venv\Scripts\Activate.ps1
```

Install the package in editable mode:

```bash
python -m pip install -e .
```

If you want the normal contributor setup with the test stack:

```bash
python -m pip install -e ".[dev]"
```

If you are working on the TUI:

```bash
python -m pip install -e ".[dev,tui]"
```

If you need Redis-backed runtime work too:

```bash
python -m pip install -e ".[dev,tui,redis]"
```

Run the test suite before you start making assumptions about the environment:

```bash
python -m pytest
```

You can also run a narrower slice while iterating:

```bash
python -m pytest tests/test_tui.py tests/test_audit.py
```

> Keep local machine files out of commits unless the change really belongs in the repo. In practice that usually means leaving `adiuvare.yaml` and any local-only `conftest.py` changes alone.

## Troubleshooting the dev environment

### Windows: choosing a terminal

The setup commands in this guide use Unix-style shell syntax. On Windows, use
one of these:

- **Git Bash** (recommended) — ships with Git for Windows, runs `source`,
  `which`, and most Unix commands without changes
- **PowerShell** — works, but use the PowerShell-specific activate command
  shown below
- **CMD** — works for basic commands; activate with `.venv\Scripts\activate.bat`

Avoid mixing terminals mid-session. Pick one and stay in it.

---

### Activating the virtual environment (Windows)

```powershell
# PowerShell
.venv\Scripts\Activate.ps1
```

If PowerShell blocks the script with an execution-policy error, run this once:

```powershell
Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser
```

Then activate again.

```bash
# Git Bash
source .venv/bin/activate
```

---

### `pip install -e ".[dev]"` fails on Windows

Some packages need a C compiler. Install
[Microsoft C++ Build Tools](https://visualstudio.microsoft.com/visual-cpp-build-tools/)
first, then retry.

If the error mentions a specific package, try upgrading pip and setuptools
before retrying the install:

```bash
python -m pip install --upgrade pip setuptools wheel
python -m pip install -e ".[dev]"
```

---

### `adv: command not found` after editable install

The `adv` script is created inside the virtual environment's `bin` (or
`Scripts` on Windows) directory. If it is not found, the environment is
probably not active.

Confirm the right Python is in use:

```bash
which python        # Git Bash / macOS / Linux
where python        # CMD
```

Then re-activate and try again. You can also run the CLI without the script:

```bash
python -m adiuvare.cli status
```

---

### How to verify the dev environment is working

After completing setup, run through this checklist:

**1. Package is importable:**

```bash
python -c "import adiuvare; print('ok')"
```

**2. CLI responds:**

```bash
adv status
```

Expected output includes a `config:` path and `runtime: offline`. That is
normal — `offline` means no app is running yet, not that anything is broken.

**3. Tests pass:**

```bash
python -m pytest
```

All tests should pass before you start making changes. If something fails on a
clean clone, open an issue before continuing.

---

### `python -m pytest` collects zero tests

Make sure you installed the `dev` extras:

```bash
python -m pip install -e ".[dev]"
```

Then run pytest again from the repo root (not from inside a subdirectory).


## Architecture

Adiuvare is intentionally compact. Most work touches one of these layers:

| Area | What it owns |
|---|---|
| `adiuvare/guard.py` | the public `Guard` entry point, integration setup, route policy application |
| `adiuvare/core/gate.py` | `trackA`, the fast gate for early exits |
| `adiuvare/core/pipeline.py` | request inspection flow and `trackB` handoff |
| `adiuvare/core/scorer.py` | weighted score calculation and contribution breakdown |
| `adiuvare/signals/` | built-in hard and soft signals |
| `adiuvare/state/` | persistence, audit history, identity state, whitelist and ban state, runtime stream |
| `adiuvare/integrations/` | FastAPI, Flask, and Django hooks |
| `adiuvare/tui/` | the 7-screen Textual operator console |

The request flow is:

```text
request
  -> trackA fast gate
  -> trackB soft-signal scoring
  -> verdict: allow | flag | throttle | block
  -> audit row + runtime visibility
```

Two design rules matter more than anything else:

1. `trackA` stays fast and deterministic.
2. Scoring logic lives in the scorer, not scattered across signals or integrations.

## Hard and soft signals

Most contributors will touch signals first.

Soft signals subclass `SoftSignal` and return a `SignalResult` from `async def extract(...)`. They add evidence to the scored path without forcing a hard stop.

```python
from adiuvare.signals import SoftSignal


class SuspiciousHeaderSignal(SoftSignal):
    name = "suspicious_header"
    weight = 0.20

    async def extract(self, ctx):
        ...
```

Hard signals subclass `HardSignal` and run in `trackA`.

```python
from adiuvare.signals import HardSignal


class PrivatePathSignal(HardSignal):
    name = "private_path"

    def check(self, ctx) -> bool:
        return ctx.path.startswith("/internal/")
```

Keep these rules in mind:

- hard signals stay synchronous
- hard signals should be cheap to evaluate
- soft signals do not mutate global score directly
- scorer math stays in `adiuvare/core/scorer.py`

Performance matters here. Pipeline changes that make request inspection noticeably slower are not a good trade.

- hard signals belong in `trackA`, so they should act like a quick check, not a mini pipeline
- soft signals should add useful evidence without creating obvious latency or heavy dependency churn
- adding many small overlapping soft signals can dilute the score and make the system harder to tune
- if you are improving an existing detection family, prefer extending the current signal with better patterns or better normalization before introducing a new near-duplicate signal

New signals should come from something defensible. That can be:

- a verified public source such as framework guidance, a well-known standards body, a mature security rule set, or a primary vendor reference
- a clear empirical case backed by a reproducer and tests in this repo

If you are proposing a new detection idea, include the source or reasoning in the issue or PR. If we cannot tell why the signal should exist, how it behaves, or what it catches, it is very unlikely to land.

Possible future signal dependencies can include tools like `rebuff`, `llm-guard`, `detoxify`, `presidio`, `detect-secrets`, `langdetect`, or `GeoIP2`, but treat those as candidates, not implied dependencies. A proposal still needs to show scope fit, performance discipline, and proof that the added signal is worth the cost.

If you are adding a new signal, read [docs/extending/custom-signals.md](docs/extending/custom-signals.md) first.

## Scoring and decisions

The default scorer currently combines these signal families:

- `payload`
- `behavior`
- `identity`
- `context`
- `ip_rep`

The configurable weights today are the first three. `context` and `ip_rep` are built-in fixed weights. If your change affects scoring, make sure it still produces:

- a bounded score in `0.0 .. 1.0`
- a clear contribution breakdown
- test coverage for both normal and edge-case paths

Do not sneak policy decisions into extractors, middleware, or UI code. If the math changes, it belongs in the scorer and in tests.

## Route policies

Adiuvare has global defaults and per-route posture. Those are not the same thing.

- global defaults come from `adiuvare.yaml`
- per-route behavior comes from decorators or route configuration

If you touch route policy code, read [docs/extending/route-policies.md](docs/extending/route-policies.md) and make sure the docs still match the code after your change.

## TUI and CLI work

The TUI is not a demo surface. It is part of the operator workflow.

That means TUI and CLI changes should be:

- honest about connected vs disconnected state
- wired to real runtime actions
- careful about enable and disable states
- tested when they change behavior, not just visuals

The TUI currently has seven screens:

1. Monitor
2. Events
3. Config
4. Signals
5. AI
6. Audit
7. Changes

If you touch the TUI, keep the docs and screenshots in sync when the visible behavior changes.

## Tests

Please add or update tests with behavioral changes.

Useful commands:

```bash
python -m pytest
python -m pytest tests/test_tui.py
python -m pytest tests/test_audit.py
python -m pytest tests/test_models.py
```

For signal work, test at least:

- clean input
- suspicious input
- boundary behavior
- shape of the returned score or gate result

For a new signal or a meaningful pattern expansion, include at least one test that proves the signal really fires on the target case and one test that proves a nearby normal case stays calm.

For TUI or runtime work, test the user-visible outcome rather than just private helper branches.

Run the relevant tests locally before you open the PR.

## Pull requests

Small, focused pull requests are much easier to review and merge. A good PR usually does one thing:

- add a signal
- fix a bug
- tighten an integration
- improve docs
- improve one operator workflow

Before opening a PR, make sure:

- tests pass locally
- docs are updated if behavior changed
- screenshots are updated if the TUI changed materially
- local-only files are not staged by accident
- new signals or major pattern additions include a source, a reproducer, or both

A good PR description usually answers:

1. What changed?
2. Why did it need to change?
3. How did you verify it?

## Communication

If you are unsure whether something fits the project, ask early. That is always cheaper than building a large patch that needs to be unwound later.

Use issues or discussions for:

- architecture questions
- scope questions
- signal ideas that may affect the product surface
- integration changes that need design agreement first

For TUI issues, include an image when you can. For TUI pull requests, include before and after screenshots or a short capture of the changed flow.

## Related docs

- [README.md](README.md)
- [docs/quickstart.md](docs/quickstart.md)
- [docs/configuration.md](docs/configuration.md)
- [docs/operator/cli.md](docs/operator/cli.md)
- [docs/operator/tui.md](docs/operator/tui.md)
- [docs/extending/custom-signals.md](docs/extending/custom-signals.md)
- [docs/extending/route-policies.md](docs/extending/route-policies.md)
