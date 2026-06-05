import json
from typing import TYPE_CHECKING, cast

from rich.text import Text
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.widgets import Button, DataTable, Input, Static

from ..workspace import PALETTE, WorkspaceView, styled_label, styled_separator

if TYPE_CHECKING:
    from ..app import AdiuvareApp


class ChangesScreen(WorkspaceView):
    shortcut_hints = "[1-7] tabs  [f] filter  [up/down] navigate  [auto 3s]"
    primary_id = "changes-table"
    search_id = "changes-search-filter"

    BINDINGS = [
        Binding("f", "focus_filter", "Filter", show=False),
    ]

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self._rows: list[dict] = []
        self._selected: dict | None = None

    def compose(self) -> ComposeResult:
        with Vertical(id="changes-outer"):
            yield Static(
                f"[{PALETTE['cyan']}]RECENT CHANGES[/]  "
                f"[{PALETTE['dim']}]Operator actions, config writes, runtime patches, and control-plane history[/]",
                id="changes-header-notice",
            )
            with Horizontal(id="changes-filter-bar"):
                yield Static(f"[{PALETTE['very_dim']}]FILTER[/]", id="changes-filter-label")
                yield Input(placeholder="identity / ip / summary...", id="changes-search-filter")
                yield Input(placeholder="kind", id="changes-kind-filter")
                yield Button("Search", id="changes-search-btn")
                yield Static("", id="changes-filter-stats")
            with Horizontal(id="changes-body"):
                yield DataTable(id="changes-table")
                with VerticalScroll(id="changes-detail-scroll"):
                    yield Static("", id="changes-detail-panel")

    def on_mount(self) -> None:
        table = self.query_one("#changes-table", DataTable)
        table.cursor_type = "row"
        table.add_columns("AGE", "KIND", "TARGET", "SUMMARY")
        self.refresh_view()

    def on_input_changed(self, event: Input.Changed) -> None:
        if event.input.id in {"changes-search-filter", "changes-kind-filter"}:
            self.refresh_view()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "changes-search-btn":
            self.refresh_view()

    def on_data_table_row_selected(self, event: DataTable.RowSelected) -> None:
        self._select_row(event.cursor_row)

    def on_data_table_row_highlighted(self, event: DataTable.RowHighlighted) -> None:
        self._select_row(event.cursor_row)

    def action_focus_filter(self) -> None:
        self.focus_search()

    def refresh_view(self) -> None:
        search = self.query_one("#changes-search-filter", Input).value.strip().lower()
        kind_filter = self.query_one("#changes-kind-filter", Input).value.strip().lower()

        base_rows = self._app().recent_changes(145)
        rows = list(base_rows)
        if kind_filter:
            rows = [row for row in rows if kind_filter in str(row.get("kind", "")).lower()]
        if search:
            rows = [
                row
                for row in rows
                if search in str(row.get("target", "")).lower()
                or search in str(row.get("summary", "")).lower()
                or search in json.dumps(row.get("patch", {}), default=str).lower()
            ]

        self._rows = rows
        self.query_one("#changes-filter-stats", Static).update(
            f"[{PALETTE['dim']}]Showing {len(rows)} of {len(base_rows)} change entries[/]"
            if base_rows
            else f"[{PALETTE['very_dim']}]No change entries yet[/]"
        )

        table = self.query_one("#changes-table", DataTable)
        table.clear(columns=False)
        for row in rows:
            kind = str(row.get("kind", "patch")).replace("_", " ")
            target = str(row.get("target", "-"))[:20]
            summary = str(row.get("summary", ""))[:62]
            age = str(row.get("age", "-"))
            kind_color = PALETTE["cyan"] if kind == "patch config" else PALETTE["orange"]
            if "ban ip" in kind or "confirm block" in kind:
                kind_color = PALETTE["red"]
            elif "whitelist" in kind or "monitor" in kind:
                kind_color = PALETTE["green"] if "un" not in kind else PALETTE["orange"]

            table.add_row(
                Text(age, style=PALETTE["dim"]),
                Text(kind, style=kind_color),
                Text(target, style=PALETTE["text"]),
                Text(summary, style=PALETTE["dim"]),
            )

        self._selected = rows[0] if rows else None
        self._render_detail()

    def footer_status(self) -> str:
        if self._selected:
            return f"Selected: {self._selected.get('kind', 'patch')}"
        return "Keyboard shortcuts active"

    def _select_row(self, cursor_row: int) -> None:
        if 0 <= cursor_row < len(self._rows):
            self._selected = self._rows[cursor_row]
            self._render_detail()

    def _render_detail(self) -> None:
        panel = self.query_one("#changes-detail-panel", Static)
        if not self._selected:
            panel.update(f"[{PALETTE['very_dim']}]Select a change entry to inspect.[/]")
            return

        row = self._selected
        patch = row.get("patch", {})
        pretty_patch = json.dumps(patch, indent=2, default=str) if isinstance(patch, dict) else str(patch)
        kind = str(row.get("kind", "patch"))
        kind_label = kind.replace("_", " ")

        lines = [
            f"[{PALETTE['dim']} bold]CHANGE DETAIL[/]",
            "",
            styled_label("Kind", kind_label, PALETTE["cyan"]),
            styled_label("Age", str(row.get("age", "-"))),
            styled_label("Recorded", str(row.get("created_at", "-")), PALETTE["dim"]),
            styled_label("Target", str(row.get("target", "-"))),
            "",
            styled_separator(),
            f"[{PALETTE['very_dim']}]SUMMARY[/]",
            "",
            f"[{PALETTE['text']}]{row.get('summary', '')}[/]",
            "",
            styled_separator(),
            f"[{PALETTE['very_dim']}]PATCH[/]",
            "",
            f"[{PALETTE['dim']}]{pretty_patch}[/]",
        ]
        panel.update("\n".join(lines))

    def _app(self):
        return cast("AdiuvareApp", self.app)
