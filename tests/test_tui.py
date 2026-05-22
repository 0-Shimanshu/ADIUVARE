import importlib.util
import json
import sqlite3
from pathlib import Path

import pytest

from adiuvare.core.models import AdiuvareEvent


HAS_TEXTUAL = importlib.util.find_spec("textual") is not None

if HAS_TEXTUAL:
    from textual.widgets import Button, ContentSwitcher, DataTable, Input, Select, Static

    from adiuvare.tui.app import AdiuvareApp
    from adiuvare.tui.wizard import SetupWizardApp


@pytest.fixture
def app(tmp_path):
    if not HAS_TEXTUAL:
        pytest.skip("textual not installed")
    cfg = tmp_path / "adiuvare.yaml"
    cfg.write_text(
        "\n".join(
            [
                "runtime:",
                f"  audit_db_path: '{(tmp_path / 'audit.db').as_posix()}'",
                f"  state_db_path: '{(tmp_path / 'state.db').as_posix()}'",
                "ai:",
                "  mode: 'off'",
            ]
        ),
        encoding="utf-8",
    )
    return AdiuvareApp(config_path=str(cfg))


@pytest.fixture
def connected_app(tmp_path, monkeypatch):
    if not HAS_TEXTUAL:
        pytest.skip("textual not installed")

    cfg = tmp_path / "adiuvare.yaml"
    cfg.write_text(
        "\n".join(
            [
                "runtime:",
                f"  audit_db_path: '{(tmp_path / 'audit.db').as_posix()}'",
                f"  state_db_path: '{(tmp_path / 'state.db').as_posix()}'",
                "ai:",
                "  mode: 'assist'",
                "  enabled: true",
                "  model: 'llama3'",
            ]
        ),
        encoding="utf-8",
    )

    async def fake_subscribe(self):
        if False:
            yield {}

    calls = []

    async def fake_command(self, name, args=None):
        payload = args or {}
        calls.append((name, payload))
        if name == "get_runtime_snapshot":
            return {
                "backend": "redis",
                "connected": True,
                "whitelist_size": 2,
                "banned_ip_count": 1,
                "monitored_identity_count": 1,
                "whitelisted_identities": ["safe:user"],
                "banned_ips": ["203.0.113.4"],
                "monitored_identities": ["live:user"],
                "recent_events": 1,
                "ai_mode": "assist",
            }
        if name == "get_route_overview":
            return {
                "routes": [
                    {
                        "route": "POST /review",
                        "status": "active",
                        "sensitivity": "critical",
                        "policy": "auth",
                        "ai_mode": "assist",
                    }
                ]
            }
        if name == "get_analysis_report":
            return {
                "source": "local",
                "stats": {
                    "events": 3,
                    "allow": 1,
                    "flag": 1,
                    "throttle": 0,
                    "block": 1,
                    "flagged": 1,
                    "blocked": 1,
                    "block_rate": 33.3,
                },
                "signal_pressure": [{"signal": "payload", "score": 3.2}],
                "summary": "Connected report summary",
                "recommendations": ["Review payload-heavy routes first."],
                "findings": ["Payload is dominant."],
            }
        if name == "ask_ai_analyst":
            question = str(payload.get("question", ""))
            return {
                "source": "ai",
                "question": question,
                "answer": "Runtime AI answer",
                "window": "7d",
            }
        return {"ok": True}

    monkeypatch.setattr("adiuvare.tui.app.EventStreamClient.subscribe", fake_subscribe)
    monkeypatch.setattr("adiuvare.tui.app.EventStreamClient.command", fake_command)

    app = AdiuvareApp(socket_path="demo.sock", config_path=str(cfg))
    app._stream_rows = [
        {
            "identity": "live:user",
            "endpoint": "POST /review",
            "ip": "203.0.113.4",
            "score": 0.91,
            "verdict": "block",
            "created_at": "2026-05-05T10:00:00+00:00",
            "breakdown": {"payload": 0.91},
            "detail": {"ai": {"verdict": "malicious", "confidence": 0.92}},
        }
    ]
    app._test_calls = calls
    return app


@pytest.mark.asyncio
async def test_tui_starts_on_monitor(app):
    async with app.run_test() as _pilot:
        switcher = app.query_one("#body-switcher", ContentSwitcher)
        assert switcher.current == "monitor-view"
        assert app.query_one("#tab-monitor", Button).has_class("-active")


@pytest.mark.asyncio
async def test_tui_switches_tabs(app):
    async with app.run_test() as pilot:
        await pilot.press("5")
        switcher = app.query_one("#body-switcher", ContentSwitcher)
        assert switcher.current == "ai-view"
        assert app.query_one("#tab-ai", Button).has_class("-active")

        await pilot.press("6")
        assert switcher.current == "audit-view"
        assert app.query_one("#tab-audit", Button).has_class("-active")

        await pilot.press("7")
        assert switcher.current == "changes-view"
        assert app.query_one("#tab-changes", Button).has_class("-active")


@pytest.mark.asyncio
async def test_monitor_reads_recent_audit_rows(app):
    app.audit.write(
        AdiuvareEvent(
            identity="user:1",
            endpoint="GET /login",
            score=0.74,
            verdict="flag",
            breakdown={"payload": 0.74},
            detail={"ip": "198.51.100.4"},
        )
    )
    async with app.run_test() as _pilot:
        table = app.query_one("#monitor-stream")
        assert table.row_count == 1


def test_recent_rows_backfill_ip_from_same_identity_history(app):
    app.audit.write(
        AdiuvareEvent(
            identity="user:shadow",
            endpoint="GET /known",
            score=0.42,
            verdict="allow",
            breakdown={"payload": 0.42},
            ip="198.51.100.8",
        )
    )
    with sqlite3.connect(app.audit._db_path) as conn:
        conn.execute(
            """
            insert into audit_events (
                identity,
                endpoint,
                score,
                verdict,
                breakdown_json,
                detail_json
            ) values (?, ?, ?, ?, ?, ?)
            """,
            (
                "user:shadow",
                "GET /missing",
                0.61,
                "throttle",
                json.dumps({"payload": 0.61}),
                json.dumps({}),
            ),
        )
        conn.commit()

    rows = app.recent_rows(2)
    assert rows[0]["identity"] == "user:shadow"
    assert rows[0]["ip"] == "198.51.100.8"


@pytest.mark.asyncio
async def test_connected_monitor_reads_live_stream_rows(connected_app):
    async with connected_app.run_test() as pilot:
        await pilot.pause()
        table = connected_app.query_one("#monitor-stream")
        assert table.row_count == 1
        assert connected_app.runtime_snapshot()["backend"] == "redis"
        assert connected_app.route_overview()[0]["route"] == "POST /review"


@pytest.mark.asyncio
async def test_events_filter_reduces_rows(app):
    app.audit.write(
        AdiuvareEvent(
            identity="user:a",
            endpoint="GET /a",
            score=0.70,
            verdict="flag",
            breakdown={"payload": 0.70},
            detail={"ip": "203.0.113.8"},
        )
    )
    app.audit.write(
        AdiuvareEvent(
            identity="user:b",
            endpoint="GET /b",
            score=0.82,
            verdict="block",
            breakdown={"payload": 0.82},
            detail={"ip": "203.0.113.9"},
        )
    )
    async with app.run_test() as pilot:
        await pilot.press("2")
        field = app.query_one("#events-identity-filter", Input)
        field.value = "user:a"
        await pilot.pause()
        table = app.query_one("#events-table")
        assert table.row_count == 1


@pytest.mark.asyncio
async def test_events_disabled_actions_show_reasons(app):
    app.audit.write(
        AdiuvareEvent(
            identity="user:blocked",
            endpoint="POST /review",
            score=0.91,
            verdict="block",
            breakdown={"payload": 0.91},
            detail={"ip": "203.0.113.4"},
        )
    )
    async with app.run_test() as pilot:
        await pilot.press("2")
        await pilot.pause()

        confirm = app.query_one("#events-confirm", Button)
        unblock = app.query_one("#events-unblock-monitor", Button)
        whitelist = app.query_one("#events-whitelist", Button)
        export_btn = app.query_one("#events-export", Button)
        status = app.query_one("#events-action-status", Static)

        assert confirm.disabled is True
        assert confirm.has_class("action-unavailable")
        assert "Already blocked" in (confirm.tooltip or "")
        assert unblock.disabled is True
        assert "Requires live runtime connection" in (unblock.tooltip or "")
        assert whitelist.disabled is True
        assert export_btn.disabled is False
        status_text = str(status.render())
        assert "Disconnected" in status_text
        assert "runtime actions disabled" in status_text
        assert "Already blocked" in status_text


@pytest.mark.asyncio
async def test_audit_whitelist_disabled_for_allow_rows(app):
    app.audit.write(
        AdiuvareEvent(
            identity="user:safe",
            endpoint="GET /health",
            score=0.05,
            verdict="allow",
            breakdown={"payload": 0.05},
            detail={"ip": "203.0.113.1"},
        )
    )
    async with app.run_test() as pilot:
        await pilot.press("6")
        await pilot.pause()

        whitelist = app.query_one("#audit-whitelist", Button)
        status = app.query_one("#audit-action-status", Static)

        assert whitelist.disabled is True
        assert whitelist.has_class("action-unavailable")
        assert "non-allow" in (whitelist.tooltip or "")
        assert "Unavailable" in str(status.render())


@pytest.mark.asyncio
async def test_connected_events_actions_use_runtime_commands(connected_app):
    async with connected_app.run_test() as pilot:
        await pilot.pause()
        await pilot.press("2")
        connected_app.query_one("#events-whitelist", Button).press()
        connected_app.query_one("#events-monitor", Button).press()
        connected_app.query_one("#events-unmonitor", Button).press()
        connected_app.query_one("#events-unblock-monitor", Button).press()
        connected_app.query_one("#events-ban-ip", Button).press()
        connected_app.query_one("#events-unban-ip", Button).press()
        await pilot.pause()

    assert ("unblock_whitelist", {"identity": "live:user"}) in connected_app._test_calls
    assert ("monitor_identity", {"identity": "live:user"}) in connected_app._test_calls
    assert ("unmonitor_identity", {"identity": "live:user"}) in connected_app._test_calls
    assert ("unblock_monitor", {"identity": "live:user"}) in connected_app._test_calls
    assert ("ban_ip", {"ip": "203.0.113.4"}) in connected_app._test_calls
    assert ("unban_ip", {"ip": "203.0.113.4"}) in connected_app._test_calls


@pytest.mark.asyncio
async def test_f_focuses_events_filter(app):
    async with app.run_test() as pilot:
        await pilot.press("2")
        await pilot.press("f")
        assert app.focused is app.query_one("#events-identity-filter")


@pytest.mark.asyncio
async def test_config_save_updates_yaml(app):
    async with app.run_test() as pilot:
        await pilot.press("3")
        app.query_one("#cfg-block", Input).value = "0.73"
        app.query_one("#cfg-ai-mode", Select).value = "assist"
        app.query_one("#cfg-save-btn", Button).press()
        await pilot.pause()
        saved = Path(app.config_path).read_text(encoding="utf-8")
        assert "block: 0.73" in saved
        assert "mode: assist" in saved


@pytest.mark.asyncio
async def test_connected_config_save_sends_runtime_patch(connected_app):
    async with connected_app.run_test() as pilot:
        await pilot.press("3")
        connected_app.query_one("#cfg-block", Input).value = "0.73"
        connected_app.query_one("#cfg-ai-mode", Select).value = "assist"
        connected_app.query_one("#cfg-save-btn", Button).press()
        await pilot.pause()

    patch_call = next(
        payload for name, payload in connected_app._test_calls if name == "patch_config"
    )
    assert patch_call["changes"]["block_threshold"] == 0.73
    assert patch_call["changes"]["observe_only"] is False
    assert patch_call["changes"]["ai_mode"] == "assist"


@pytest.mark.asyncio
async def test_signals_screen_uses_route_overview(connected_app):
    async with connected_app.run_test() as pilot:
        await pilot.pause()
        await pilot.press("4")
        routes = connected_app.query_one("#signals-routes-table")
        assert routes.row_count == 1
        table = connected_app.query_one("#signals-table")
        assert table.get_cell_at((4, 2)).plain == "0.050"
        assert table.get_cell_at((4, 3)).plain == "ACTIVE"


@pytest.mark.asyncio
async def test_f_focuses_audit_filter(app):
    async with app.run_test() as pilot:
        await pilot.press("6")
        await pilot.press("f")
        assert app.focused is app.query_one("#audit-identity-filter")


@pytest.mark.asyncio
async def test_connected_audit_actions_use_runtime_commands(connected_app):
    async with connected_app.run_test() as pilot:
        await pilot.pause()
        await pilot.press("6")
        connected_app.query_one("#audit-whitelist", Button).press()
        connected_app.query_one("#audit-monitor", Button).press()
        connected_app.query_one("#audit-unmonitor", Button).press()
        connected_app.query_one("#audit-ban-ip", Button).press()
        connected_app.query_one("#audit-unban-ip", Button).press()
        await pilot.pause()

    assert ("unblock_whitelist", {"identity": "live:user"}) in connected_app._test_calls
    assert ("monitor_identity", {"identity": "live:user"}) in connected_app._test_calls
    assert ("unmonitor_identity", {"identity": "live:user"}) in connected_app._test_calls
    assert ("ban_ip", {"ip": "203.0.113.4"}) in connected_app._test_calls
    assert ("unban_ip", {"ip": "203.0.113.4"}) in connected_app._test_calls


@pytest.mark.asyncio
async def test_changes_screen_shows_recent_operator_history(app):
    app.audit.write_patch("monitor_identity", {"identity": "user:7", "requests": 12, "multiplier": 1.3})
    app.audit.write_patch("patch_config", {"thresholds": {"block": 0.77}, "ai": {"mode": "assist"}})

    async with app.run_test() as pilot:
        await pilot.press("7")
        table = app.query_one("#changes-table", DataTable)
        assert table.row_count == 2
        kinds = {table.get_cell_at((index, 1)).plain for index in range(table.row_count)}
        assert "monitor identity" in kinds
        assert "patch config" in kinds
        detail = str(app.query_one("#changes-detail-panel", Static).render())
        assert "CHANGE DETAIL" in detail
        assert "patch config" in detail.lower()


@pytest.mark.asyncio
async def test_ai_screen_uses_runtime_report_and_question(connected_app):
    async with connected_app.run_test() as pilot:
        await pilot.pause()
        await pilot.press("5")
        connected_app.query_one("#ai-7day-btn", Button).press()
        await pilot.pause()
        ai_screen = connected_app.query_one("#ai-view")
        assert ai_screen._last_report["summary"] == "Connected report summary"

        await pilot.press("k")
        ask_status = str(connected_app.query_one("#ai-ask-status", Static).render())
        assert "runtime:" in ask_status
        assert "model reach:" in ask_status
        assert "AI connected" not in ask_status

        connected_app.query_one("#ai-chat-input", Input).value = "what are the top threats?"
        connected_app.query_one("#ai-chat-send", Button).press()
        await pilot.pause()
        assert ai_screen._chat_history[-2] == ("user", "what are the top threats?", "")
        assert ai_screen._chat_history[-1] == ("assistant", "Runtime AI answer", "ai")


@pytest.mark.asyncio
async def test_setup_wizard_uses_selects_and_writes_full_config(tmp_path):
    if not HAS_TEXTUAL:
        pytest.skip("textual not installed")
    dest = tmp_path / "adiuvare.yaml"
    app = SetupWizardApp(dest)

    async with app.run_test() as pilot:
        assert isinstance(app.query_one("#wiz-framework"), Select)
        assert isinstance(app.query_one("#wiz-strict"), Select)
        app.query_one("#wiz-ai", Select).value = "assist"
        app.query_one("#wiz-save", Button).press()
        await pilot.pause()

    saved = Path(dest).read_text(encoding="utf-8")
    assert "weights:" in saved
    assert "thresholds:" in saved
    assert "framework: fastapi" in saved
    assert "mode: assist" in saved
