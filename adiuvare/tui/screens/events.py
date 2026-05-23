from collections import Counter
from typing import TYPE_CHECKING, cast

from rich.text import Text
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, HorizontalScroll, Vertical
from textual.widgets import Button, DataTable, Input, Static

from ..operator_actions import (
    ActionAvailability,
    apply_action_availability,
    format_action_legend_line,
    format_action_status,
    require_runtime_connection,
)
from ..workspace import (
    PALETTE,
    WorkspaceView,
    decision_color,
    decision_icon,
    dominant_color,
    render_score_bar,
    render_signal_bar,
    styled_label,
    styled_separator,
)

if TYPE_CHECKING:
    from ..app import AdiuvareApp


class EventsScreen(WorkspaceView):
    shortcut_hints = "[1-7] tabs  [f] filter  [c] confirm  [w] whitelist  [m] monitor  [e] export"
    primary_id = "events-table"
    search_id = "events-identity-filter"

    BINDINGS = [
        Binding("c", "confirm_block", "Confirm block", show=False),
        Binding("w", "whitelist", "Whitelist", show=False),
        Binding("m", "monitor_identity", "Monitor", show=False),
        Binding("e", "export_json", "Export", show=False),
        Binding("f", "focus_filter", "Filter", show=False),
    ]

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self._rows: list[dict] = []
        self._selected: dict | None = None

    def compose(self) -> ComposeResult:
        with Vertical(id="events-outer"):
            with Horizontal(id="events-filter-bar"):
                yield Static(f"[{PALETTE['very_dim']}]FILTER[/]", id="events-filter-label")
                yield Input(placeholder="identity", id="events-identity-filter")
                yield Input(placeholder="flag / throttle / block", id="events-verdict-filter")
                yield Static("", id="events-filter-stats")
            yield DataTable(id="events-table")
            with Horizontal(id="events-detail-area"):
                yield Static("", id="events-detail-panel")
                yield Static("", id="events-context-panel")
            with HorizontalScroll(id="events-action-bar"):
                yield Button("Confirm Block", id="events-confirm", classes="confirm")
                yield Button("Whitelist", id="events-whitelist", classes="success")
                yield Button("Monitor", id="events-monitor", classes="warning")
                yield Button("Unmonitor", id="events-unmonitor", classes="outline")
                yield Button("Unblock+Monitor", id="events-unblock-monitor", classes="warning")
                yield Button("Ban IP", id="events-ban-ip", classes="confirm")
                yield Button("Unban IP", id="events-unban-ip", classes="outline")
                yield Button("Export JSON", id="events-export", classes="danger")
                yield Static("", id="events-action-status")

    def on_mount(self) -> None:
        table = self.query_one("#events-table", DataTable)
        table.cursor_type = "row"
        table.add_columns("VERDICT", "SCORE", "IDENTITY", "ENDPOINT", "IP", "DOMINANT", "AGE")
        self.refresh_view()

    def on_input_changed(self, event: Input.Changed) -> None:
        if event.input.id in {"events-identity-filter", "events-verdict-filter"}:
            self.refresh_view()

    def on_key(self, event) -> None:
        if event.key == "escape" and self._has_filter():
            self.query_one("#events-identity-filter", Input).value = ""
            self.query_one("#events-verdict-filter", Input).value = ""
            self.refresh_view()
            event.stop()

    def on_data_table_row_selected(self, event: DataTable.RowSelected) -> None:
        self._select_row(event.cursor_row)

    def on_data_table_row_highlighted(self, event: DataTable.RowHighlighted) -> None:
        self._select_row(event.cursor_row)

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if not self._selected or event.button.disabled:
            return
        button_id = event.button.id
        if button_id == "events-confirm":
            self.action_confirm_block()
        elif button_id == "events-whitelist":
            self.action_whitelist()
        elif button_id == "events-monitor":
            self.action_monitor_identity()
        elif button_id == "events-unmonitor":
            self._action_unmonitor()
        elif button_id == "events-unblock-monitor":
            self._action_unblock_monitor()
        elif button_id == "events-ban-ip":
            self._action_ban_ip()
        elif button_id == "events-unban-ip":
            self._action_unban_ip()
        elif button_id == "events-export":
            self.action_export_json()

    def action_confirm_block(self) -> None:
        if not self._selected or not self._app().connected:
            return
        self._app().confirm_block(str(self._selected.get("identity", "")))
        self._app().set_footer_status("confirm block sent")

    def action_whitelist(self) -> None:
        if not self._selected or not self._app().connected:
            return
        self._app().whitelist_identity(str(self._selected.get("identity", "")))
        self._app().set_footer_status("whitelist sent")

    def action_monitor_identity(self) -> None:
        if not self._selected or not self._app().connected:
            return
        self._app().monitor_identity(str(self._selected.get("identity", "")))
        self._app().set_footer_status("monitor identity sent")

    def _action_unmonitor(self) -> None:
        if not self._selected or not self._app().connected:
            return
        self._app().unmonitor_identity(str(self._selected.get("identity", "")))
        self._app().set_footer_status("unmonitor identity sent")

    def _action_unblock_monitor(self) -> None:
        if not self._selected or not self._app().connected:
            return
        self._app().unblock_monitor(str(self._selected.get("identity", "")))
        self._app().set_footer_status("unblock + monitor sent")

    def _action_ban_ip(self) -> None:
        if not self._selected or not self._app().connected:
            return
        ip = str(self._selected.get("ip", ""))
        if ip:
            self._app().ban_ip(ip)
            self._app().set_footer_status(f"ban IP {ip} sent")

    def _action_unban_ip(self) -> None:
        if not self._selected or not self._app().connected:
            return
        ip = str(self._selected.get("ip", ""))
        if ip:
            self._app().unban_ip(ip)
            self._app().set_footer_status(f"unban IP {ip} sent")

    def action_export_json(self) -> None:
        if not self._selected:
            return
        import json
        from pathlib import Path

        out = Path("adiuvare_event_export.json")
        out.write_text(json.dumps(self._selected, indent=2, default=str), encoding="utf-8")
        self._app().set_footer_status(f"exported {out.name}")

    def action_focus_filter(self) -> None:
        self.focus_search()

    def refresh_view(self) -> None:
        identity_filter = self.query_one("#events-identity-filter", Input).value.strip().lower()
        verdict_filter = self.query_one("#events-verdict-filter", Input).value.strip().lower()

        base_rows = [
            row for row in self._app().recent_rows(145)
            if str(row.get("verdict", "allow")) != "allow"
        ]
        rows = list(base_rows)
        if identity_filter:
            rows = [row for row in rows if identity_filter in str(row.get("identity", "")).lower()]
        if verdict_filter:
            rows = [row for row in rows if verdict_filter in str(row.get("verdict", "")).lower()]
        self._rows = rows

        counts = Counter(str(row.get("verdict", "allow")) for row in base_rows)
        flags = counts.get("flag", 0)
        throttles = counts.get("throttle", 0)
        blocks = counts.get("block", 0)
        self.query_one("#events-filter-stats", Static).update(
            f"[{PALETTE['dim']}]Review queue: {len(rows)} of {len(base_rows)} non-allow events . [/] "
            f"[{PALETTE['orange']}]^ {flags}[/] "
            f"[{PALETTE['orange']}]! {throttles}[/] "
            f"[{PALETTE['red']}]x {blocks}[/]"
        )

        table = self.query_one("#events-table", DataTable)
        table.clear(columns=False)
        for row in rows:
            verdict = str(row.get("verdict", "allow"))
            score = float(row.get("score", 0))
            identity = str(row.get("identity", "?"))[:18]
            endpoint = str(row.get("endpoint", "?"))[:28]
            ip = str(row.get("ip", "-") or "-")[:15]
            dominant = str(row.get("dominant", "-"))
            age = str(row.get("age", "-"))
            icon = decision_icon(verdict)
            color = decision_color(verdict)
            table.add_row(
                Text(f" {icon} {verdict.upper():<9}", style=f"{color} bold"),
                Text(f"{score:.4f}", style=PALETTE["cyan"]),
                Text(identity, style=PALETTE["text"]),
                Text(endpoint, style=PALETTE["dim"]),
                Text(ip, style=PALETTE["dim"]),
                Text(dominant, style=dominant_color(dominant)),
                Text(age, style=PALETTE["dim"]),
            )

        self._selected = rows[0] if rows else None
        self._render_detail()
        self._render_context()
        self._update_action_status()

    def footer_status(self) -> str:
        if self._selected:
            return f"Selected: {self._selected.get('identity', '?')}"
        return "Keyboard shortcuts active"

    def _select_row(self, cursor_row: int) -> None:
        if 0 <= cursor_row < len(self._rows):
            self._selected = self._rows[cursor_row]
            self._render_detail()
            self._render_context()
            self._update_action_status()

    def _action_states(self, event: dict | None) -> dict[str, ActionAvailability]:
        has = event is not None
        verdict = str(event.get("verdict", "allow")) if event else "allow"
        ip = str(event.get("ip", "") or "") if event else ""
        has_ip = bool(ip and ip != "-")
        connected = self._app().connected

        select_first = "Select an event row first"
        runtime = require_runtime_connection

        return {
            "events-confirm": runtime(
                ActionAvailability(
                    has and verdict != "block",
                    select_first if not has else "Already blocked",
                ),
                connected,
            ),
            "events-whitelist": runtime(ActionAvailability(has, select_first), connected),
            "events-monitor": runtime(ActionAvailability(has, select_first), connected),
            "events-unmonitor": runtime(ActionAvailability(has, select_first), connected),
            "events-unblock-monitor": runtime(
                ActionAvailability(
                    has and verdict == "block",
                    select_first if not has else "Only for blocked events",
                ),
                connected,
            ),
            "events-ban-ip": runtime(
                ActionAvailability(has and has_ip, select_first if not has else "No IP on event"),
                connected,
            ),
            "events-unban-ip": runtime(
                ActionAvailability(has and has_ip, select_first if not has else "No IP on event"),
                connected,
            ),
            "events-export": ActionAvailability(has, select_first),
        }

    def _update_action_status(self) -> None:
        event = self._selected
        states = self._action_states(event)

        for button_id, state in states.items():
            apply_action_availability(self.query_one(f"#{button_id}", Button), state)

        blocked_reasons = [state.reason for state in states.values() if not state.enabled]
        self.query_one("#events-action-status", Static).update(
            format_action_status(
                connected=self._app().connected,
                selected_label=str(event.get("identity", "?")) if event else None,
                blocked_reasons=blocked_reasons,
            )
        )

    def _render_detail(self) -> None:
        panel = self.query_one("#events-detail-panel", Static)
        if not self._selected:
            panel.update(f"[{PALETTE['very_dim']}]Select an event to view details.[/]")
            return

        event = self._selected
        verdict = str(event.get("verdict", "allow"))
        score = float(event.get("score", 0))
        verdict_color = decision_color(verdict)
        breakdown = event.get("breakdown") or {}
        detail = event.get("detail") or {}

        lines = [
            f"[{PALETTE['dim']} bold]EVENT DETAIL[/]",
            "",
            styled_label("Identity", str(event.get("identity", "?"))),
            styled_label("Endpoint", f"[{PALETTE['dim']}]{event.get('endpoint', '?')}[/]"),
            styled_label("IP", str(event.get("ip", "-") or "-")),
            f"[{PALETTE['dim']}]Score         [/] {render_score_bar(score)} [{PALETTE['cyan']}]{score:.4f}[/]",
            styled_label("Verdict", f"[{verdict_color}]{decision_icon(verdict)} {verdict.upper()}[/]"),
        ]

        if isinstance(breakdown, dict) and breakdown:
            lines.extend(["", styled_separator(), f"[{PALETTE['very_dim']}]SIGNAL BREAKDOWN[/]", ""])
            peak = max(breakdown.values()) if breakdown.values() else 1.0
            for name, value in sorted(breakdown.items(), key=lambda item: item[1], reverse=True):
                value_f = float(value)
                bar = render_signal_bar(value_f, peak, 15)
                lines.append(f"  [{PALETTE['dim']}]{name:<12}[/] {bar} [{PALETTE['cyan']}]{value_f:.4f}[/]")

        ai = detail.get("ai") if isinstance(detail, dict) else None
        if isinstance(ai, dict) and ai:
            lines.extend([
                "",
                styled_separator(),
                f"[{PALETTE['very_dim']}]AI DETAIL[/]",
                styled_label("AI verdict", str(ai.get("verdict", "n/a")), PALETTE["purple"]),
                styled_label("Confidence", f"{ai.get('confidence', 0):.2f}", PALETTE["cyan"]),
            ])

        panel.update("\n".join(lines))

    def _render_context(self) -> None:
        panel = self.query_one("#events-context-panel", Static)
        if not self._selected:
            panel.update("")
            return

        event = self._selected
        identity = str(event.get("identity", "?"))
        verdict = str(event.get("verdict", "allow"))
        ip = str(event.get("ip", "-") or "-")
        snap = self._app().runtime_snapshot()

        monitored = set(str(item) for item in snap.get("monitored_identities", []) or [])
        banned = set(str(item) for item in snap.get("banned_ips", []) or [])
        whitelisted = set(str(item) for item in snap.get("whitelisted_identities", []) or [])

        is_monitored = identity in monitored
        is_blocked = verdict == "block"
        is_banned = ip in banned
        is_whitelisted = identity in whitelisted

        states = self._action_states(event)
        lines = [
            f"[{PALETTE['dim']} bold]IDENTITY CONTEXT[/]",
            "",
            styled_label("Identity", identity),
            f"[{PALETTE['dim']}]Monitored     [/] [{PALETTE['green'] if is_monitored else PALETTE['dim']}]{'yes' if is_monitored else 'no'}[/]",
            f"[{PALETTE['dim']}]Blocked       [/] [{PALETTE['red'] if is_blocked else PALETTE['dim']}]{'yes' if is_blocked else 'no'}[/]",
            f"[{PALETTE['dim']}]Banned IP     [/] [{PALETTE['red'] if is_banned else PALETTE['dim']}]{'yes' if is_banned else 'no'}[/]",
            f"[{PALETTE['dim']}]Whitelisted   [/] [{PALETTE['green'] if is_whitelisted else PALETTE['dim']}]{'yes' if is_whitelisted else 'no'}[/]",
            "",
            styled_separator(),
            f"[{PALETTE['very_dim']}]AVAILABLE ACTIONS[/]",
            f"[{PALETTE['very_dim']}]● ready  ○ unavailable (hover buttons for detail)[/]",
            "",
            format_action_legend_line("Confirm block", states["events-confirm"], "C"),
            format_action_legend_line("Whitelist", states["events-whitelist"], "W"),
            format_action_legend_line("Monitor identity", states["events-monitor"], "M"),
            format_action_legend_line("Unmonitor identity", states["events-unmonitor"]),
            format_action_legend_line("Unblock + monitor", states["events-unblock-monitor"]),
            format_action_legend_line("Ban IP", states["events-ban-ip"]),
            format_action_legend_line("Unban IP", states["events-unban-ip"]),
            format_action_legend_line("Export JSON", states["events-export"], "E"),
        ]
        panel.update("\n".join(lines))

    def _has_filter(self) -> bool:
        return any(
            self.query_one(f"#{field}", Input).value.strip()
            for field in ("events-identity-filter", "events-verdict-filter")
        )

    def _app(self):
        return cast("AdiuvareApp", self.app)
