# TUI Operator Guide

The Adiuvare TUI is a multi-screen terminal console for monitoring and managing a running WAF runtime. It is built with Textual and connects to the runtime over a Unix socket.

---

## Launching the TUI

Run the `adv` command with no arguments:

```bash
adv
```

If no `adiuvare.yaml` is found, the setup wizard runs first. Once config exists, the TUI opens immediately and attempts to connect to the runtime socket.

To install TUI dependencies if missing:

```bash
pip install -e ".[tui]"
```

---

## Connection States

The header bar shows the current connection state at all times:

| Header indicator | Meaning |
|-----------------|---------|
| `connected` (green) | Live runtime socket found; all actions available |
| `offline` (orange) | No socket found or runtime unreachable; read-only mode |

The footer center shows **live link active** when connected, and is blank when offline.

The header also shows the current **mode** (observe / enforce), **backend**, and **strictness** level, all read from the runtime snapshot or local config.

---

## Screens

Switch between screens using number keys or by clicking the tab buttons at the top.

### 1 — Monitor

**Works offline:** Yes (reads from local audit cache)

The main dashboard. Shows a live overview of runtime state including recent event counts, active identities, verdicts, and signal pressure. In connected mode, data refreshes automatically every 3 seconds and updates instantly on new stream events. In offline mode, data is read from the local audit database.

### 2 — Events

**Works offline:** Yes (reads from local audit cache)

Shows the event stream — individual request decisions made by the WAF. In connected mode, new rows arrive in real time via the stream loop (up to 145 rows in memory). In offline mode, rows are loaded from the audit database.

### 3 — Config

**Works offline:** Partial

Displays and edits the current `adiuvare.yaml` configuration. Config is always read from and written to disk, so this screen works offline. However, applying a config change to the running runtime (pushing thresholds, mode, AI settings) requires a live connection. When connected, config changes are sent to the runtime immediately after saving to disk.

### 4 — Signals

**Works offline:** Yes (reads from local audit cache)

Shows signal pressure and breakdown data — which detection signals (payload, behavior, identity) are contributing most to recent verdicts. Populated from stream rows when connected, or from the audit database when offline.

### 5 — AI

**Works offline:** Yes (degrades to local analysis)

The AI analyst screen. Operators can ask questions about recent traffic patterns and get a report with findings and recommendations. When connected, queries are forwarded to the runtime AI analyst. When offline, the screen falls back to local audit summarisation using the last 500 rows from the past 7 days. Answers in offline mode may be less detailed.

### 6 — Audit

**Works offline:** Yes (local reads only)

Displays the audit log — a record of all operator actions (blocks confirmed, IPs banned, config patches, etc.). This screen always reads from the local audit database and is fully available offline.

### 7 — Changes

**Works offline:** Yes (local reads only)

Shows a history of config and identity changes written to the audit log. Fully available offline.

---

## State-Changing Actions

The following actions mutate runtime state. When connected, they are dispatched to the runtime over the socket. When offline, they are written to the local audit log only and **are not replayed when the runtime reconnects**.

| Action | Connected behaviour | Offline behaviour |
|--------|-------------------|------------------|
| Confirm block (identity) | Sent to runtime immediately | Written to audit log only |
| Whitelist identity | Sent to runtime immediately | Written to audit log only |
| Monitor identity | Sent to runtime immediately | Written to audit log only |
| Unmonitor identity | Sent to runtime immediately | Written to audit log only |
| Unblock + monitor | Sent to runtime immediately | Written to audit log only |
| Ban IP | Sent to runtime immediately | Written to audit log only |
| Unban IP | Sent to runtime immediately | Written to audit log only |
| Apply config changes | Written to disk + sent to runtime | Written to disk only |

---

## Keyboard Reference

| Key | Action |
|-----|--------|
| `1` | Switch to Monitor screen |
| `2` | Switch to Events screen |
| `3` | Switch to Config screen |
| `4` | Switch to Signals screen |
| `5` | Switch to AI screen |
| `6` | Switch to Audit screen |
| `7` | Switch to Changes screen |
| `r` | Refresh the current screen |
| `q` | Quit the TUI |

---

## How the TUI Signals Unavailable State

The TUI does not disable or grey out individual action buttons based on connection state. Instead:

- When offline, state-changing actions fall back to writing to the local audit log. The footer note updates to confirm what happened (e.g. `runtime command sent` or `runtime command failed`).
- If the stream drops mid-session, the footer shows **stream link dropped**. The TUI continues running with the last cached data.
- The header **offline** indicator is always visible when the runtime is unreachable, giving operators a persistent signal that live dispatch is not active.
