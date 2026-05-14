# Runtime Stream

The runtime stream is the live channel between the TUI and a running Adiuvare WAF process. This document explains how the stream is established, what it carries, and what operators should expect when it is healthy, degraded, or absent.

---

## How the Stream is Established

When the TUI starts, it scans the system temp directory for Unix socket files matching the pattern `adiuvare*.sock`. If multiple sockets are found, it picks the most recently modified one.

The socket path is passed into the TUI app at launch. If no socket is found, `socket_path` is `None` and the TUI starts in offline mode without attempting any connection.

There is no retry loop on startup. If the socket is absent when `adv` is run, the TUI starts offline and stays offline for that session.

---

## What the Stream Carries

Once connected, the TUI establishes two concurrent async tasks:

**Stream loop (`_stream_loop`)** — subscribes to the runtime event feed. Each incoming row is a WAF decision (a request that was allowed, flagged, throttled, or blocked). Rows are prepended to an in-memory list capped at 145 entries. All screens that show event data read from this list when connected.

**Runtime refresh (`_refresh_runtime`)** — periodically calls two runtime commands: `get_runtime_snapshot` (returns current runtime state: mode, backend, banned IPs, identity counts, thresholds, etc.) and `get_route_overview` (returns the list of seen routes). This runs on the 3-second auto-refresh interval and after every state-changing command.

---

## Stream Lifecycle

```
adv launched
    │
    ├─ Socket found ──► TUI starts connected
    │                       │
    │                       ├─ stream_loop: live event rows
    │                       ├─ refresh_runtime: snapshot + routes
    │                       └─ auto-refresh every 3s
    │
    └─ No socket ────► TUI starts offline
                           │
                           └─ reads audit DB + local config only
```

If the stream drops during a session, `_stream_loop` catches the exception and sets the footer to **stream link dropped**. No reconnection is attempted. The TUI continues running with cached data.

---

## State-Changing Commands

When an operator takes an action in the TUI (confirm block, ban IP, apply config, etc.), the command is sent to the runtime via `_send_command`. This is an async call over the socket using `EventStreamClient`.

On success, the footer shows **runtime command sent** and the runtime snapshot refreshes immediately. On failure, the footer shows **runtime command failed** and no state is changed in the runtime.

Commands are fire-and-forget within the session. There is no acknowledgement queue and no retry. If the socket drops between the operator action and the runtime receiving it, the command is lost.

**When offline**, the same action methods (`ban_ip`, `confirm_block`, `whitelist_identity`, etc.) write the intent to the local audit log via `AuditLog.write_patch`. These entries are visible in the Changes screen but are **not dispatched to the runtime** and are **not replayed** when a runtime starts later.

---

## Runtime Snapshot

The snapshot is the TUI's authoritative view of live runtime state. It includes:

- Connection status (`connected`)
- Operating mode (`observe_only`)
- Backend type and strictness
- Banned IP count and monitored identity count
- Threshold values (flag, throttle, block)
- Weight values (payload, behavior, identity)
- AI mode and model
- Socket path and audit/state DB paths

When connected, the snapshot is refreshed from the runtime every 3 seconds and after every command. When offline, the snapshot is built entirely from local config values, with live fields (banned IPs, event counts, etc.) defaulting to zero or empty.

---

## Config Watcher

The TUI also watches `adiuvare.yaml` for changes on disk via `ConfigWatcher`. If the file changes between ticks (checked every 1 second), the config is reloaded and the active screen refreshes. This works regardless of connection state. The footer shows **config changed on disk** when this happens.

---

## Debugging Connection Issues

Check whether the runtime is running and has created a socket:

```bash
adv status
```

This command reads the same socket discovery logic and prints `runtime: connected` or `runtime: offline` along with the socket path if found.

If the socket exists but the TUI shows offline, the runtime process may have crashed after creating the socket. Remove stale socket files from the temp directory and restart the runtime.

To see the socket path the TUI found, check the Monitor screen's runtime snapshot panel (the `stream_path` field) when connected.
