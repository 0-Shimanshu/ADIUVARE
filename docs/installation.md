# Installation

Installing Adiuvare is straightforward. The only real choice up front is whether you want just the core library, the TUI, or the Redis backend too.

## Quick install

### For Regular Users (Remote Installation)

Use these commands to install Adiuvare directly from GitHub into your environment without needing to clone the repository source tree manually:

| need | command |
| --- | --- |
| core library | `python -m pip install "git+https://github.com/0-Shimanshu/ADIUVARE.git"` |
| core + TUI | `python -m pip install "adiuvare[tui] @ git+https://github.com/0-Shimanshu/ADIUVARE.git"` |
| core + Redis | `python -m pip install "adiuvare[redis] @ git+https://github.com/0-Shimanshu/ADIUVARE.git"` |

### For Project Contributors (Local Repository Clone)

If you are a developer working directly inside a local clone of the repository source tree, navigate to the repository root directory and use these commands:

| need | command |
| --- | --- |
| editable local dev | `python -m pip install -e .` |
| editable dev test stack | `python -m pip install -e ".[dev]"` |
| editable dev with extras | `python -m pip install -e ".[dev,tui,redis]"` |

## Verify the install

The quickest check is to write a starter config and ask for status.

```bash
adv init --no-tui
adv status
```

Typical output before your app is running:

```text
$ adv init --no-tui
wrote config: adiuvare.yaml

$ adv status
config: H:\path\to\adiuvare.yaml
runtime: offline
framework: fastapi
instances: single
observe_only: True
ai_mode: off
audit_db: .adiuvare/audit.db
```

That means the install is fine, the config file exists, and the operator tools
can read it.

## TUI install

If you want the Textual operator console, install the TUI extra.

```bash
python -m pip install "adiuvare[tui] @ git+https://github.com/0-Shimanshu/ADIUVARE.git"
```

Then launch it with:

```bash
adv
```

The current TUI has seven screens:

- Monitor
- Events
- Config
- Signals
- AI
- Audit
- Changes

## Redis install

If you want the Redis event-stream backend, install the Redis extra.

```bash
python -m pip install "adiuvare[redis] @ git+https://github.com/0-Shimanshu/ADIUVARE.git"
```

Then set:

```yaml
runtime:
  backend: redis
  redis_url: redis://127.0.0.1:6379/0
```

> Redis is a working backend. It is not the same thing as full distributed
> shared state. Use it confidently for a single running app. Treat broader
> multi-instance coordination as a separate question.

## Editable install

Use an editable install when you are changing the library itself.

```bash
python -m pip install -e ".[dev]"
```

Or with the common extras:

```bash
python -m pip install -e ".[dev,tui,redis]"
```

That is the smoothest setup for local development, tests, and doc work.

## libinjection assets

Adiuvare ships with:

- a checked-in Windows DLL
- the vendored `libinjection_src/` tree
- local build scripts

In the common case, you should not have to do anything special here.

## Local libinjection build

If the bundled binary is not right for your machine, build it locally.

Windows:

```bash
python scripts/build_libinjection.py
```

Shell:

```bash
sh scripts/build_libinjection.sh
```

If the compiled detector is unavailable, Adiuvare falls back to Python
heuristics. That keeps the runtime usable, but it is still the weaker path.

## Troubleshooting

### `tui deps are missing`

Install the TUI extra:

```bash
python -m pip install "adiuvare[tui] @ git+https://github.com/0-Shimanshu/ADIUVARE.git"
```

### Redis import errors

Install the Redis extra:

```bash
python -m pip install "adiuvare[redis] @ git+https://github.com/0-Shimanshu/ADIUVARE.git"
```

### libinjection not loading

Try the local build script first. If that still fails, the runtime will stay up
on the Python fallback path.

## Related

- [Quickstart](quickstart.md)
- [Configuration](configuration.md)
- [Limitations](limitations.md)
