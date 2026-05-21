"""Shared helpers for operator action availability and disabled-state UX."""

from __future__ import annotations

from dataclasses import dataclass

from textual.widgets import Button

from .workspace import PALETTE


DISCONNECTED_RUNTIME_REASON = "Requires live runtime connection"


@dataclass(frozen=True)
class ActionAvailability:
    """Whether an operator action can run and why it is blocked when not."""

    enabled: bool
    reason: str = ""


def require_runtime_connection(state: ActionAvailability, connected: bool) -> ActionAvailability:
    """Block runtime-mutating actions when the TUI is not attached to a live runtime."""

    if connected or not state.enabled:
        return state
    return ActionAvailability(False, DISCONNECTED_RUNTIME_REASON)


def apply_action_availability(button: Button, state: ActionAvailability) -> None:
    """Apply disabled styling and a hover tooltip for one action button."""

    button.disabled = not state.enabled
    if state.enabled:
        button.remove_class("action-unavailable")
        button.tooltip = ""
    else:
        button.add_class("action-unavailable")
        button.tooltip = state.reason or "Unavailable"


def format_action_status(
    *,
    connected: bool,
    selected_label: str | None,
    blocked_reasons: list[str],
) -> str:
    """Build the action-bar hint line shown beside operator buttons."""

    parts: list[str] = []

    if not connected:
        parts.append(
            f"[{PALETTE['orange']}]Disconnected[/] "
            f"[{PALETTE['dim']}]— cached inspection only; runtime actions disabled[/]"
        )

    if selected_label:
        parts.append(f"[{PALETTE['dim']}]Selected: {selected_label}[/]")
    else:
        parts.append(f"[{PALETTE['very_dim']}]Select a row to enable operator actions[/]")

    unique_reasons = list(dict.fromkeys(reason for reason in blocked_reasons if reason))
    if unique_reasons:
        summary = unique_reasons[0]
        if len(unique_reasons) > 1:
            summary = f"{summary} (+{len(unique_reasons) - 1} more)"
        parts.append(f"[{PALETTE['very_dim']}]Unavailable: {summary}[/]")

    return "  ·  ".join(parts)


def format_action_legend_line(label: str, state: ActionAvailability, shortcut: str = "") -> str:
    """Render one entry for the available-actions panel."""

    prefix = f"  [{PALETTE['cyan']}]{shortcut:<3}[/] " if shortcut else "      "
    if state.enabled:
        marker = f"[{PALETTE['green']}]●[/]"
        text_style = PALETTE["text"]
    else:
        marker = f"[{PALETTE['very_dim']}]○[/]"
        text_style = PALETTE["very_dim"]

    line = f"{prefix}{marker} [{text_style}]{label}[/]"
    if not state.enabled and state.reason:
        line += f" [{PALETTE['very_dim']}]— {state.reason}[/]"
    return line
