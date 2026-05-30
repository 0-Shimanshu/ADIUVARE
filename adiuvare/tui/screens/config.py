from typing import TYPE_CHECKING, cast

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.widgets import Button, Input, Select, Static

from ..workspace import PALETTE, WorkspaceView

if TYPE_CHECKING:
    from ..app import AdiuvareApp


BOOL_OPTIONS = [("True", "True"), ("False", "False")]
AI_MODE_OPTIONS = [("off", "off"), ("assist", "assist"), ("critical", "critical")]
BACKEND_OPTIONS = [("sqlite", "sqlite"), ("redis", "redis")]
STRICTNESS_OPTIONS = [("public", "public"), ("internal", "internal"), ("critical", "critical")]


class ConfigScreen(WorkspaceView):
    shortcut_hints = "[1-7] tabs  [s] save  [t] toggle observe  [Tab] next field"
    primary_id = "cfg-mode-display"

    BINDINGS = [
        Binding("s", "save_config", "Save", show=False),
        Binding("t", "toggle_mode", "Toggle mode", show=False),
    ]

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self._observe = False

    def compose(self) -> ComposeResult:
        with Vertical():
            yield Static(
                f"[{PALETTE['orange']}]![/] [{PALETTE['dim']}]Changes are written to [/] "
                f"[{PALETTE['cyan']}]adiuvare.yaml[/] [{PALETTE['dim']}]. Thresholds, observe mode, and global AI mode patch live when connected.[/]",
                id="config-notice",
            )
            with Horizontal(id="config-outer"):
                with Vertical(id="config-col-left"):
                    with Vertical(classes="config-panel"):
                        yield Static(f"[{PALETTE['dim']} bold]DECISION THRESHOLDS[/]", classes="cfg-label")
                        yield Static(f"[{PALETTE['dim']}]flag < throttle < block[/]")
                        yield Static(f"[{PALETTE['very_dim']}]FLAG[/]", classes="cfg-label")
                        yield Input(id="cfg-flag", classes="cfg-input")
                        yield Static(f"[{PALETTE['very_dim']}]THROTTLE[/]", classes="cfg-label")
                        yield Input(id="cfg-throttle", classes="cfg-input")
                        yield Static(f"[{PALETTE['very_dim']}]BLOCK[/]", classes="cfg-label")
                        yield Input(id="cfg-block", classes="cfg-input")

                    with Vertical(classes="config-panel"):
                        yield Static(f"[{PALETTE['dim']} bold]OPERATING MODE[/]", classes="cfg-label")
                        yield Static("", id="cfg-mode-display")
                        yield Button("[T] Toggle enforce / observe", id="cfg-toggle-btn")

                    with Vertical(classes="config-panel"):
                        yield Static("", id="cfg-history")

                with Vertical(id="config-col-center"):
                    with Vertical(classes="config-panel"):
                        yield Static(f"[{PALETTE['dim']} bold]SIGNAL WEIGHTS[/]", classes="cfg-label")
                        yield Static(f"[{PALETTE['dim']}]Auto-normalised to sum 1.0[/]")
                        yield Static(f"[{PALETTE['very_dim']}]PAYLOAD[/]", classes="cfg-label")
                        yield Input(id="cfg-w-payload", classes="cfg-input")
                        yield Static(f"[{PALETTE['very_dim']}]BEHAVIOR[/]", classes="cfg-label")
                        yield Input(id="cfg-w-behavior", classes="cfg-input")
                        yield Static(f"[{PALETTE['very_dim']}]IDENTITY[/]", classes="cfg-label")
                        yield Input(id="cfg-w-identity", classes="cfg-input")

                    with Vertical(classes="config-panel"):
                        yield Static(f"[{PALETTE['dim']} bold]RUNTIME[/]", classes="cfg-label")
                        yield Static(f"[{PALETTE['very_dim']}]BACKEND[/]", classes="cfg-label")
                        yield Select(options=BACKEND_OPTIONS, id="cfg-backend", classes="cfg-select")
                        yield Static(f"[{PALETTE['very_dim']}]REDIS URL[/]", id="cfg-redis-url-label", classes="cfg-label")
                        yield Input(id="cfg-redis-url", classes="cfg-input", placeholder="redis://localhost:6379")

                    with Vertical(classes="config-panel"):
                        yield Static(f"[{PALETTE['dim']} bold]MONITORED DEFAULTS[/]", classes="cfg-label")
                        yield Static(f"[{PALETTE['very_dim']}]WINDOW (requests)[/]", classes="cfg-label")
                        yield Input(id="cfg-monitored-window", classes="cfg-input")
                        yield Static(f"[{PALETTE['very_dim']}]MULTIPLIER[/]", classes="cfg-label")
                        yield Input(id="cfg-monitored-multiplier", classes="cfg-input")

                    yield Button("[S] Save to adiuvare.yaml", id="cfg-save-btn")

                with Vertical(id="config-col-right"):
                    with Vertical(classes="config-panel"):
                        yield Static(f"[{PALETTE['dim']} bold]AI[/]", classes="cfg-label")
                        yield Static(f"[{PALETTE['very_dim']}]ENABLED[/]", classes="cfg-label")
                        yield Select(options=BOOL_OPTIONS, id="cfg-ai-enabled", classes="cfg-select")
                        yield Static(f"[{PALETTE['very_dim']}]MODE[/]", classes="cfg-label")
                        yield Select(options=AI_MODE_OPTIONS, id="cfg-ai-mode", classes="cfg-select")
                        yield Static(f"[{PALETTE['very_dim']}]MODEL[/]", classes="cfg-label")
                        yield Input(id="cfg-ai-model", classes="cfg-input")
                        yield Static(f"[{PALETTE['very_dim']}]BASE URL[/]", classes="cfg-label")
                        yield Input(id="cfg-ai-base-url", classes="cfg-input", placeholder="http://127.0.0.1:11434")
                        yield Static(f"[{PALETTE['very_dim']}]API KEY[/]", classes="cfg-label")
                        yield Input(id="cfg-ai-api-key", classes="cfg-input", password=True)
                        yield Static(f"[{PALETTE['very_dim']}]TIMEOUT SECS[/]", classes="cfg-label")
                        yield Input(id="cfg-ai-timeout", classes="cfg-input")

                    with Vertical(classes="config-panel"):
                        yield Static(f"[{PALETTE['dim']} bold]PROFILE[/]", classes="cfg-label")
                        yield Static(f"[{PALETTE['very_dim']}]STRICTNESS[/]", classes="cfg-label")
                        yield Select(options=STRICTNESS_OPTIONS, id="cfg-meta-strictness", classes="cfg-select")

                    with Vertical(classes="config-panel"):
                        yield Static(
                            f"[{PALETTE['dim']} bold]NOTES[/]\n\n"
                            f"[{PALETTE['very_dim']}]Thresholds control when verdicts move from allow to flag to throttle to block.\n\n"
                            f"Signal weights control how much each configurable family contributes. Context and ip_rep stay built-in fixed weights.\n\n"
                            f"Thresholds, observe mode, and global AI mode patch live when connected. Most other fields are saved for the next reload/start.\n\n"
                            f"Per-route policy and per-route AI mode shown on Signals stay separate from these global defaults.[/]",
                            id="cfg-notes",
                        )

    def on_mount(self) -> None:
        self.refresh_view()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "cfg-toggle-btn":
            self.action_toggle_mode()
        elif event.button.id == "cfg-save-btn":
            self.action_save_config()

    def on_select_changed(self, event: Select.Changed) -> None:
        if event.select.id == "cfg-backend":
            self._update_redis_visibility()

    def action_save_config(self) -> None:
        try:
            changes = {
                "thresholds": {
                    "flag": float(self.query_one("#cfg-flag", Input).value),
                    "throttle": float(self.query_one("#cfg-throttle", Input).value),
                    "block": float(self.query_one("#cfg-block", Input).value),
                },
                "weights": {
                    "payload": float(self.query_one("#cfg-w-payload", Input).value),
                    "behavior": float(self.query_one("#cfg-w-behavior", Input).value),
                    "identity": float(self.query_one("#cfg-w-identity", Input).value),
                },
                "runtime": {
                    "backend": str(self.query_one("#cfg-backend", Select).value or self._app().config.runtime.backend),
                    "redis_url": self.query_one("#cfg-redis-url", Input).value.strip() or None,
                    "observe_only": self._observe,
                    "monitored_window": int(self.query_one("#cfg-monitored-window", Input).value),
                    "monitored_multiplier": float(self.query_one("#cfg-monitored-multiplier", Input).value),
                },
                "ai": {
                    "enabled": str(self.query_one("#cfg-ai-enabled", Select).value) == "True",
                    "mode": str(self.query_one("#cfg-ai-mode", Select).value or self._app().config.ai.mode),
                    "model": self.query_one("#cfg-ai-model", Input).value.strip() or self._app().config.ai.model,
                    "base_url": self.query_one("#cfg-ai-base-url", Input).value.strip() or "http://127.0.0.1:11434",
                    "api_key": self.query_one("#cfg-ai-api-key", Input).value.strip() or None,
                    "timeout_secs": float(self.query_one("#cfg-ai-timeout", Input).value),
                },
                "meta": {
                    "strictness": str(self.query_one("#cfg-meta-strictness", Select).value or self._app().config.meta.strictness),
                },
            }
        except ValueError:
            self._app().set_footer_status("invalid config value")
            return

        self._app().save_config(changes)
        self.refresh_view()
        self._app().set_footer_status("config saved")

    def action_toggle_mode(self) -> None:
        self._observe = not self._observe
        self._render_mode()
        self._app().set_footer_status("observe mode toggled")

    def refresh_view(self) -> None:
        cfg = self._app().config
        self._observe = cfg.runtime.observe_only

        self.query_one("#cfg-flag", Input).value = str(cfg.thresholds.flag)
        self.query_one("#cfg-throttle", Input).value = str(cfg.thresholds.throttle)
        self.query_one("#cfg-block", Input).value = str(cfg.thresholds.block)

        self.query_one("#cfg-w-payload", Input).value = str(cfg.weights.payload)
        self.query_one("#cfg-w-behavior", Input).value = str(cfg.weights.behavior)
        self.query_one("#cfg-w-identity", Input).value = str(cfg.weights.identity)

        self.query_one("#cfg-backend", Select).value = str(cfg.runtime.backend)
        self.query_one("#cfg-redis-url", Input).value = getattr(cfg.runtime, "redis_url", "") or ""
        self.query_one("#cfg-monitored-window", Input).value = str(getattr(cfg.runtime, "monitored_window", 20))
        self.query_one("#cfg-monitored-multiplier", Input).value = str(getattr(cfg.runtime, "monitored_multiplier", 1.2))

        self.query_one("#cfg-ai-enabled", Select).value = str(cfg.ai.enabled)
        self.query_one("#cfg-ai-mode", Select).value = str(cfg.ai.mode)
        self.query_one("#cfg-ai-model", Input).value = str(cfg.ai.model)
        self.query_one("#cfg-ai-base-url", Input).value = str(getattr(cfg.ai, "base_url", "") or "http://127.0.0.1:11434")
        self.query_one("#cfg-ai-api-key", Input).value = str(getattr(cfg.ai, "api_key", "") or "")
        self.query_one("#cfg-ai-timeout", Input).value = str(getattr(cfg.ai, "timeout_secs", 5.0))

        self.query_one("#cfg-meta-strictness", Select).value = str(cfg.meta.strictness)

        self._render_mode()
        self._render_history()
        self._update_redis_visibility()

    def footer_status(self) -> str:
        return "Keyboard shortcuts active"

    def _render_mode(self) -> None:
        mode_text = "observe" if self._observe else "enforce"
        mode_color = PALETTE["green"] if self._observe else PALETTE["red"]
        self.query_one("#cfg-mode-display", Static).update(
            f"[{PALETTE['dim']}]Current: [/][{mode_color} bold]{mode_text.upper()}[/]"
        )

    def _update_redis_visibility(self) -> None:
        backend = str(self.query_one("#cfg-backend", Select).value)
        redis_label = self.query_one("#cfg-redis-url-label", Static)
        redis_input = self.query_one("#cfg-redis-url", Input)
        if backend == "sqlite":
            redis_label.update(f"[{PALETTE['very_dim']}]REDIS URL  [{PALETTE['very_dim']}](not active)[/][/]")
            redis_input.disabled = True
        else:
            redis_label.update(f"[{PALETTE['very_dim']}]REDIS URL[/]")
            redis_input.disabled = False

    def _render_history(self) -> None:
        lines = [f"[{PALETTE['dim']} bold]RECENT CHANGES[/]", ""]
        rows = self._app().recent_changes(4)

        if rows:
            for row in rows:
                kind = str(row.get("kind", "patch")).replace("_", " ")
                age = str(row.get("age", "-"))
                target = str(row.get("target", "-"))
                summary = str(row.get("summary", ""))
                lines.append(
                    f"[{PALETTE['green']}]+[/] [{PALETTE['dim']}]{age}[/]  "
                    f"[{PALETTE['text']}]{kind}[/]  "
                    f"[{PALETTE['cyan']}]{target}[/]"
                )
                lines.append(f"  [{PALETTE['dim']}]{summary[:64]}[/]")
            lines.extend(["", f"[{PALETTE['very_dim']}]Open 7 Changes for the full timeline.[/]"])
        else:
            lines.append(f"[{PALETTE['very_dim']}]No saved changes yet.[/]")

        self.query_one("#cfg-history", Static).update("\n".join(lines))

    def _app(self):
        return cast("AdiuvareApp", self.app)
