from typing import Literal

from pydantic import BaseModel, Field, model_validator


class SignalWeights(BaseModel):
    """Hold the configurable weights for the signal families you can tune."""

    payload: float = Field(default=0.40, ge=0.0, le=1.0)
    behavior: float = Field(default=0.35, ge=0.0, le=1.0)
    identity: float = Field(default=0.25, ge=0.0, le=1.0)


class Thresholds(BaseModel):
    """Define the score cutoffs for flag, throttle, and block."""

    flag: float = Field(default=0.25, ge=0.0, le=1.0)
    throttle: float = Field(default=0.55, ge=0.0, le=1.0)
    block: float = Field(default=0.80, ge=0.0, le=1.0)

    @model_validator(mode="after")
    def check_order(self):
        if not (self.flag <= self.throttle <= self.block):
            raise ValueError("thresholds are out of order")
        return self


class RuntimeConfig(BaseModel):
    """Collect the runtime backend and stateful operator defaults."""

    backend: Literal["memory", "sqlite", "redis"] = "sqlite"
    audit_db_path: str = ".adiuvare/audit.db"
    state_db_path: str = ".adiuvare/state.db"
    redis_url: str | None = None
    observe_only: bool = False
    monitored_window: int = Field(default=20, ge=1, le=1000)
    monitored_multiplier: float = Field(default=1.2, ge=1.0, le=5.0)


class AiConfig(BaseModel):
    """Describe how request-time AI review should reach the model endpoint."""

    enabled: bool = False
    mode: Literal["off", "assist", "critical", "async"] = "off"
    model: str = "llama3"
    base_url: str = "http://127.0.0.1:11434"
    api_key: str | None = None
    timeout_secs: float = Field(default=5.0, gt=0.0, le=120.0)


class MetaConfig(BaseModel):
    """Store setup metadata and the current strictness profile."""

    framework: str = "fastapi"
    instances: str = "single"
    strictness: str = "internal"


class AdiuvareConfig(BaseModel):
    """Collect the config sections loaded from presets, file, and env."""

    weights: SignalWeights = Field(default_factory=SignalWeights)
    thresholds: Thresholds = Field(default_factory=Thresholds)
    runtime: RuntimeConfig = Field(default_factory=RuntimeConfig)
    ai: AiConfig = Field(default_factory=AiConfig)
    meta: MetaConfig = Field(default_factory=MetaConfig)


PRESETS = {
    "balanced": AdiuvareConfig(),
    "strict": AdiuvareConfig(
        thresholds=Thresholds(flag=0.20, throttle=0.45, block=0.70),
        ai=AiConfig(enabled=True, mode="assist"),
    ),
}
