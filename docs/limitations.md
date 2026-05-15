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

### Connected vs disconnected mode

When the TUI starts, it looks for a live runtime socket. The header bar shows
the result at all times:

- `connected` in green means the runtime is reachable
- `offline` in orange means no socket was found or the runtime is unreachable

### Which views still work offline

All seven screens remain open and navigable when disconnected:

- Monitor, Events, Signals read from the local audit cache. Data may be stale.
- Audit and Changes always read from the local audit database.
- Config always reads and writes `adiuvare.yaml` on disk.
- AI falls back to local audit summarisation. Answers may be less detailed.

### Which actions mutate live runtime state

These actions send commands to the running runtime when connected:

- confirm block
- whitelist identity
- monitor identity
- unmonitor identity
- unblock and monitor
- ban IP
- unban IP
- apply config changes

When disconnected, these actions only write a local audit record. They do not
change runtime state. No ban, block, or monitor takes effect until a connected
session sends the command to a live runtime.

### How the UI signals unavailable actions

The TUI does not currently dim or disable individual action buttons based on
connection state. The header persistently shows `connected` or `offline` so
operators always know which mode they are in. The footer shows `live link
active` when the stream is healthy and `stream link dropped` if it disconnects
mid-session. Operators should check the header before taking any
state-changing action.

This is an area to tighten further. The long-term goal is to make the offline
story more explicit, either by disabling actions that cannot be applied for
real or by giving local single-instance mode a true local mutation path.

That means the TUI is strongest when attached to a running runtime.

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

## Related

- [Installation](installation.md)
- [Configuration](configuration.md)
- [TUI](operator/tui.md)
