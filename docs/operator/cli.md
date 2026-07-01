# CLI

The `adv` command is the quick operator shell. Use it when you want fast checks,
recent audit rows, a small report, or a simple live action without opening the
TUI.

## Command summary

| command | use it for |
| --- | --- |
| `adv init [--path adiuvare.yaml] [--no-tui]` | write a starter config |
| `adv status` | show config and runtime status |
| `adv config set <dotted.key> <value>` | update one config value |
| `adv logs [--tail 20] [--format text\|json\|jsonl]` | show recent audit rows |
| `adv report [--save] [--format markdown\|json]` | print or save a small local summary |
| `adv ban-ip <ip>` | ban an IP in a connected runtime |
| `adv unban-ip <ip>` | remove an IP ban in a connected runtime |
| `adv` | open the TUI |

## Config discovery

The CLI uses the same config resolver as the library itself.

If a command needs config and you do not pass a path explicitly, it checks:

1. `ADIUVARE_CONFIG`
2. the nearest `adiuvare.yaml` from the current working directory upward
3. `~/adiuvare.yaml`

### Example: working inside a service subfolder

```text
repo/
  adiuvare.yaml
  services/
    billing/
      scripts/
```

From `repo/services/billing/scripts`:

```bash
adv status
```

```text
config: H:\repo\adiuvare.yaml
runtime: offline
framework: fastapi
instances: single
observe_only: False
ai_mode: off
audit_db: .adiuvare/audit.db
```

### Example: force one config file

```bash
export ADIUVARE_CONFIG=H:\tenant-b\adiuvare.yaml
adv status
```

```text
config: H:\tenant-b\adiuvare.yaml
runtime: offline
framework: django
instances: single
observe_only: False
ai_mode: off
audit_db: .adiuvare/audit.db
```

## adv init

`adv init` writes a starter config.

```bash
adv init --no-tui
```

Typical terminal flow:

```text
Framework? [fastapi / flask / django] (fastapi):
Instances? [single / multi] (single):
Strictness? [public / internal / critical] (internal):
Mode? [observe / enforce] (observe):
Enable AI? [yes / no] (no):
AI model (llama3):
AI API key (leave blank if none):
Save path [adiuvare.yaml] (adiuvare.yaml):
wrote config: adiuvare.yaml
```

If the target file already exists, the CLI asks before overwriting it:

```text
adiuvare.yaml exists - overwrite? [y/N]
```

If you are already inside a project that has an `adiuvare.yaml` higher up the
tree, the CLI warns before creating a second config root:

```text
found existing config at H:\repo\adiuvare.yaml - create another one at H:\repo\services\billing\adiuvare.yaml? [y/N]
```

Without `--no-tui`, Adiuvare tries the TUI wizard first:

```bash
adv init
```

If the TUI dependencies are missing, it falls back to the plain terminal flow.

## adv status

`adv status` is the fastest answer to "what config is active?" and "is the
runtime connected?"

```bash
adv status
```

Connected runtime:

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

Offline runtime:

```text
config: H:\ADIUVARE\adiuvare.yaml
runtime: offline
framework: fastapi
instances: single
observe_only: False
ai_mode: off
audit_db: .adiuvare/audit.db
```

## adv config set

`adv config set` edits `adiuvare.yaml` directly.

```bash
adv config set thresholds.block 0.73
adv config set runtime.observe_only true
adv config set ai.mode assist
```

A successful run is silent. That is expected.

The command:

- resolves the active config file
- walks the dotted key path
- coerces simple values like booleans and numbers
- writes the YAML back to disk

Use it for file edits. It is separate from the live runtime command path.

## adv logs

`adv logs` prints recent audit rows.

```bash
adv logs --tail 20
```

```text
allow    user:1 /health
flag     user:7 /review
throttle user:8 /billing
block    user:9 /admin/login
```

This is the fastest human-readable view of "what just happened?"

The default format is `text`, so existing usage does not need to change. For
automation, choose JSON or JSONL explicitly:

```bash
adv logs --tail 20 --format json
adv logs --tail 20 --format jsonl
```

## adv report

`adv report` builds a small local summary from recent audit rows.

```bash
adv report
```

```text
# Adiuvare report

- rows: 42
- allow: 34
- flag: 3
- throttle: 4
- block: 1

## busiest identities
- user:8: 6
- api-key:tenant-a: 4
```

To save the same output to disk:

```bash
adv report --save
```

The command writes `adiuvare_report.md` in the current directory. The save does
not print an extra success line.

The default format is `markdown`. To emit machine-readable report data:

```bash
adv report --format json
```

To save the JSON report instead of Markdown:

```bash
adv report --save --format json
```

The command writes `adiuvare_report.json` in the current directory.

## adv ban-ip

`adv ban-ip` sends a live runtime action.

```bash
adv ban-ip 198.51.100.84
```

```text
banned ip: 198.51.100.84
banned_ips: 1
```

This requires a connected runtime. If the runtime is offline, the CLI fails
instead of pretending the action succeeded.

```text
runtime: offline
```

## adv unban-ip

`adv unban-ip` removes a live IP ban.

```bash
adv unban-ip 198.51.100.84
```

```text
unbanned ip: 198.51.100.84
banned_ips: 0
```

## adv

With no subcommand:

```bash
adv
```

The CLI tries to:

1. find `adiuvare.yaml`
2. discover a live runtime socket if one exists
3. open the TUI

If no config exists yet, it starts the init flow.

If the TUI dependencies are missing:

```text
tui deps are missing, try pip install -e .[tui]
```

## Good workflows

First-time local setup:

```bash
adv init --no-tui
adv status
```

Check recent activity:

```bash
adv status
adv logs --tail 20
```

Change one setting and recheck:

```bash
adv config set thresholds.block 0.72
adv status
```

Generate a quick local summary:

```bash
adv report --save
```

Run a live IP action:

```bash
adv ban-ip 198.51.100.84
adv unban-ip 198.51.100.84
```

## Related

- [Quickstart](../quickstart.md)
- [TUI](tui.md)
- [Runtime stream](runtime-stream.md)
