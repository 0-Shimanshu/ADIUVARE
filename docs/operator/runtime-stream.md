# Runtime Stream

Adiuvare has a local runtime stream behind the operator surface. Most people do
not talk to it directly, but it is the reason `adv status`, the TUI, and live
runtime actions feel connected to the running app.

## Local runtime stream

The runtime stream carries:

- recent event replay for new clients
- live event broadcast
- runtime snapshots
- runtime commands from the operator tools

That is what lets the CLI and TUI feel live without sitting inside the same
request handler process.

## Local backend

The normal local path is `UnixSocketEventStream`.

On platforms with Unix-domain support, it uses a real socket path. It supports:

- replay buffer on connect
- live broadcast to connected clients
- runtime commands over the same transport

## Windows fallback

On runtimes without `asyncio.start_unix_server`, the local path falls back to:

- localhost TCP
- a small `.sock` marker file containing the host and port

That keeps discovery simple for the CLI and TUI, even though it is not a true
Unix socket on Windows.

## Redis backend

You can also use a Redis-backed event stream:

```yaml
runtime:
  backend: redis
  redis_url: redis://127.0.0.1:6379/0
```

What Redis already gives you:

- Redis-backed event publication
- replay stored in Redis
- operator clients that connect through that backend
- runtime command flow over Redis transport

What it does not solve by itself:

- full shared identity state
- cluster-wide rate state
- cluster-wide whitelist coherence

## Runtime snapshots

Connected operator tools can ask for a runtime snapshot. That snapshot includes
things like:

- backend
- observe-only mode
- AI mode
- thresholds
- configurable weights
- banned IP count
- monitored identity count
- recent event count
- route overview

That is why `adv status`, Monitor, Signals, and AI can show live runtime
context instead of only static file values.

## Runtime commands

Current command names include:

- `get_runtime_snapshot`
- `confirm_block`
- `unblock_whitelist`
- `monitor_identity`
- `unmonitor_identity`
- `unblock_monitor`
- `ban_ip`
- `unban_ip`
- `patch_config`
- `get_analysis_report`
- `get_route_overview`
- `ask_ai_analyst`

The CLI and TUI use these under the hood. For normal use, treat them as
implementation details behind the supported operator surface.

## Connected vs disconnected operator experience

### When the stream is connected

The TUI header shows `connected` in green and the footer shows
`live link active`. Runtime-backed screens refresh from live data every 3
seconds. State-changing actions are sent to the runtime immediately.

### When the stream is not reachable

The TUI header shows `offline` in orange. All seven screens remain open but
read from local cache and the audit database instead of the live runtime. Data
shown may be stale.

State-changing actions taken while offline only write a local audit record.
They do not change runtime state. No ban, block, or monitor takes effect until
a connected session sends the command to a live runtime.

### When the stream drops mid-session

If the socket becomes unreachable after the TUI has already started, the
footer shows `stream link dropped`. The TUI continues running with the last
cached data. It does not exit or reconnect automatically. Restart `adv` to
re-establish the stream.

### How the UI signals unavailable actions

The TUI does not currently dim or disable individual action buttons based on
connection state. The header persistently shows `connected` or `offline`.
Operators should check the header before taking any state-changing action.

## Connected status example

```bash
adv status
```

```text
config: H:\ADIUVARE\adiuvare.yaml
runtime: connected
socket: C:\Users\me\AppData\Local\Temp\adiuvare.sock
backend: sqlite
framework: fastapi
instances: single
observe_only: False
ai_mode: assist
banned_ips: 1
recent_events: 7
```

That is the easy signal that the operator surface can reach the live runtime.

## What you get from it

The runtime stream solves:

- local operator inspection
- event replay for new clients
- live event broadcast
- runtime snapshot transport
- runtime command transport
- Redis-backed event transport when configured

## Boundaries

The runtime stream by itself does not solve:

- full distributed identity state
- cluster-wide shared rate control
- cluster-wide shared whitelist state

Those are larger runtime architecture questions.

## Related

- [CLI](cli.md)
- [TUI](tui.md)
- [Limitations](../limitations.md)
