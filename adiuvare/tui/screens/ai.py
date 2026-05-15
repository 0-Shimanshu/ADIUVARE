from typing import TYPE_CHECKING, cast

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.widgets import Button, Input, Static

from ..workspace import (
    PALETTE,
    WorkspaceView,
    decision_color,
    decision_icon,
    render_decision_bar,
    render_signal_bar,
    styled_separator,
)

if TYPE_CHECKING:
    from ..app import AdiuvareApp


class AIScreen(WorkspaceView):
    shortcut_hints = "[1-7] tabs  [a] analyze  [k] ask  [d] 7-day  [0] 30-day"
    primary_id = "ai-7day-btn"

    BINDINGS = [
        Binding("d", "generate_7day", "7-day report", show=False),
        Binding("0", "generate_30day", "30-day report", show=False),
        Binding("a", "switch_analyze", "Analyze", show=False),
        Binding("k", "switch_ask", "Ask", show=False),
    ]

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self._active_subtab = "analyze"
        self._chat_history: list[tuple[str, str, str]] = []
        self._last_report: dict | None = None

    def compose(self) -> ComposeResult:
        with Vertical(id="ai-outer"):
            with Horizontal(id="ai-subtab-bar"):
                yield Button("Analyze", id="ai-sub-analyze", classes="ai-subtab -active")
                yield Button("Ask", id="ai-sub-ask", classes="ai-subtab")
                yield Static("", id="ai-subtab-spacer")

            with Vertical(id="ai-analyze-view"):
                with Horizontal(id="ai-kpi-row"):
                    yield Static("", id="ai-kpi-total", classes="ai-kpi-card")
                    yield Static("", id="ai-kpi-blocked", classes="ai-kpi-card")
                    yield Static("", id="ai-kpi-flagged", classes="ai-kpi-card")
                    yield Static("", id="ai-kpi-blockrate", classes="ai-kpi-card")
                yield Static("", id="ai-source-badge")
                with Horizontal(id="ai-charts-row"):
                    yield Static("", id="ai-chart-decisions", classes="ai-chart-panel")
                    yield Static("", id="ai-chart-signals", classes="ai-chart-panel")
                with Horizontal(id="ai-report-row"):
                    yield Static("", id="ai-summary-panel", classes="ai-report-panel")
                    yield Static("", id="ai-recommendations", classes="ai-report-panel")
                with Horizontal(id="ai-btn-row"):
                    yield Button("7-Day Report", id="ai-7day-btn", classes="confirm")
                    yield Button("30-Day Report", id="ai-30day-btn", classes="outline")
                    yield Static("", id="ai-gen-status")

            with Vertical(id="ai-ask-view"):
                with Horizontal(id="ai-ask-header-row"):
                    yield Static(
                        f"[{PALETTE['purple']} bold]OPERATOR ASSISTANT[/]  "
                        f"[{PALETTE['dim']}]Runtime link, model config, "
                        "and local fallback shown separately[/]",
                        id="ai-chat-header",
                    )
                    yield Static("", id="ai-ask-status")
                yield Static("", id="ai-prompt-hints")
                yield Static("", id="ai-chat-display")
                with Horizontal(id="ai-chat-input-row"):
                    yield Static(f"[{PALETTE['cyan']}]>[/]", id="ai-chat-prompt")
                    yield Input(placeholder="Ask about threats, identities, config...", id="ai-chat-input")
                    yield Button("Send >", id="ai-chat-send", classes="confirm")

    def on_mount(self) -> None:
        self.query_one("#ai-ask-view").display = False
        self._render_dashboard_local()
        self._render_prompt_hints()
        self._render_ask_status()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        button_id = event.button.id or ""
        if button_id == "ai-7day-btn":
            self.action_generate_7day()
        elif button_id == "ai-30day-btn":
            self.action_generate_30day()
        elif button_id == "ai-sub-analyze":
            self.action_switch_analyze()
        elif button_id == "ai-sub-ask":
            self.action_switch_ask()
        elif button_id == "ai-chat-send":
            self._send_chat()

    def on_input_submitted(self, event: Input.Submitted) -> None:
        if event.input.id == "ai-chat-input":
            self._send_chat()

    def action_switch_analyze(self) -> None:
        self._active_subtab = "analyze"
        self._sync_subtabs()

    def action_switch_ask(self) -> None:
        self._active_subtab = "ask"
        self._sync_subtabs()
        self._render_chat()
        self._render_ask_status()

    def action_generate_7day(self) -> None:
        self._request_report(7)

    def action_generate_30day(self) -> None:
        self._request_report(30)

    def refresh_view(self) -> None:
        if self._active_subtab == "analyze":
            self._render_dashboard_local()
        else:
            self._render_ask_status()

    def footer_status(self) -> str:
        if self._last_report:
            return f"Last report source: {self._last_report.get('source', 'unknown')}"
        return "Keyboard shortcuts active"

    def _sync_subtabs(self) -> None:
        analyze_button = self.query_one("#ai-sub-analyze", Button)
        ask_button = self.query_one("#ai-sub-ask", Button)
        analyze_view = self.query_one("#ai-analyze-view")
        ask_view = self.query_one("#ai-ask-view")

        if self._active_subtab == "analyze":
            analyze_button.add_class("-active")
            ask_button.remove_class("-active")
            analyze_view.display = True
            ask_view.display = False
        else:
            analyze_button.remove_class("-active")
            ask_button.add_class("-active")
            analyze_view.display = False
            ask_view.display = True

    def _request_report(self, days: int) -> None:
        self.query_one("#ai-gen-status", Static).update(
            f"[{PALETTE['dim']}]Generating {days}-day report...[/]"
        )
        self.run_worker(self._async_report(days), exclusive=False)

    async def _async_report(self, days: int) -> None:
        try:
            report = await self._app().get_analysis_report(days)
        except Exception:
            report = self._app()._local_analysis_report(days)
        self._last_report = report
        self._render_report(report)

    def _render_dashboard_local(self) -> None:
        report = self._app()._local_analysis_report(7)
        self._last_report = report
        self._render_report(report)

    def _render_report(self, report: dict) -> None:
        source = str(report.get("source", "unknown"))
        total = int(report.get("total", 0))
        blocked = int(report.get("blocked", 0))
        flagged = int(report.get("flagged", 0))
        block_rate = float(report.get("block_rate", 0.0))
        verdicts = report.get("verdicts", {})
        signal_pressure = report.get("signal_pressure", {})
        summary = str(report.get("summary", ""))
        recommendations = [str(item) for item in report.get("recommendations", [])]
        window = int(report.get("window_days", 7))

        source_color = PALETTE["green"] if source == "ai analysis" else PALETTE["orange"]
        self.query_one("#ai-source-badge", Static).update(f"[{source_color} bold]o {source}[/]")

        self.query_one("#ai-kpi-total", Static).update(
            f"[{PALETTE['very_dim']}]EVENTS[/]\n[{PALETTE['white']} bold]{total}[/]"
        )
        self.query_one("#ai-kpi-blocked", Static).update(
            f"[{PALETTE['very_dim']}]BLOCKED[/]\n[{PALETTE['red']} bold]{blocked}[/]"
        )
        self.query_one("#ai-kpi-flagged", Static).update(
            f"[{PALETTE['very_dim']}]FLAGGED[/]\n[{PALETTE['orange']} bold]{flagged}[/]"
        )
        self.query_one("#ai-kpi-blockrate", Static).update(
            f"[{PALETTE['very_dim']}]BLOCK RATE[/]\n[{PALETTE['cyan']} bold]{block_rate:.1f}%[/]"
        )

        max_count = max(verdicts.values()) if verdicts else 1
        decision_lines = [f"[{PALETTE['dim']} bold]DECISION DISTRIBUTION[/]", ""]
        for decision in ("allow", "flag", "throttle", "block"):
            count = int(verdicts.get(decision, 0))
            pct = (count / max(total, 1)) * 100
            color = decision_color(decision)
            icon = decision_icon(decision)
            bar = render_decision_bar(count, max_count, color, 20)
            decision_lines.append(
                f"  [{color}]{icon} {decision:<8}[/] {bar} [{PALETTE['cyan']}]{count:>3}[/] [{PALETTE['very_dim']}]{pct:>5.1f}%[/]"
            )
        self.query_one("#ai-chart-decisions", Static).update("\n".join(decision_lines))

        peak = max(signal_pressure.values()) if signal_pressure else 1.0
        signal_lines = [f"[{PALETTE['dim']} bold]SIGNAL PRESSURE[/]", ""]
        for name in ("payload", "behavior", "identity", "context"):
            value = float(signal_pressure.get(name, 0.0))
            bar = render_signal_bar(value, peak, 20)
            signal_lines.append(f"  [{PALETTE['cyan']}]{name:<10}[/] {bar} [{PALETTE['text']}]{value:>6.1f}[/]")
        self.query_one("#ai-chart-signals", Static).update("\n".join(signal_lines))

        summary_lines = [
            f"[{PALETTE['dim']} bold]SUMMARY[/]",
            "",
            f"[{PALETTE['text']}]{summary}[/]",
            "",
            styled_separator(),
            f"[{source_color}]Source: {source}[/]",
        ]
        self.query_one("#ai-summary-panel", Static).update("\n".join(summary_lines))

        recommendation_lines = [f"[{PALETTE['dim']} bold]RECOMMENDATIONS[/]", ""]
        for index, recommendation in enumerate(recommendations, 1):
            recommendation_lines.append(f"  [{PALETTE['cyan']}]{index:02}[/] [{PALETTE['dim']}]{recommendation}[/]")
        if not recommendations:
            recommendation_lines.append(f"  [{PALETTE['very_dim']}]No recommendations at this time.[/]")
        recommendation_lines.extend(["", f"[{source_color}]Source: {source}[/]"])
        self.query_one("#ai-recommendations", Static).update("\n".join(recommendation_lines))

        self.query_one("#ai-gen-status", Static).update(
            f"[{PALETTE['green']}]ok[/] [{PALETTE['dim']}]{window}-day report . {source}[/]"
        )

    def _render_prompt_hints(self) -> None:
        self.query_one("#ai-prompt-hints", Static).update(
            f"  [{PALETTE['dim']}]Try:[/] "
            f"[{PALETTE['cyan']}]what are the top threats?[/]  "
            f"[{PALETTE['cyan']}]who is most active?[/]  "
            f"[{PALETTE['cyan']}]should I change thresholds?[/]  "
            f"[{PALETTE['cyan']}]explain payload signals[/]"
        )

    def _render_ask_status(self) -> None:
        snap = self._app().runtime_snapshot()
        connected = bool(snap.get("connected", False))
        model = str(snap.get("ai_model") or self._app().config.ai.model)
        conn_color = PALETTE["green"] if connected else PALETTE["orange"]
        conn_text = "connected" if connected else "disconnected"
        self.query_one("#ai-ask-status", Static).update(
            f"[{PALETTE['dim']}]runtime:[/] [{conn_color}]{conn_text}[/]  "
            f"[{PALETTE['dim']}]model:[/] [{PALETTE['cyan']}]{model}[/]  "
            f"[{PALETTE['dim']}]model reach:[/] [{PALETTE['orange']}]not checked[/]  "
            f"[{PALETTE['dim']}]fallback:[/] [{PALETTE['green']}]available[/]"
        )

    def _send_chat(self) -> None:
        input_widget = self.query_one("#ai-chat-input", Input)
        question = input_widget.value.strip()
        if not question:
            return
        input_widget.value = ""
        self._chat_history.append(("user", question, ""))
        self._render_chat()
        self.run_worker(self._async_ask(question), exclusive=False)

    async def _async_ask(self, question: str) -> None:
        try:
            result = await self._app().ask_ai_analyst(question)
        except Exception:
            result = self._app()._local_ask_fallback(question)
        source = str(result.get("source", "unknown"))
        answer = str(result.get("answer", "No answer available."))
        self._chat_history.append(("assistant", answer, source))
        self._render_chat()

    def _render_chat(self) -> None:
        display = self.query_one("#ai-chat-display", Static)
        if not self._chat_history:
            display.update(
                f"\n  [{PALETTE['dim']}]Welcome to the Operator Assistant.[/]\n\n"
                f"  [{PALETTE['very_dim']}]Ask questions about your security posture, threat patterns,[/]\n"
                f"  [{PALETTE['very_dim']}]identity behavior, or configuration recommendations.[/]\n\n"
                f"  [{PALETTE['dim']}]Runtime connection is shown separately from model reachability.[/]\n"
                f"  [{PALETTE['dim']}]Answers use runtime AI when it responds, otherwise local fallback.[/]\n"
            )
            return

        lines: list[str] = []
        for role, message, source in self._chat_history[-12:]:
            if role == "user":
                lines.append(f"  [{PALETTE['cyan']} bold]You >[/]  [{PALETTE['text']}]{message}[/]")
                lines.append("")
                continue

            words = message.split()
            wrapped: list[str] = []
            current = ""
            for word in words:
                if len(current) + len(word) + 1 > 70:
                    wrapped.append(current)
                    current = word
                else:
                    current = f"{current} {word}" if current else word
            if current:
                wrapped.append(current)

            source_color = PALETTE["green"] if source == "ai" else PALETTE["orange"]
            first = True
            for line in wrapped:
                prefix = f"[{PALETTE['purple']} bold]AI <[/]" if first else "    "
                lines.append(f"  {prefix}  [{PALETTE['dim']}]{line}[/]")
                first = False
            lines.append(f"      [{source_color}]source: {source or 'unknown'}[/]")
            lines.append("")
            lines.append(f"  [{PALETTE['very_dim']}]{'-' * 60}[/]")
            lines.append("")

        display.update("\n".join(lines))

    def _app(self):
        return cast("AdiuvareApp", self.app)
