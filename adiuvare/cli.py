import argparse
import asyncio
import sys
import tempfile
from collections import Counter
from pathlib import Path
from typing import Any

import yaml

from adiuvare.config.editor import merge_sections, starter_config
from adiuvare.config.loader import find_config_file, load_config
from adiuvare.state.audit_log import AuditLog
from adiuvare.state.event_stream import EventStreamClient


def main() -> None:
    parser = argparse.ArgumentParser(prog="adv", description="Adiuvare local operator shell")
    sub = parser.add_subparsers(dest="cmd")

    p_init = sub.add_parser("init", help="write a starter adiuvare.yaml")
    p_init.add_argument("--path", default="adiuvare.yaml")
    p_init.add_argument("--no-tui", action="store_true")

    sub.add_parser("status", help="show local status")

    p_cfg = sub.add_parser("config", help="patch a config key")
    p_cfg.add_argument("action", choices=["set"])
    p_cfg.add_argument("key")
    p_cfg.add_argument("value")

    p_logs = sub.add_parser("logs", help="print recent audit rows")
    p_logs.add_argument("--tail", type=int, default=20)

    p_report = sub.add_parser("report", help="print a local markdown summary")
    p_report.add_argument("--save", action="store_true")

    p_ban_ip = sub.add_parser("ban-ip", help="ban an ip in the running runtime")
    p_ban_ip.add_argument("ip")

    p_unban_ip = sub.add_parser("unban-ip", help="remove an ip ban from the running runtime")
    p_unban_ip.add_argument("ip")

    args = parser.parse_args()

    if args.cmd is None:
        _open_tui()
    elif args.cmd == "init":
        _run_init(Path(args.path), no_tui=args.no_tui)
    elif args.cmd == "status":
        _run_status()
    elif args.cmd == "config":
        _run_config_set(args.key, args.value)
    elif args.cmd == "logs":
        _run_logs(args.tail)
    elif args.cmd == "report":
        _run_report(save=args.save)
    elif args.cmd == "ban-ip":
        _run_ip_ban(args.ip)
    elif args.cmd == "unban-ip":
        _run_ip_unban(args.ip)


def _open_tui() -> None:
    cfg = _find_cfg()
    if cfg is None:
        _run_init(Path("adiuvare.yaml"), no_tui=False)
        return
    try:
        from adiuvare.tui.app import AdiuvareApp
    except ImportError:
        print("tui deps are missing, try pip install -e .[tui]")
        raise SystemExit(1)

    socket_path, _snap = _runtime_link()
    AdiuvareApp(socket_path=socket_path, config_path=str(cfg)).run()


def _run_init(path: Path, no_tui: bool) -> None:
    dest = path if path.suffix else path / "adiuvare.yaml"
    if dest.exists():
        answer = input(f"{dest} exists - overwrite? [y/N] ").strip().lower()
        if answer != "y":
            print("aborted")
            return
    else:
        parent_cfg = find_config_file(dest.parent, include_home=False, use_env=False)
        if parent_cfg is not None and parent_cfg != dest:
            answer = input(
                f"found existing config at {parent_cfg} - create another one at {dest}? [y/N] "
            ).strip().lower()
            if answer != "y":
                print("aborted")
                return
    if no_tui:
        _plain_terminal_wizard(dest)
        return
    try:
        from adiuvare.tui.wizard import run_wizard
    except ImportError:
        _plain_terminal_wizard(dest)
        return
    run_wizard(dest)


def _plain_terminal_wizard(dest: Path) -> None:
    framework = _ask("Framework?", ["fastapi", "flask", "django"], "fastapi")
    instances = _ask("Instances?", ["single", "multi"], "single")
    strictness = _ask("Strictness?", ["public", "internal", "critical"], "internal")
    mode = _ask("Mode?", ["observe", "enforce"], "observe")
    ai_mode = "assist" if _ask("Enable AI?", ["yes", "no"], "no") == "yes" else "off"
    ai_model = input("AI model (llama3): ").strip() or "llama3"
    ai_api_key = input("AI API key (leave blank if none): ").strip()
    save_path = Path(_ask("Save path", [str(dest)], str(dest)))

    merge_sections(
        save_path,
        starter_config(
            framework=framework,
            instances=instances,
            strictness=strictness,
            mode=mode,
            ai_mode=ai_mode,
            ai_model=ai_model,
            ai_api_key=ai_api_key or None,
        ),
    )
    print(f"wrote config: {save_path}")


def _run_status() -> None:
    cfg = _find_cfg()
    if cfg is None:
        print("missing adiuvare.yaml")
        return
    loaded = load_config(cfg)
    socket_path, snap = _runtime_link()
    print(f"config: {cfg}")
    if socket_path and snap:
        print("runtime: connected")
        print(f"socket: {socket_path}")
        print(f"backend: {snap.get('backend', loaded.runtime.backend)}")
        print(f"framework: {loaded.meta.framework}")
        print(f"instances: {loaded.meta.instances}")
        print(f"observe_only: {snap.get('observe_only', loaded.runtime.observe_only)}")
        print(f"ai_mode: {snap.get('ai_mode', loaded.ai.mode)}")
        print(f"banned_ips: {snap.get('banned_ip_count', 0)}")
        print(f"recent_events: {snap.get('recent_events', 0)}")
        return

    print("runtime: offline")
    print(f"framework: {loaded.meta.framework}")
    print(f"instances: {loaded.meta.instances}")
    print(f"observe_only: {loaded.runtime.observe_only}")
    print(f"ai_mode: {loaded.ai.mode}")
    print(f"audit_db: {loaded.runtime.audit_db_path}")


def _run_config_set(key: str, value: str) -> None:
    cfg = _find_cfg()
    if cfg is None:
        print("missing adiuvare.yaml", file=sys.stderr)
        raise SystemExit(1)

    raw = yaml.safe_load(cfg.read_text(encoding="utf-8")) or {}
    node = raw
    parts = key.split(".")
    for part in parts[:-1]:
        child = node.get(part)
        if not isinstance(child, dict):
            child = {}
            node[part] = child
        node = child
    node[parts[-1]] = _coerce(value)
    cfg.write_text(yaml.safe_dump(raw, sort_keys=False), encoding="utf-8")


def _run_logs(tail: int) -> None:
    cfg = _must_cfg()
    loaded = load_config(cfg)
    audit = AuditLog(loaded.runtime.audit_db_path)
    for row in audit.recent(limit=tail):
        print(f"{row.get('verdict', '?'):8} {row.get('identity', '?')} {row.get('endpoint', '?')}")


def _run_report(save: bool = False) -> None:
    cfg = _must_cfg()
    loaded = load_config(cfg)
    audit = AuditLog(loaded.runtime.audit_db_path)
    rows = audit.recent(limit=200)
    counts = Counter(str(row.get("verdict", "allow")) for row in rows)
    top_ids = Counter(str(row.get("identity", "?")) for row in rows).most_common(5)
    lines = [
        "# Adiuvare report",
        "",
        f"- rows: {len(rows)}",
        f"- allow: {counts.get('allow', 0)}",
        f"- flag: {counts.get('flag', 0)}",
        f"- throttle: {counts.get('throttle', 0)}",
        f"- block: {counts.get('block', 0)}",
        "",
        "## busiest identities",
    ]
    for identity, count in top_ids:
        lines.append(f"- {identity}: {count}")
    report = "\n".join(lines)
    print(report)
    if save:
        Path("adiuvare_report.md").write_text(report, encoding="utf-8")


def _run_ip_ban(ip: str) -> None:
    res = _runtime_command("ban_ip", {"ip": ip})
    print(f"banned ip: {res['ip']}")
    print(f"banned_ips: {res.get('banned_ip_count', '?')}")


def _run_ip_unban(ip: str) -> None:
    res = _runtime_command("unban_ip", {"ip": ip})
    print(f"unbanned ip: {res['ip']}")
    print(f"banned_ips: {res.get('banned_ip_count', '?')}")


def _find_cfg() -> Path | None:
    return find_config_file()


def _must_cfg() -> Path:
    cfg = _find_cfg()
    if cfg is None:
        print("missing adiuvare.yaml", file=sys.stderr)
        raise SystemExit(1)
    return cfg


def _coerce(value: str) -> Any:
    low = value.lower()
    if low == "true":
        return True
    if low == "false":
        return False
    try:
        if "." in value:
            return float(value)
        return int(value)
    except ValueError:
        return value


def _ask(prompt: str, options: list[str], default: str) -> str:
    answer = input(f"{prompt} [{' / '.join(options)}] ({default}): ").strip().lower()
    return answer if answer in options else default


def _runtime_link() -> tuple[str | None, dict[str, Any] | None]:
    socket_path = _find_socket()
    if not socket_path:
        return None, None

    snap = _runtime_snap(socket_path)
    if snap is None:
        return None, None
    return socket_path, snap


def _find_socket() -> str | None:
    base = Path(tempfile.gettempdir())
    matches = sorted(
        base.glob("adiuvare*.sock"),
        key=lambda item: item.stat().st_mtime,
        reverse=True,
    )
    return str(matches[0]) if matches else None


def _runtime_snap(socket_path: str) -> dict[str, Any] | None:
    async def call() -> dict[str, Any]:
        client = EventStreamClient(socket_path)
        return await client.command("get_runtime_snapshot", {})

    try:
        return asyncio.run(call())
    except Exception:
        return None


def _runtime_command(name: str, args: dict[str, Any]) -> dict[str, Any]:
    socket_path = _find_socket()
    if not socket_path:
        print("runtime: offline", file=sys.stderr)
        raise SystemExit(1)

    async def call() -> dict[str, Any]:
        client = EventStreamClient(socket_path)
        return await client.command(name, args)

    try:
        return asyncio.run(call())
    except Exception as exc:
        print(f"runtime command failed: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc


if __name__ == "__main__":
    main()
