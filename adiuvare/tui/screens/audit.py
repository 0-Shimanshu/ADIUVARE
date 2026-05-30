import json
from pathlib import Path
from typing import TYPE_CHECKING, cast

from rich.text import Text
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, HorizontalScroll, Vertical
from textual.widgets import Button, DataTable, Input, Static

from ..operator_actions import (
    ActionAvailability,
    apply_action_availability,
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


class AuditScreen(WorkspaceView):
    shortcut_hints = "[1-7] tabs  [f] filter  [e] export JSONL  [up/down] navigate"
    primary_id = "audit-table"
    search_id = "audit-identity-filter"

    BINDINGS = [
        Binding("f", "focus_filter", "Filter", show=False),
        Binding("e", "export_jsonl", "Export", show=False),
    ]

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self._rows: list[dict] = []
        self._selected: dict | None = None

    def compose(self) -> ComposeResult:
        with Vertical(id="audit-outer"):
            yield Static(
                f"[{PALETTE['cyan']}]AUDIT LOG[/]  "
                f"[{PALETTE['dim']}]Full recent history including allow rows - broader than the Events review queue[/]",
                id="audit-header-notice",
            )
            with Horizontal(id="audit-filter-bar"):
                yield Static(f"[{PALETTE['very_dim']}]FILTER[/]", id="audit-filter-label")
                yield Input(placeholder="identity filter...", id="audit-identity-filter")
                yield Input(placeholder="allow / flag / throttle / block / all", id="audit-verdict-filter")
                yield Button("Search", id="audit-search-btn")
                yield Static("", id="audit-filter-stats")
            with Horizontal(id="audit-body"):
                yield DataTable(id="audit-table")
                with Vertical(id="audit-right-col"):
                    yield Static("", id="audit-detail-panel")
                    with HorizontalScroll(id="audit-action-bar"):
                        yield Button("Ban IP", id="audit-ban-ip", classes="confirm")
                        yield Button("Unban IP", id="audit-unban-ip", classes="outline")
                        yield Button("Monitor", id="audit-monitor", classes="warning")
                        yield Button("Unmonitor", id="audit-unmonitor", classes="outline")
                        yield Button("Whitelist", id="audit-whitelist", classes="success")
                        yield Button("Export JSON", id="audit-export-btn", classes="danger")
                        yield Static("", id="audit-action-status")

    def on_mount(self) -> None:
        table = self.query_one("#audit-table", DataTable)
        table.cursor_type = "row"
        table.add_columns("AGE", "VERDICT", "SCORE", "IDENTITY", "ENDPOINT", "IP", "DOMINANT")
        self.refresh_view()

    def on_input_changed(self, event: Input.Changed) -> None:
        if event.input.id in {"audit-identity-filter", "audit-verdict-filter"}:
            self.refresh_view()

    def on_key(self, event) -> None:
        if event.key == "escape" and self._has_filter():
            self.query_one("#audit-identity-filter", Input).value = ""
            self.query_one("#audit-verdict-filter", Input).value = ""
            self.refresh_view()
            event.stop()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.disabled:
            return
        button_id = event.button.id
        if button_id == "audit-search-btn":
            self.refresh_view()
        elif button_id == "audit-export-btn":
            self.action_export_jsonl()
        elif button_id == "audit-ban-ip":
            self._action_ban_ip()
        elif button_id == "audit-unban-ip":
            self._action_unban_ip()
        elif button_id == "audit-monitor":
            self._action_monitor()
        elif button_id == "audit-unmonitor":
            self._action_unmonitor()
        elif button_id == "audit-whitelist":
            self._action_whitelist()

    def on_data_table_row_selected(self, event: DataTable.RowSelected) -> None:
        self._select_row(event.cursor_row)

    def on_data_table_row_highlighted(self, event: DataTable.RowHighlighted) -> None:
        self._select_row(event.cursor_row)

    def action_focus_filter(self) -> None:
        self.focus_search()

    def action_export_jsonl(self) -> None:
        out = Path("adiuvare_audit_export.jsonl")
        out.write_text("\n".join(json.dumps(row, default=str) for row in self._rows), encoding="utf-8")
        self._app().set_footer_status(f"exported {out.name}")

    def refresh_view(self) -> None:
        identity_filter = self.query_one("#audit-identity-filter", Input).value.strip().lower()
        verdict_filter = self.query_one("#audit-verdict-filter", Input).value.strip().lower()

        base_rows = self._app().recent_rows(145)
        rows = list(base_rows)
        if identity_filter:
            rows = [row for row in rows if identity_filter in str(row.get("identity", "")).lower()]
        if verdict_filter and verdict_filter != "all":
            rows = [row for row in rows if verdict_filter in str(row.get("verdict", "")).lower()]
        self._rows = rows

        allow_count = sum(1 for row in base_rows if str(row.get("verdict", "allow")) == "allow")
        flag_count = sum(1 for row in base_rows if str(row.get("verdict", "allow")) == "flag")
        throttle_count = sum(1 for row in base_rows if str(row.get("verdict", "allow")) == "throttle")
        block_count = sum(1 for row in base_rows if str(row.get("verdict", "allow")) == "block")
        self.query_one("#audit-filter-stats", Static).update(
            f"[{PALETTE['dim']}]{len(rows)} of {len(base_rows)} events . [/] "
            f"[{PALETTE['green']}]o {allow_count}[/] "
            f"[{PALETTE['orange']}]^ {flag_count}[/] "
            f"[{PALETTE['orange']}]! {throttle_count}[/] "
            f"[{PALETTE['red']}]x {block_count}[/]"
            if base_rows
            else ""
        )

        table = self.query_one("#audit-table", DataTable)
        table.clear(columns=False)
        for row in rows:
            verdict = str(row.get("verdict", "allow"))
            score = float(row.get("score", 0))
            identity = str(row.get("identity", "?"))[:18]
            endpoint = str(row.get("endpoint", "?"))[:28]
            ip = str(row.get("ip", "-") or "-")[:15]
            age = str(row.get("age", "-"))
            dominant = str(row.get("dominant", "-"))
            icon = decision_icon(verdict)
            color = decision_color(verdict)

            table.add_row(
                Text(age, style=PALETTE["dim"]),
                Text(f" {icon} {verdict.upper():<9}", style=f"{color} bold"),
                Text(f"{score:.4f}", style=PALETTE["cyan"]),
                Text(identity, style=PALETTE["text"]),
                Text(endpoint, style=PALETTE["dim"]),
                Text(ip, style=PALETTE["dim"]),
                Text(dominant, style=dominant_color(dominant)),
            )

        self._selected = rows[0] if rows else None
        self._render_detail()
        self._update_actions()

    def footer_status(self) -> str:
        if self._selected:
            return f"Selected: {self._selected.get('identity', '?')}"
        return "Keyboard shortcuts active"

    def _select_row(self, cursor_row: int) -> None:
        if 0 <= cursor_row < len(self._rows):
            self._selected = self._rows[cursor_row]
            self._render_detail()
            self._update_actions()

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

    def _action_monitor(self) -> None:
        if not self._selected or not self._app().connected:
            return
        self._app().monitor_identity(str(self._selected.get("identity", "")))
        self._app().set_footer_status("monitor identity sent")

    def _action_unmonitor(self) -> None:
        if not self._selected or not self._app().connected:
            return
        self._app().unmonitor_identity(str(self._selected.get("identity", "")))
        self._app().set_footer_status("unmonitor identity sent")

    def _action_whitelist(self) -> None:
        if not self._selected or not self._app().connected:
            return
        self._app().whitelist_identity(str(self._selected.get("identity", "")))
        self._app().set_footer_status("whitelist sent")

    def _action_states(self, event: dict | None) -> dict[str, ActionAvailability]:
        has = event is not None
        verdict = str(event.get("verdict", "allow")) if event else "allow"
        ip = str(event.get("ip", "") or "") if event else ""
        has_ip = bool(ip and ip != "-")
        connected = self._app().connected
        select_first = "Select an audit row first"
        runtime = require_runtime_connection

        return {
            "audit-ban-ip": runtime(
                ActionAvailability(has and has_ip, select_first if not has else "No IP on event"),
                connected,
            ),
            "audit-unban-ip": runtime(
                ActionAvailability(has and has_ip, select_first if not has else "No IP on event"),
                connected,
            ),
            "audit-monitor": runtime(ActionAvailability(has, select_first), connected),
            "audit-unmonitor": runtime(ActionAvailability(has, select_first), connected),
            "audit-whitelist": runtime(
                ActionAvailability(
                    has and verdict != "allow",
                    select_first if not has else "Only for non-allow events",
                ),
                connected,
            ),
            "audit-export-btn": ActionAvailability(has, select_first),
        }

    def _update_actions(self) -> None:
        event = self._selected
        states = self._action_states(event)

        for button_id, state in states.items():
            apply_action_availability(self.query_one(f"#{button_id}", Button), state)

        blocked_reasons = [state.reason for state in states.values() if not state.enabled]
        self.query_one("#audit-action-status", Static).update(
            format_action_status(
                connected=self._app().connected,
                selected_label=str(event.get("identity", "?")) if event else None,
                blocked_reasons=blocked_reasons,
            )
        )

    def _render_detail(self) -> None:
        panel = self.query_one("#audit-detail-panel", Static)
        if not self._selected:
            panel.update(f"[{PALETTE['very_dim']}]Select a row to inspect.[/]")
            return

        event = self._selected
        verdict = str(event.get("verdict", "allow"))
        verdict_color = decision_color(verdict)
        score = float(event.get("score", 0))
        detail = event.get("detail") or {}
        breakdown = event.get("breakdown") or {}

        states = self._action_states(event)
        lines = [
            f"[{PALETTE['dim']} bold]EVENT DETAIL[/]",
            "",
            styled_label("Identity", str(event.get("identity", "?"))),
            styled_label("Endpoint", f"[{PALETTE['dim']}]{event.get('endpoint', '?')}[/]"),
            styled_label("IP", str(event.get("ip", "-") or "-")),
            f"[{PALETTE['dim']}]Score         [/] {render_score_bar(score)} [{PALETTE['cyan']}]{score:.4f}[/]",
            styled_label("Verdict", f"[{verdict_color}]{decision_icon(verdict)} {verdict.upper()}[/]"),
            styled_label("Mode", str(event.get("mode", "enforce"))),
            styled_label("Dominant", f"[{PALETTE['cyan']}]{event.get('dominant', '-')}[/]"),
        ]

        if isinstance(breakdown, dict) and breakdown:
            lines.extend(["", styled_separator(), f"[{PALETTE['very_dim']}]SIGNAL BREAKDOWN[/]", ""])
            peak = max(breakdown.values()) if breakdown.values() else 1.0
            for name, value in sorted(breakdown.items(), key=lambda item: item[1], reverse=True):
                value_f = float(value)
                bar = render_signal_bar(value_f, peak, 14)
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

        unavailable = [state.reason for state in states.values() if not state.enabled and state.reason]
        if unavailable:
            lines.extend([
                "",
                styled_separator(),
                f"[{PALETTE['very_dim']}]ACTION NOTES[/]",
                f"  [{PALETTE['very_dim']}]Unavailable: {unavailable[0]}[/]"
                + (f" (+{len(unavailable) - 1} more)" if len(unavailable) > 1 else ""),
            ])

        panel.update("\n".join(lines))

    def _has_filter(self) -> bool:
        return any(
            self.query_one(f"#{field}", Input).value.strip()
            for field in ("audit-identity-filter", "audit-verdict-filter")
        )

    def _app(self):
        return cast("AdiuvareApp", self.app)
