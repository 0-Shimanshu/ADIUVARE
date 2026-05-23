import pytest
from pydantic import ValidationError

from adiuvare.config import SignalWeights, Thresholds, build_snapshot, find_config_file, load_config
from adiuvare.config.schema import AdiuvareConfig, PRESETS


def test_signal_weights_default_shape():
    weights = SignalWeights()
    assert weights.payload == 0.40
    assert weights.behavior == 0.35
    assert weights.identity == 0.25


def test_thresholds_default_shape():
    thresholds = Thresholds()
    assert thresholds.flag == 0.25
    assert thresholds.throttle == 0.55
    assert thresholds.block == 0.80


def test_thresholds_reject_bad_order():
    with pytest.raises(ValueError):
        Thresholds(flag=0.70, throttle=0.50, block=0.80)


def test_adiuvare_config_builds_with_runtime_and_ai():
    cfg = AdiuvareConfig()
    assert cfg.runtime.backend == "sqlite"
    assert cfg.runtime.audit_db_path == ".adiuvare/audit.db"
    assert cfg.runtime.monitored_window == 20
    assert cfg.runtime.monitored_multiplier == 1.2
    assert cfg.ai.mode == "off"
    assert cfg.ai.base_url == "http://127.0.0.1:11434"
    assert cfg.ai.api_key is None
    assert cfg.ai.timeout_secs == 5.0
    assert cfg.meta.framework == "fastapi"


def test_presets_keep_distinct_thresholds():
    assert PRESETS["strict"].thresholds.block == 0.70
    assert PRESETS["balanced"].thresholds.block == 0.80


def test_load_config_reads_yaml(tmp_path):
    cfg_path = tmp_path / "adiuvare.yaml"
    cfg_path.write_text(
        """
runtime:
  backend: redis
  observe_only: true
  monitored_window: 12
  monitored_multiplier: 1.5
weights:
  payload: 0.50
"""
    )

    cfg = load_config(cfg_path)
    assert cfg.runtime.backend == "redis"
    assert cfg.weights.payload == 0.50
    assert cfg.runtime.observe_only is True
    assert cfg.runtime.monitored_window == 12
    assert cfg.runtime.monitored_multiplier == 1.5


def test_load_config_uses_nearest_parent_file(tmp_path, monkeypatch):
    root = tmp_path / "project"
    child = root / "service" / "api"
    child.mkdir(parents=True)
    cfg_path = root / "adiuvare.yaml"
    cfg_path.write_text(
        """
meta:
  framework: flask
runtime:
  backend: redis
""",
        encoding="utf-8",
    )
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.chdir(child)
    monkeypatch.setattr("adiuvare.config.loader.Path.home", lambda: home)

    cfg = load_config()
    assert cfg.meta.framework == "flask"
    assert cfg.runtime.backend == "redis"


def test_find_config_file_prefers_env_override(tmp_path, monkeypatch):
    project = tmp_path / "project"
    child = project / "svc"
    child.mkdir(parents=True)
    (project / "adiuvare.yaml").write_text("meta:\n  framework: flask\n", encoding="utf-8")
    env_cfg = tmp_path / "custom" / "adiuvare.yaml"
    env_cfg.parent.mkdir(parents=True)
    env_cfg.write_text("meta:\n  framework: django\n", encoding="utf-8")

    monkeypatch.chdir(child)
    monkeypatch.setenv("ADIUVARE_CONFIG", str(env_cfg))

    assert find_config_file() == env_cfg


def test_find_config_file_uses_home_fallback(tmp_path, monkeypatch):
    cwd = tmp_path / "project" / "svc"
    cwd.mkdir(parents=True)
    home = tmp_path / "home"
    home.mkdir()
    home_cfg = home / "adiuvare.yaml"
    home_cfg.write_text("meta:\n  framework: django\n", encoding="utf-8")

    monkeypatch.chdir(cwd)
    monkeypatch.setattr("adiuvare.config.loader.Path.home", lambda: home)

    assert find_config_file() == home_cfg


def test_load_config_raises_for_missing_explicit_path(tmp_path):
    missing = tmp_path / "missing.yaml"
    with pytest.raises(FileNotFoundError):
        load_config(missing)


def test_load_config_applies_env_overrides(tmp_path, monkeypatch):
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr("adiuvare.config.loader.Path.home", lambda: home)
    monkeypatch.setenv("ADIUVARE_AI_MODE", "assist")
    monkeypatch.setenv("ADIUVARE_AI_BASE_URL", "http://127.0.0.1:9000")
    monkeypatch.setenv("ADIUVARE_AI_MODEL", "mistral")
    monkeypatch.setenv("ADIUVARE_AI_API_KEY", "demo-key")
    monkeypatch.setenv("ADIUVARE_AI_TIMEOUT_SECS", "12")
    monkeypatch.setenv("ADIUVARE_REDIS_URL", "redis://127.0.0.1:6379/0")
    monkeypatch.setenv("ADIUVARE_BLOCK_THRESHOLD", "0.72")
    cfg = load_config()
    assert cfg.ai.mode == "assist"
    assert cfg.ai.model == "mistral"
    assert cfg.ai.base_url == "http://127.0.0.1:9000"
    assert cfg.ai.api_key == "demo-key"
    assert cfg.ai.timeout_secs == 12.0
    assert cfg.runtime.redis_url == "redis://127.0.0.1:6379/0"
    assert cfg.thresholds.block == 0.72


def test_build_snapshot_pulls_runtime_values():
    snap = build_snapshot(AdiuvareConfig())
    assert snap.payload_weight == 0.40
    assert snap.block_threshold == 0.80


def test_load_config_raises_for_yaml_list(tmp_path):
    cfg_path = tmp_path / "adiuvare.yaml"
    cfg_path.write_text("- hello\n- world\n", encoding="utf-8")
    with pytest.raises(ValueError, match="must contain a top-level mapping/object, got list"):
        load_config(cfg_path)


def test_load_config_raises_for_yaml_string(tmp_path):
    cfg_path = tmp_path / "adiuvare.yaml"
    cfg_path.write_text("just a string\n", encoding="utf-8")
    with pytest.raises(ValueError, match="must contain a top-level mapping/object, got str"):
        load_config(cfg_path)


def test_load_config_raises_for_yaml_integer(tmp_path):
    cfg_path = tmp_path / "adiuvare.yaml"
    cfg_path.write_text("42\n", encoding="utf-8")
    with pytest.raises(ValueError, match="must contain a top-level mapping/object, got int"):
        load_config(cfg_path)


def test_load_config_raises_for_yaml_boolean(tmp_path):
    cfg_path = tmp_path / "adiuvare.yaml"
    cfg_path.write_text("true\n", encoding="utf-8")
    with pytest.raises(ValueError, match="must contain a top-level mapping/object, got bool"):
        load_config(cfg_path)


def test_ai_config_rejects_invalid_mode():
    """A typo like 'assit' must raise ValidationError, not silently disable AI."""
    with pytest.raises(ValidationError): 
        AdiuvareConfig(ai={"mode": "assit"})


def test_ai_config_accepts_all_valid_modes():
    """All four documented modes must be accepted without error."""
    for mode in ("off", "assist", "critical", "async"):
        cfg = AdiuvareConfig(ai={"mode": mode})
        assert cfg.ai.mode == mode


def test_load_config_rejects_invalid_ai_mode_from_yaml(tmp_path):
    """A YAML file with an invalid ai.mode must fail on load, not silently."""
    cfg_path = tmp_path / "adiuvare.yaml"
    cfg_path.write_text("ai:\n  mode: assit\n", encoding="utf-8")
    with pytest.raises(ValidationError):  
        load_config(cfg_path)