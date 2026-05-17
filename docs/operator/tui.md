# TUI

The TUI is Adiuvare's richer operator console. It gives you live screens for
traffic, reviewable events, config edits, signal mix, AI summaries, audit
history, and recent control-plane changes.

## Launch

```bash
adv
```

If there is no `adiuvare.yaml` yet, startup sends you through setup first.

## Connected and disconnected mode

When connected, the TUI can:

- subscribe to live rows
- request runtime snapshots
- send runtime commands
- patch a small set of live runtime values

When disconnected, it falls back to:

- local config reads
- local audit reads
- cached recent views where possible

The TUI is still useful offline. It is just strongest when attached to a
running runtime.

### How the UI signals connection state

The header bar shows the current connection state at all times:

- `connected` in green means a live runtime socket is reachable
- `offline` in orange means no socket was found or the runtime is unreachable

The footer shows `live link active` when the stream is healthy. If the stream
drops mid-session, the footer shows `stream link dropped`. The TUI does not
exit or reconnect automatically in that case.

### How the UI signals unavailable actions

The TUI does not currently dim or disable individual action buttons based on
connection state. The header persistently shows `connected` or `offline` so
operators always know which mode they are in. Operators should check the
header before taking any state-changing action. Any action taken while the
header shows `offline` only writes a local audit record and does not change
runtime state.

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

## Navigation

The current TUI has seven screens:

1. `Monitor`
2. `Events`
3. `Config`
4. `Signals`
5. `AI`
6. `Audit`
7. `Changes`

Common keys:

```text
[1-7] switch screens
[up/down] move in tables
[Tab] move between inputs
[q] quit
```

The TUI refreshes automatically every 3 seconds.

## Monitor

Monitor is the landing screen. It is the fastest answer to:

- are we connected?
- which backend are we on?
- are recent events flowing?
- what does the current decision mix look like?

It shows:

- recent rows
- runtime status
- decision thresholds
- verdict mix
- aggregate signal pressure
- top identities
- hot endpoints

![Monitor screen](../assets/tui/monitor.png)

## Events

Events is the review queue. It focuses on non-allow rows that need operator
attention.

It shows:

- verdict
- score
- identity
- endpoint
- IP
- dominant signal
- age

The lower panes show:

- selected event detail
- signal breakdown
- identity context
- available actions

Current actions include:

- confirm block
- whitelist
- monitor identity
- unmonitor identity
- unblock + monitor
- ban IP
- unban IP
- export JSON

![Events screen](../assets/tui/events.png)

## Config

Config is the live operator settings screen. It is built around the current
runtime shape, not a generic admin panel.

You can edit:

- decision thresholds
- signal weights
- AI settings
- runtime settings
- monitored defaults
- profile strictness

It also shows a small recent-changes preview.

Typical flow:

```text
1. Open Config
2. Edit one field
3. Press [S]
4. Recheck Monitor or Changes
```

Some fields patch live when connected. Others are saved for the next reload or
startup.

![Config screen](../assets/tui/config.png)

## Signals

Signals is the live scoring view.

It shows:

- built-in signal families
- current weights
- status
- recent hit counts
- route overview
- route AI mode
- aggregate signal pressure
- top contributors

Use it when you want to understand why recent traffic is scoring the way it is.

![Signals screen](../assets/tui/signals.png)

## AI

The AI screen has two modes:

- `Analyze`
- `Ask`

### Analyze

Analyze builds a compact report-style summary from recent audit rows.

It shows:

- event totals
- flagged and blocked counts
- decision distribution
- signal pressure
- a short summary
- recommendations
- report source

Source is shown clearly because results may come from runtime AI or local
analysis fallback.

![AI Analyze screen](../assets/tui/ai-analyze.png)

### Ask

Ask is the bounded operator assistant.

It is meant for questions like:

- what are the top threats?
- who is most active?
- should I change thresholds?
- explain payload signals

The header shows:

- whether the TUI is connected to the runtime
- which model is configured
- that model reachability is not checked by this header
- whether local fallback is available

Runtime connection only means the operator console can reach the Adiuvare
runtime snapshot/command surface. It does not prove that the configured model
endpoint is reachable.

![AI Ask screen](../assets/tui/ai-ask.png)

## Audit

Audit is the broader recent-history screen. Unlike Events, it includes allow
rows too.

It shows:

- the recent audit table
- selected event detail
- signal breakdown
- AI detail when present

Use it when you want the larger recent record instead of only the review queue.

![Audit screen](../assets/tui/audit.png)

## Changes

Changes is the control-plane history screen.

It tracks:

- operator actions
- config writes
- runtime patches
- control-plane events such as ban, unban, monitor, and whitelist actions

The detail pane shows:

- kind
- age
- recorded time
- target
- summary
- patch payload when present

![Changes screen](../assets/tui/changes.png)

## Typical workflows

Review live traffic:

```text
1. Open Monitor
2. Move to Events for reviewable rows
3. Inspect the selected row
4. Take an action if needed
5. Verify the result in Changes
```

Tune thresholds:

```text
1. Open Config
2. Change one threshold
3. Save
4. Check Changes for the patch record
5. Return to Monitor or Events
```

Ask for a summary:

```text
1. Open AI
2. Use Analyze for the report view
3. Use Ask for a direct question
4. Check the source label on the result
```

## Related

- [CLI](cli.md)
- [Runtime stream](runtime-stream.md)
- [Limitations](../limitations.md)
