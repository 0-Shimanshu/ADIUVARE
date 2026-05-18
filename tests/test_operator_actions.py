from adiuvare.tui.operator_actions import (
    ActionAvailability,
    apply_action_availability,
    format_action_status,
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


def test_format_action_status_includes_disconnect_and_reason() -> None:
    text = format_action_status(
        connected=False,
        selected_label="user:1",
        blocked_reasons=["Already blocked", "No IP on event"],
    )

    assert "Disconnected" in text
    assert "user:1" in text
    assert "Already blocked" in text
    assert "(+1 more)" in text
