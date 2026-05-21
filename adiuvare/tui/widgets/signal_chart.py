"""
Signal chart widget — heat gradient bar visualization.
"""
from textual.widgets import Static

from ..workspace import PALETTE, render_signal_bar, SIGNAL_COLORS


class SignalChart(Static):
    def show_breakdown(self, breakdown: dict[str, float]) -> None:
        if not breakdown:
            self.update(f"[{PALETTE['very_dim']}]No signal pressure yet.[/]")
            return

        peak = max(breakdown.values()) or 1.0
        rows = []
        for name, value in sorted(breakdown.items(), key=lambda item: item[1], reverse=True):
            bar = render_signal_bar(value, peak, 20)
            color = SIGNAL_COLORS.get(name, PALETTE["cyan"])
            rows.append(
                f"[{color}]{name:<10}[/] {bar} "
                f"[{PALETTE['text']}]{value:>6.4f}[/] "
                f"[{PALETTE['cyan']}]{value / peak:.2f}[/]"
            )
        self.update("\n".join(rows))
