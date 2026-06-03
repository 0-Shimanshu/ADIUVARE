from collections import Counter
from typing import TYPE_CHECKING, cast

from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.widgets import Static

from ..widgets.risk_stream import RiskStream
from ..workspace import (
    PALETTE,
    SIGNAL_COLORS,
    WorkspaceView,
    decision_color,
    render_decision_bar,
    render_signal_bar,
)

if TYPE_CHECKING:
    from ..app import AdiuvareApp


class MonitorScreen(WorkspaceView):
    shortcut_hints = "[1-7] tabs  [up/down] scroll  [auto 3s]  [q] quit"
    primary_id = "monitor-stream"

    def compose(self) -> ComposeResult:
        with Horizontal(id="monitor-shell"):
            with Vertical(id="monitor-col-left"):
                yield RiskStream(id="monitor-stream")
            with Vertical(id="monitor-col-right"):
                yield Static("", id="system-status-panel")
                yield Static("", id="band-thresholds-panel")
                yield Static("", id="decision-breakdown-panel")
                yield Static("", id="signal-activity-panel")
                yield Static("", id="top-identities-panel")
                yield Static("", id="hot-endpoints-panel")

    def on_mount(self) -> None:
        self.refresh_view()

    def refresh_view(self) -> None:
        rows = self._app().recent_rows(25)
        all_rows = self._app().recent_rows(145)
        counts = Counter(str(row.get("verdict", "allow")) for row in all_rows)
        total = len(all_rows)

        self.query_one("#monitor-stream", RiskStream).show_events(rows)
        self._render_system_status(total)
        self._render_band_thresholds()
        self._render_decision_breakdown(counts, total)
        self._render_signal_activity(all_rows)
        self._render_top_identities(all_rows)
        self._render_hot_endpoints(all_rows)

    def footer_status(self) -> str:
        return "Keyboard shortcuts active"

    def _render_system_status(self, total: int) -> None:
        snap = self._app().runtime_snapshot()
        live = bool(snap.get("connected", False))
        observe = bool(snap.get("observe_only", False))

        status_text = "connected" if live else "offline"
        status_color = PALETTE["green"] if live else PALETTE["orange"]
        mode_text = "observe" if observe else "enforce"
        mode_color = PALETTE["green"] if observe else PALETTE["red"]
        backend = snap.get("backend", "sqlite")
        ai_mode = snap.get("ai_mode", "off")
        whitelist = snap.get("whitelist_size", 0)
        banned = snap.get("banned_ip_count", 0)
        monitored = snap.get("monitored_identity_count", 0)
        source = "live stream" if self._app()._stream_rows else "cached audit"
        source_color = PALETTE["green"] if self._app()._stream_rows else PALETTE["orange"]

        lines = [
            f"[{PALETTE['dim']} bold]RUNTIME STATUS[/]",
            f"  [{PALETTE['dim']}]Backend       [/] [{PALETTE['cyan']}]{backend}[/]",
            f"  [{PALETTE['dim']}]Status        [/] [{status_color}]{status_text}[/]",
            f"  [{PALETTE['dim']}]Mode          [/] [{mode_color}]{mode_text}[/]",
            f"  [{PALETTE['dim']}]AI mode       [/] [{PALETTE['cyan']}]{ai_mode}[/]",
            f"  [{PALETTE['dim']}]Recent events [/] [{PALETTE['cyan']}]{total}[/]",
            f"  [{PALETTE['dim']}]Whitelist     [/] [{PALETTE['cyan']}]{whitelist}[/]",
            f"  [{PALETTE['dim']}]Banned IPs    [/] [{PALETTE['red']}]{banned}[/]",
            f"  [{PALETTE['dim']}]Monitored     [/] [{PALETTE['orange']}]{monitored}[/]",
            f"  [{PALETTE['dim']}]Source        [/] [{source_color}]{source}[/]",
        ]
        if not live:
            lines.extend(["", f"  [{PALETTE['orange']}]disconnected - showing cached data[/]"])
        self.query_one("#system-status-panel", Static).update("\n".join(lines))

    def _render_band_thresholds(self) -> None:
        snap = self._app().runtime_snapshot()
        lines = [
            f"[{PALETTE['dim']} bold]BAND THRESHOLDS[/]",
            f"  [{PALETTE['dim']}]flag     [/] [{PALETTE['orange']}]{snap.get('flag_threshold', 0.45)}[/]",
            f"  [{PALETTE['dim']}]throttle [/] [{PALETTE['orange']}]{snap.get('throttle_threshold', 0.60)}[/]",
            f"  [{PALETTE['dim']}]block    [/] [{PALETTE['red']}]{snap.get('block_threshold', 0.80)}[/]",
        ]
        self.query_one("#band-thresholds-panel", Static).update("\n".join(lines))

    def _render_signal_activity(self, rows: list[dict]) -> None:
        signal_totals: dict[str, float] = {"payload": 0.0, "behavior": 0.0, "identity": 0.0, "context": 0.0}
        for row in rows:
            for name, score in (row.get("breakdown") or {}).items():
                signal_totals[str(name)] = signal_totals.get(str(name), 0.0) + float(score)

        peak = max(signal_totals.values()) if signal_totals else 1.0
        lines = [f"[{PALETTE['dim']} bold]SIGNAL PRESSURE[/]"]
        for name in ("payload", "behavior", "identity", "context"):
            total = signal_totals.get(name, 0.0)
            color = SIGNAL_COLORS.get(name, PALETTE["orange"])
            bar = render_signal_bar(total, peak, 18)
            lines.append(f"  [{color}]{name:<9}[/] {bar} [{PALETTE['text']}]{total:>6.1f}[/]")
        self.query_one("#signal-activity-panel", Static).update("\n".join(lines))

    def _render_decision_breakdown(self, counts: Counter, total: int) -> None:
        max_count = max(counts.values()) if counts else 1
        lines = [f"[{PALETTE['dim']} bold]DECISIONS[/]"]
        for decision in ("allow", "flag", "throttle", "block"):
            count = counts.get(decision, 0)
            pct = (count / max(total, 1)) * 100
            color = decision_color(decision)
            bar = render_decision_bar(count, max_count, color, 14)
            lines.append(f"  [{color}]{decision:<8}[/] {bar} [{PALETTE['cyan']}]{count:>3}[/] [{PALETTE['dim']}]{pct:.0f}%[/]")
        self.query_one("#decision-breakdown-panel", Static).update("\n".join(lines))

    def _render_top_identities(self, rows: list[dict]) -> None:
        identity_counts: dict[str, int] = {}
        identity_max_score: dict[str, float] = {}
        for row in rows:
            identity = str(row.get("identity", "?"))
            identity_counts[identity] = identity_counts.get(identity, 0) + 1
            score = float(row.get("score", 0))
            if score > identity_max_score.get(identity, 0.0):
                identity_max_score[identity] = score

        top = sorted(identity_counts.items(), key=lambda item: item[1], reverse=True)[:5]
        lines = [f"[{PALETTE['dim']} bold]TOP IDENTITIES[/]"]
        for identity, count in top:
            max_score = identity_max_score.get(identity, 0.0)
            icon_color = PALETTE["red"] if max_score >= 0.7 else PALETTE["orange"] if max_score >= 0.45 else PALETTE["green"]
            icon_char = "x" if max_score >= 0.7 else "!" if max_score >= 0.45 else "o"
            lines.append(f"  [{icon_color}]{icon_char}[/] [{PALETTE['text']}]{identity:<16}[/] [{PALETTE['dim']}]{count:>3}[/]")
        self.query_one("#top-identities-panel", Static).update("\n".join(lines))

    def _render_hot_endpoints(self, rows: list[dict]) -> None:
        endpoint_counts: dict[str, int] = {}
        for row in rows:
            endpoint = str(row.get("endpoint", "?"))
            endpoint_counts[endpoint] = endpoint_counts.get(endpoint, 0) + 1
        top = sorted(endpoint_counts.items(), key=lambda item: item[1], reverse=True)[:5]

        lines = [f"[{PALETTE['dim']} bold]HOT ENDPOINTS[/]"]
        for endpoint, count in top:
            parts = endpoint.split(" ", 1)
            method = parts[0] if len(parts) > 1 else "GET"
            path = parts[1] if len(parts) > 1 else endpoint
            lines.append(f"  [{PALETTE['cyan']}]{count:>3}[/] [{PALETTE['orange']}]{method:<6}[/] [{PALETTE['dim']}]{path}[/]")
        self.query_one("#hot-endpoints-panel", Static).update("\n".join(lines))

    def _app(self):
        return cast("AdiuvareApp", self.app)
