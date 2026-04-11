from pathlib import Path

import pytest
import yaml

from agentlabx.core.config import (
    BudgetPolicyConfig,
    ExecutionConfig,
    LabMeetingConfig,
    LLMConfig,
    PipelineConfig,
    ServerConfig,
    Settings,
    StorageConfig,
    load_yaml_config,
)

FIXTURES_DIR = Path(__file__).parent / "fixtures"


@pytest.fixture()
def yaml_config_path(tmp_path: Path) -> Path:
    config = {
        "server": {"host": "127.0.0.1", "port": 9000},
        "llm": {"default_model": "gpt-4o", "cost_ceiling": 5.00},
        "pipeline": {
            "default_sequence": ["literature_review", "experimentation"],
            "max_total_iterations": 20,
        },
    }
    p = tmp_path / "config.yaml"
    p.write_text(yaml.dump(config))
    return p


class TestServerConfig:
    def test_defaults(self):
        cfg = ServerConfig()
        assert cfg.host == "0.0.0.0"
        assert cfg.port == 8000
        assert cfg.cors_origins == ["*"]

    def test_override(self):
        cfg = ServerConfig(host="127.0.0.1", port=9000)
        assert cfg.host == "127.0.0.1"
        assert cfg.port == 9000


class TestLLMConfig:
    def test_defaults(self):
        cfg = LLMConfig()
        assert cfg.default_model == "claude-sonnet-4-6"
        assert cfg.temperature == 0.0
        assert cfg.max_retries == 3
        assert cfg.cost_ceiling == 10.00

    def test_override(self):
        cfg = LLMConfig(default_model="gpt-4o", cost_ceiling=5.00)
        assert cfg.default_model == "gpt-4o"
        assert cfg.cost_ceiling == 5.00


class TestPipelineConfig:
    def test_defaults(self):
        cfg = PipelineConfig()
        assert "literature_review" in cfg.default_sequence
        assert "experimentation" in cfg.default_sequence
        assert cfg.max_total_iterations == 50
        assert cfg.default_mode == "auto"

    def test_custom_sequence(self):
        cfg = PipelineConfig(default_sequence=["plan_formulation", "experimentation"])
        assert cfg.default_sequence == ["plan_formulation", "experimentation"]


class TestExecutionConfig:
    def test_defaults(self):
        cfg = ExecutionConfig()
        assert cfg.backend == "subprocess"
        assert cfg.timeout == 120
        assert cfg.memory_limit == "4g"


class TestStorageConfig:
    def test_defaults(self):
        cfg = StorageConfig()
        assert cfg.backend == "sqlite"
        assert "sqlite" in cfg.database_url
        assert cfg.artifacts_path == "./data/artifacts"


class TestBudgetPolicyConfig:
    def test_defaults(self):
        cfg = BudgetPolicyConfig()
        assert cfg.warning_threshold == 0.7
        assert cfg.critical_threshold == 0.9
        assert cfg.hard_ceiling == 1.0

    def test_validation_ordering(self):
        with pytest.raises(ValueError):
            BudgetPolicyConfig(
                warning_threshold=0.95,
                critical_threshold=0.9,
                hard_ceiling=1.0,
            )


class TestLabMeetingConfig:
    def test_defaults(self):
        cfg = LabMeetingConfig()
        assert cfg.enabled is True
        assert cfg.triggers.consecutive_failures == 3
        assert cfg.max_discussion_rounds == 5


class TestLoadYamlConfig:
    def test_load_valid_yaml(self, yaml_config_path: Path):
        data = load_yaml_config(yaml_config_path)
        assert data["server"]["host"] == "127.0.0.1"
        assert data["llm"]["default_model"] == "gpt-4o"

    def test_load_nonexistent_returns_empty(self, tmp_path: Path):
        data = load_yaml_config(tmp_path / "nonexistent.yaml")
        assert data == {}


class TestSettings:
    def test_default_construction(self):
        settings = Settings()
        assert settings.server.port == 8000
        assert settings.llm.default_model == "claude-sonnet-4-6"
        assert settings.pipeline.max_total_iterations == 50

    def test_from_yaml(self, yaml_config_path: Path):
        settings = Settings.from_yaml(yaml_config_path)
        assert settings.server.host == "127.0.0.1"
        assert settings.server.port == 9000
        assert settings.llm.default_model == "gpt-4o"
        # Non-overridden fields keep defaults
        assert settings.execution.backend == "subprocess"

    def test_env_override(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setenv("AGENTLABX_LLM__DEFAULT_MODEL", "o3-mini")
        settings = Settings()
        assert settings.llm.default_model == "o3-mini"

    def test_merge_session_overrides(self):
        settings = Settings()
        overrides = {
            "llm": {"default_model": "gpt-4o", "cost_ceiling": 5.00},
            "pipeline": {"max_total_iterations": 10},
        }
        merged = settings.merge_session_overrides(overrides)
        assert merged.llm.default_model == "gpt-4o"
        assert merged.llm.cost_ceiling == 5.00
        assert merged.pipeline.max_total_iterations == 10
        # Original unchanged
        assert settings.llm.default_model == "claude-sonnet-4-6"
