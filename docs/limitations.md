# Limitations

## TUI Connectivity

The TUI operates in two distinct modes depending on whether a live runtime socket is reachable. The runtime is located by scanning for `adiuvare*.sock` files in the system temp directory. If no socket is found, or the socket does not respond, the TUI starts in offline mode.

### Connected Mode

When a live runtime socket is found and responsive, all screens and actions are fully available. The header bar shows **connected** in green and the footer shows **live link active**.

Real-time event rows stream from the runtime and are kept in memory (up to 145 rows). The runtime snapshot, route overview, and all state-changing commands are sent directly to the running process.

### Disconnected Mode

When no socket is found or the runtime is unreachable, the TUI starts in offline mode. The header shows **offline** in orange and the footer link status is blank.

In offline mode:

- All seven screens are still accessible and navigable.
- Screens read from the local audit database and cached config instead of the live runtime.
- State-changing actions (block, whitelist, monitor, ban IP, apply config) write their intent to the local audit log rather than dispatching to the runtime. These are **not replayed** automatically when the runtime reconnects.
- AI analysis falls back to local audit summarisation instead of querying the runtime AI.
- The stream loop does not run; no new event rows arrive until reconnection.

### Stream Interruption During a Session

If the runtime socket drops while the TUI is already running, the footer shows **stream link dropped**. Screens continue to display the last cached data. The TUI does not exit or attempt automatic reconnection; it must be restarted to re-establish the stream.

---

## Known Constraints

- **No command buffering.** State-changing actions issued in offline mode are written to the local audit log only. They are not queued for replay when the runtime comes back online.
- **No automatic reconnection.** Once the stream drops mid-session, the TUI must be restarted to reconnect.
- **Event row cap.** The in-memory stream buffer holds a maximum of 145 rows. Older rows are dropped as new ones arrive.
- **Config apply requires connection.** Editing config in the TUI always writes to disk. Pushing the change to a running runtime requires a live socket; without one, only the file is updated.
- **AI screen degrades gracefully.** When offline, the AI screen answers questions using local audit data. Answers may be less detailed than those produced by a connected runtime with full AI access.
