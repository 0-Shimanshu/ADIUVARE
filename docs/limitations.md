# Limitations

Adiuvare is usable at `0.1.0`, but it still has real boundaries worth knowing
before you build around it. This is the plainspoken version.

## Redis is a working backend, not full distributed coordination

The practical backend story today is:

- `sqlite` -> normal local single-instance backend
- `redis` -> supported backend for a single running app too

What Redis already does well:

- event publication
- replay for operator clients
- runtime command flow over the Redis transport

What is still partial:

- shared identity state across processes
- cluster-wide rate and block behavior
- cluster-wide whitelist and ban state as one coordinated store

If you set:

```yaml
meta:
  instances: multi
```

read that as a deployment hint, not a promise that full distributed runtime
coordination is already solved.

## Some TUI behavior depends on a live runtime

The TUI works in both connected and disconnected states, but those states are
not identical.

When connected, it can:

- subscribe to live rows
- ask for runtime snapshots
- send runtime commands

When disconnected, it falls back to:

- local config reads
- local audit reads
- cached recent views where possible

One important consequence today:

- state-changing operator actions such as `ban_ip`, `unban_ip`,
  `monitor_identity`, `unmonitor_identity`, and `unblock_monitor` are
  authoritative when the TUI is connected to a live runtime
- a disconnected TUI can still show cached data and control-plane history, but
  that is not the same thing as mutating live runtime state

The header bar shows `connected` or `disconnected` at all times. When
disconnected, a banner and footer text make cached-only mode obvious. On Events
and Audit, runtime-mutating buttons and shortcuts are disabled so they cannot
be mistaken for live control. Export and read-only inspection still work.

For the full breakdown of which screens work offline, which actions require a
live runtime, and how the UI signals connection state, see
[TUI](operator/tui.md).

The TUI is strongest when attached to a running runtime.

## The TUI is still a bounded operator console

The current TUI covers:

- Monitor
- Events
- Config
- Signals
- AI
- Audit
- Changes

That is a useful live console. It is still lighter than a larger standalone
operator platform.

Current product boundaries:

- Audit and Events are recent-window surfaces, not deep paginated
  investigation tools
- Signals explains the live signal mix, but it is not a full route-policy editor
- AI Analyze is strongest as a compact summary, not a long-form investigation system
- AI Ask is bounded analysis, not a general-purpose copilot
- some Config fields are saved for next reload or startup instead of fully hot-applied

## Saved config and live config are not the same thing

The Config screen and `adv config set` both write `adiuvare.yaml`, but not
every field behaves the same way in the already-running app.

The best live-patch candidates are:

- threshold bands
- observe mode
- global AI mode

Other values are still mainly:

- saved to file
- picked up on the next reload or startup

That matters most for:

- backend selection
- Redis connection settings
- monitored defaults
- some AI connection details

## AI requires an external endpoint

The AI path is real, but it depends on an Ollama-compatible endpoint and a
usable model being available there.

If the endpoint is unavailable, Adiuvare degrades cleanly instead of failing
the whole runtime.

That is also why there are two related but different AI experiences:

- request-time AI for verdict shaping
- TUI AI for operator summaries and bounded questions

They should not be expected to produce the same style of output.

## libinjection still has a build edge

What works already:

- a checked-in Windows DLL
- the vendored source tree
- local build scripts
- Python fallback heuristics

What is not fully finished:

- automated wheel builds for every platform
- a completely smooth binary story on every user machine

If the bundled binary is not right for the target machine, you may still need a
local build step.

## Windows local stream uses a fallback

On runtimes without `asyncio.start_unix_server`, the local stream uses:

- a localhost TCP server
- plus a small `.sock` marker file for discovery

That keeps the operator path working, but it is not the same thing as a true
Unix socket.

## The CLI is intentionally smaller than the TUI

The CLI is meant for quick tasks:

- init
- status
- logs
- report
- small config edits
- simple live actions such as `ban-ip` and `unban-ip`

It is not trying to be a full terminal version of the TUI.

## Public API is smaller than the module tree

Adiuvare has many internal modules. Only a smaller set should be treated as the
public API.

Use the pages in `docs/api/` as the real boundary. That keeps app code from
coupling itself to internals that may still move.

## Source install is still the smoothest pre-release path

Before a broader publish story is in place, the smoothest setup is still:

- clone the repo
- create a virtual environment
- `pip install .`
- add extras like `.[tui]` or `.[redis]` when needed

That is fine for contributors and early adopters. It is simply different from a
fully polished "pip install from PyPI and go" story on every machine.

## Payload detection limits

Payload inspection is intentionally narrow and focused on high-signal patterns. It does not attempt full coverage of all attack classes.

### Strong areas

- common SQL injection patterns such as `SELECT`, `UNION`, and simple tautologies
- basic XSS markers such as `<script>` and inline JavaScript
- path traversal sequences like `../` and encoded variants
- simple normalization and encoding variants of these patterns

### Known gaps

- broader or uncommon attack families
- multi-step or context-dependent payloads
- deeply obfuscated or fragmented inputs
- domain-specific payload formats

These cases may be detected inconsistently or assigned lower scores.

### False positives

The system can over-trigger on benign content that includes risky strings.

Typical cases:

- SQL examples in tutorials or documentation
- literal HTML or script tags in docs
- copied payloads used for explanation or testing

Examples:

- "How do I write SELECT \* FROM users in a tutorial?"
- "How do I print <script> literally in docs?"

These are not attacks, but may still produce elevated payload scores.

### Practical implication

Payload detection should not be treated as complete or authoritative.

Use:

- custom signals
- route-level policies
- threshold tuning

to adapt behavior to real workloads and reduce false positives.

## Related

- [Installation](installation.md)
- [Configuration](configuration.md)
- [TUI](operator/tui.md)
