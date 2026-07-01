from collections import Counter
from typing import TYPE_CHECKING, cast

from rich.console import Group
from rich.table import Table
from rich.text import Text
from textual.css.scalar import Scalar
from textual.layouts.vertical import VerticalLayout
from textual.app import ComposeResult
from textual.binding import Binding
from textual import events
from textual.containers import Horizontal, HorizontalScroll, Vertical, VerticalScroll
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
    styled_separator,
)

if TYPE_CHECKING:
    from ..app import AdiuvareApp


class EventsScreen(WorkspaceView):
    shortcut_hints = "[1-7] tabs  [f] filter  [c] confirm  [w] whitelist  [m] monitor  [e] export"
    primary_id = "events-table"
    search_id = "events-identity-filter"
    responsive_breakpoint = 90

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
            yield Static(
                f"[{PALETTE['cyan']}]EVENTS[/]  "
                f"[{PALETTE['dim']}]Review queue for non-allow events (select a row to inspect + act)[/]",
                id="events-header-notice",
            )
            with Horizontal(id="events-filter-bar"):
                yield Static(f"[{PALETTE['very_dim']}]FILTER[/]", id="events-filter-label")
                yield Input(placeholder="identity", id="events-identity-filter")
                yield Input(placeholder="flag / throttle / block", id="events-verdict-filter")
                yield Static("", id="events-filter-stats")
            with Horizontal(id="events-body"):
                yield DataTable(id="events-table")
                with Vertical(id="events-right-col"):
                    with VerticalScroll(id="events-detail-panel"):
                        yield Static("", id="events-detail-text")
                    with VerticalScroll(id="events-context-panel"):
                        yield Static("", id="events-context-text")
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
        self._apply_responsive_layout()

    def on_resize(self, event: events.Resize) -> None:
        self._apply_responsive_layout()

    def _apply_responsive_layout(self) -> None:
        body = self.query_one("#events-body")
        right_col = self.query_one("#events-right-col")

        if self.size.width <= self.responsive_breakpoint:
            body.styles.set_rule("layout", VerticalLayout())
            right_col.styles.set_rule("width", Scalar.parse("1fr"))
            right_col.styles.set_rule("min_width", Scalar.parse("0"))
        else:
            body.styles.clear_rule("layout")
            right_col.styles.clear_rule("width")
            right_col.styles.clear_rule("min_width")

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
        self._app().set_footer_status("block confirmed")

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
        self._app().set_footer_status("unblock and monitor sent")

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
        panel = self.query_one("#events-detail-text", Static)
        if not self._selected:
            panel.update(f"[{PALETTE['very_dim']}]Select an event to view details.[/]")
            return

        event = self._selected
        verdict = str(event.get("verdict", "allow"))
        score = float(event.get("score", 0))
        verdict_color = decision_color(verdict)
        breakdown = event.get("breakdown") or {}
        detail = event.get("detail") or {}

        title = Text("EVENT DETAIL", style=f"{PALETTE['dim']} bold")
        identity = str(event.get("identity", "?"))
        endpoint = str(event.get("endpoint", "?"))
        ip = str(event.get("ip", "-") or "-")

        kv = Table.grid(padding=(0, 1))
        kv.expand = True
        kv.add_column(style=PALETTE["dim"], no_wrap=True)
        kv.add_column(ratio=1)
        kv.add_row("Identity", Text(identity, style=PALETTE["text"]))
        kv.add_row(
            "Endpoint",
            Text(endpoint, style=PALETTE["dim"], overflow="ellipsis", no_wrap=True),
        )
        kv.add_row("IP", Text(ip, style=PALETTE["dim"]))

        score_line = Text.from_markup(
            (
                f"[{PALETTE['dim']}]Score[/] {render_score_bar(score, 8)} "
                f"[{PALETTE['cyan']}]{score:.4f}[/]  "
                f"[{PALETTE['dim']}]Verdict[/] "
                f"[{verdict_color}]{decision_icon(verdict)} {verdict.upper()}[/]"
            )
        )

        renderables: list[object] = [title, kv, score_line]

        if isinstance(breakdown, dict) and breakdown:
            breakdown_table = Table.grid(padding=(0, 1))
            breakdown_table.expand = True
            breakdown_table.add_column(style=PALETTE["dim"], no_wrap=True)
            breakdown_table.add_column(ratio=1)
            breakdown_table.add_column(justify="right", no_wrap=True, style=PALETTE["cyan"])

            peak = max(breakdown.values()) if breakdown.values() else 1.0
            for name, value in sorted(breakdown.items(), key=lambda item: item[1], reverse=True):
                value_f = float(value)
                bar = render_signal_bar(value_f, peak, 15)
                breakdown_table.add_row(str(name), Text.from_markup(bar), f"{value_f:.4f}")

            renderables.extend(
                [
                    Text(""),
                    Text.from_markup(styled_separator()),
                    Text.from_markup(f"[{PALETTE['very_dim']}]SIGNAL BREAKDOWN[/]"),
                    Text(""),
                    breakdown_table,
                ]
            )

        ai = detail.get("ai") if isinstance(detail, dict) else None
        if isinstance(ai, dict) and ai:
            ai_table = Table.grid(padding=(0, 1))
            ai_table.expand = True
            ai_table.add_column(style=PALETTE["dim"], no_wrap=True)
            ai_table.add_column(ratio=1)
            ai_table.add_row("AI verdict", Text(str(ai.get("verdict", "n/a")), style=PALETTE["purple"]))
            ai_table.add_row("Confidence", Text(f"{ai.get('confidence', 0):.2f}", style=PALETTE["cyan"]))

            renderables.extend(
                [
                    Text(""),
                    Text.from_markup(styled_separator()),
                    Text.from_markup(f"[{PALETTE['very_dim']}]AI DETAIL[/]"),
                    ai_table,
                ]
            )

        panel.update(Group(*renderables))

    def _render_context(self) -> None:
        panel = self.query_one("#events-context-text", Static)
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
        title = Text("IDENTITY CONTEXT", style=f"{PALETTE['dim']} bold")

        context_table = Table.grid(padding=(0, 1))
        context_table.expand = True
        context_table.add_column(style=PALETTE["dim"], no_wrap=True)
        context_table.add_column(ratio=1)
        context_table.add_row("Identity", Text(identity, style=PALETTE["text"]))

        status_line_1 = Text.from_markup(
            (
                f"[{PALETTE['dim']}]Monitored[/] "
                f"[{PALETTE['green'] if is_monitored else PALETTE['dim']}]"
                f"{'yes' if is_monitored else 'no'}[/]   "
                f"[{PALETTE['dim']}]Blocked[/] "
                f"[{PALETTE['red'] if is_blocked else PALETTE['dim']}]"
                f"{'yes' if is_blocked else 'no'}[/]"
            )
        )
        status_line_2 = Text.from_markup(
            (
                f"[{PALETTE['dim']}]Banned IP[/] "
                f"[{PALETTE['red'] if is_banned else PALETTE['dim']}]"
                f"{'yes' if is_banned else 'no'}[/]   "
                f"[{PALETTE['dim']}]Whitelisted[/] "
                f"[{PALETTE['green'] if is_whitelisted else PALETTE['dim']}]"
                f"{'yes' if is_whitelisted else 'no'}[/]"
            )
        )

        action_lines = [
            Text.from_markup(format_action_legend_line("Confirm block", states["events-confirm"], "C")),
            Text.from_markup(format_action_legend_line("Whitelist", states["events-whitelist"], "W")),
            Text.from_markup(format_action_legend_line("Monitor identity", states["events-monitor"], "M")),
            Text.from_markup(format_action_legend_line("Unmonitor identity", states["events-unmonitor"])),
            Text.from_markup(format_action_legend_line("Unblock + monitor", states["events-unblock-monitor"])),
            Text.from_markup(format_action_legend_line("Ban IP", states["events-ban-ip"])),
            Text.from_markup(format_action_legend_line("Unban IP", states["events-unban-ip"])),
            Text.from_markup(format_action_legend_line("Export JSON", states["events-export"], "E")),
        ]

        panel.update(
            Group(
                title,
                context_table,
                status_line_1,
                status_line_2,
                Text(""),
                Text.from_markup(styled_separator()),
                Text.from_markup(f"[{PALETTE['very_dim']}]AVAILABLE ACTIONS[/]"),
                Text.from_markup(f"[{PALETTE['very_dim']}]● ready  ○ unavailable (hover buttons for detail)[/]"),
                Text(""),
                *action_lines,
            )
        )

    def _has_filter(self) -> bool:
        return any(
            self.query_one(f"#{field}", Input).value.strip()
            for field in ("events-identity-filter", "events-verdict-filter")
        )

    def _app(self):
        return cast("AdiuvareApp", self.app)
