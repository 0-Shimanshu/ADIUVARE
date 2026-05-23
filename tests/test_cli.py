import sys
import time
from types import SimpleNamespace

import yaml

from adiuvare.cli import _find_cfg, _find_socket, _open_tui, _plain_terminal_wizard, _run_config_set, _run_init, _run_ip_ban, _run_ip_unban, _run_logs, _run_status
from adiuvare.core.models import AdiuvareEvent
from adiuvare.state.audit_log import AuditLog


def test_plain_wizard_writes_yaml(tmp_path, monkeypatch):
    dest = tmp_path / "adiuvare.yaml"
    answers = iter(["fastapi", "single", "internal", "observe", "no", "llama3", "", str(dest)])
    monkeypatch.setattr("builtins.input", lambda _prompt: next(answers))
    _plain_terminal_wizard(dest)
    loaded = yaml.safe_load(dest.read_text(encoding="utf-8"))
    assert loaded["runtime"]["observe_only"] is True
    assert loaded["runtime"]["audit_db_path"] == ".adiuvare/audit.db"
    assert loaded["runtime"]["state_db_path"] == ".adiuvare/state.db"
    assert loaded["ai"]["mode"] == "off"
    assert loaded["ai"]["model"] == "llama3"
    assert loaded["ai"]["api_key"] is None
    assert loaded["thresholds"]["flag"] == 0.25
    assert loaded["thresholds"]["throttle"] == 0.55
    assert loaded["weights"]["payload"] == 0.40
    assert loaded["meta"]["framework"] == "fastapi"
    assert loaded["meta"]["instances"] == "single"
    assert loaded["meta"]["strictness"] == "internal"


def test_plain_wizard_can_store_ai_model_and_key(tmp_path, monkeypatch):
    dest = tmp_path / "adiuvare.yaml"
    answers = iter(
        ["fastapi", "single", "critical", "enforce", "yes", "qwen2.5", "demo-key", str(dest)]
    )
    monkeypatch.setattr("builtins.input", lambda _prompt: next(answers))
    _plain_terminal_wizard(dest)
    loaded = yaml.safe_load(dest.read_text(encoding="utf-8"))
    assert loaded["ai"]["enabled"] is True
    assert loaded["ai"]["mode"] == "assist"
    assert loaded["ai"]["model"] == "qwen2.5"
    assert loaded["ai"]["api_key"] == "demo-key"


def test_run_config_set_patches_nested_value(tmp_path, monkeypatch):
    cfg = tmp_path / "adiuvare.yaml"
    cfg.write_text("thresholds:\n  block: 0.8\n", encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    _run_config_set("thresholds.block", "0.73")
    loaded = yaml.safe_load(cfg.read_text(encoding="utf-8"))
    assert loaded["thresholds"]["block"] == 0.73


def test_run_logs_prints_recent_rows(tmp_path, monkeypatch, capsys):
    cfg = tmp_path / "adiuvare.yaml"
    audit_path = tmp_path / "audit.db"
    cfg.write_text(
        yaml.safe_dump({"runtime": {"audit_db_path": str(audit_path), "state_db_path": str(tmp_path / "state.db")}}),
        encoding="utf-8",
    )
    audit = AuditLog(audit_path)
    audit.write(
        AdiuvareEvent(
            identity="user:1",
            endpoint="GET /health",
            score=0.0,
            verdict="allow",
            breakdown={},
        )
    )
    monkeypatch.chdir(tmp_path)
    _run_logs(5)
    out = capsys.readouterr().out
    assert "user:1" in out
    assert "GET /health" in out


def test_run_status_prints_framework_and_instances(tmp_path, monkeypatch, capsys):
    cfg = tmp_path / "adiuvare.yaml"
    cfg.write_text(
        yaml.safe_dump(
            {
                "runtime": {"audit_db_path": str(tmp_path / "audit.db"), "state_db_path": str(tmp_path / "state.db")},
                "meta": {"framework": "fastapi", "instances": "single"},
                "ai": {"mode": "assist"},
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.chdir(tmp_path)
    _run_status()
    out = capsys.readouterr().out
    assert "framework: fastapi" in out
    assert "instances: single" in out
    assert "runtime: offline" in out


def test_run_init_keeps_existing_file_when_user_declines(tmp_path, monkeypatch, capsys):
    cfg = tmp_path / "adiuvare.yaml"
    cfg.write_text("thresholds:\n  block: 0.8\n", encoding="utf-8")
    monkeypatch.setattr("builtins.input", lambda _prompt: "n")
    _run_init(cfg, no_tui=True)
    assert cfg.read_text(encoding="utf-8") == "thresholds:\n  block: 0.8\n"
    assert "aborted" in capsys.readouterr().out


def test_run_init_warns_before_creating_nested_config(tmp_path, monkeypatch, capsys):
    root_cfg = tmp_path / "adiuvare.yaml"
    root_cfg.write_text("meta:\n  framework: fastapi\n", encoding="utf-8")
    nested = tmp_path / "service" / "adiuvare.yaml"
    nested.parent.mkdir(parents=True)

    monkeypatch.setattr("builtins.input", lambda _prompt: "n")
    _run_init(nested, no_tui=True)

    assert not nested.exists()
    out = capsys.readouterr().out
    assert "found existing config" in out or "aborted" in out


def test_find_socket_picks_newest_marker(tmp_path, monkeypatch):
    older = tmp_path / "adiuvare-old.sock"
    older.write_text("{}", encoding="utf-8")
    time.sleep(0.01)
    newer = tmp_path / "adiuvare-live.sock"
    newer.write_text("{}", encoding="utf-8")

    monkeypatch.setattr("adiuvare.cli.tempfile.gettempdir", lambda: str(tmp_path))
    assert _find_socket() == str(newer)


def test_find_cfg_prefers_env_override(tmp_path, monkeypatch):
    local = tmp_path / "adiuvare.yaml"
    local.write_text("meta:\n  framework: fastapi\n", encoding="utf-8")
    custom = tmp_path / "custom" / "adiuvare.yaml"
    custom.parent.mkdir(parents=True)
    custom.write_text("meta:\n  framework: django\n", encoding="utf-8")

    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("ADIUVARE_CONFIG", str(custom))

    assert _find_cfg() == custom


def test_run_status_uses_runtime_snapshot_when_socket_is_live(tmp_path, monkeypatch, capsys):
    cfg = tmp_path / "adiuvare.yaml"
    cfg.write_text(
        yaml.safe_dump(
            {
                "runtime": {"audit_db_path": str(tmp_path / "audit.db"), "state_db_path": str(tmp_path / "state.db")},
                "meta": {"framework": "fastapi", "instances": "single"},
                "ai": {"mode": "assist"},
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(
        "adiuvare.cli._runtime_link",
        lambda: (
            "demo.sock",
            {
                "backend": "sqlite",
                "observe_only": False,
                "ai_mode": "assist",
                "banned_ip_count": 2,
                "recent_events": 7,
            },
        ),
    )
    _run_status()
    out = capsys.readouterr().out
    assert "runtime: connected" in out
    assert "socket: demo.sock" in out
    assert "banned_ips: 2" in out
    assert "recent_events: 7" in out


def test_open_tui_passes_live_socket_to_app(tmp_path, monkeypatch):
    cfg = tmp_path / "adiuvare.yaml"
    cfg.write_text("runtime:\n  audit_db_path: .adiuvare/audit.db\n  state_db_path: .adiuvare/state.db\n", encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr("adiuvare.cli._runtime_link", lambda: ("demo.sock", {"backend": "sqlite"}))
    seen = {}

    class FakeApp:
        def __init__(self, socket_path=None, config_path=None):
            seen["socket_path"] = socket_path
            seen["config_path"] = config_path

        def run(self):
            seen["ran"] = True

    monkeypatch.setitem(sys.modules, "adiuvare.tui.app", SimpleNamespace(AdiuvareApp=FakeApp))
    _open_tui()
    assert seen["socket_path"] == "demo.sock"
    assert seen["config_path"] == str(cfg)
    assert seen["ran"] is True


def test_run_ip_ban_sends_runtime_command(monkeypatch, capsys):
    monkeypatch.setattr("adiuvare.cli._find_socket", lambda: "demo.sock")

    async def fake_command(self, name, args=None):
        assert name == "ban_ip"
        assert args == {"ip": "203.0.113.4"}
        return {"ok": True, "ip": "203.0.113.4", "banned_ip_count": 1}

    monkeypatch.setattr("adiuvare.cli.EventStreamClient.command", fake_command)
    _run_ip_ban("203.0.113.4")
    out = capsys.readouterr().out
    assert "banned ip: 203.0.113.4" in out
    assert "banned_ips: 1" in out


def test_run_ip_unban_sends_runtime_command(monkeypatch, capsys):
    monkeypatch.setattr("adiuvare.cli._find_socket", lambda: "demo.sock")

    async def fake_command(self, name, args=None):
        assert name == "unban_ip"
        assert args == {"ip": "203.0.113.4"}
        return {"ok": True, "ip": "203.0.113.4", "banned_ip_count": 0}

    monkeypatch.setattr("adiuvare.cli.EventStreamClient.command", fake_command)
    _run_ip_unban("203.0.113.4")
    out = capsys.readouterr().out
    assert "unbanned ip: 203.0.113.4" in out
    assert "banned_ips: 0" in out


def test_run_ip_ban_exits_when_runtime_is_offline(monkeypatch, capsys):
    monkeypatch.setattr("adiuvare.cli._find_socket", lambda: None)

    try:
        _run_ip_ban("203.0.113.4")
    except SystemExit as exc:
        assert exc.code == 1
    else:
        raise AssertionError("expected SystemExit")

    err = capsys.readouterr().err
    assert "runtime: offline" in err
