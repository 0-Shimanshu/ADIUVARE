from adiuvare.tui.operator_actions import (
    ActionAvailability,
    DISCONNECTED_RUNTIME_REASON,
    apply_action_availability,
    format_action_status,
    require_runtime_connection,
)


class FakeButton:
    def __init__(self) -> None:
        self.disabled = False
        self.classes: set[str] = set()
        self.tooltip = ""

    def add_class(self, name: str) -> None:
        self.classes.add(name)

    def remove_class(self, name: str) -> None:
        self.classes.discard(name)


def test_apply_action_availability_marks_disabled_state() -> None:
    button = FakeButton()
    apply_action_availability(button, ActionAvailability(False, "No IP on event"))

    assert button.disabled is True
    assert "action-unavailable" in button.classes
    assert button.tooltip == "No IP on event"


def test_require_runtime_connection_blocks_only_when_otherwise_enabled() -> None:
    blocked = require_runtime_connection(ActionAvailability(True), connected=False)
    assert blocked.enabled is False
    assert blocked.reason == DISCONNECTED_RUNTIME_REASON

    kept = require_runtime_connection(ActionAvailability(False, "No IP on event"), connected=False)
    assert kept.reason == "No IP on event"

    live = require_runtime_connection(ActionAvailability(True), connected=True)
    assert live.enabled is True


def test_format_action_status_includes_disconnect_and_reason() -> None:
    text = format_action_status(
        connected=False,
        selected_label="user:1",
        blocked_reasons=["Already blocked", "No IP on event"],
    )

    assert "Disconnected" in text
    assert "runtime actions disabled" in text
    assert "user:1" in text
    assert "Already blocked" in text
    assert "(+1 more)" in text
