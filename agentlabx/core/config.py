"""Layered configuration system with Pydantic v2 settings."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class ServerConfig(BaseModel):
    host: str = "0.0.0.0"
    port: int = 8000
    cors_origins: list[str] = ["*"]


class LLMConfig(BaseModel):
    default_model: str = "claude-sonnet-4-6"
    temperature: float = 0.0
    max_retries: int = 3
    cost_ceiling: float = 10.00


class PipelineConfig(BaseModel):
    default_sequence: list[str] = [
        "literature_review",
        "plan_formulation",
        "data_exploration",
        "data_preparation",
        "experimentation",
        "results_interpretation",
        "report_writing",
        "peer_review",
    ]
    max_total_iterations: int = 50
    default_mode: str = "auto"


class ExecutionConfig(BaseModel):
    backend: str = "subprocess"
    timeout: int = 120
    memory_limit: str = "4g"


class StorageConfig(BaseModel):
    backend: str = "sqlite"
    database_url: str = "sqlite:///data/agentlabx.db"
    artifacts_path: str = "./data/artifacts"


class BudgetPolicyConfig(BaseModel):
    warning_threshold: float = 0.7
    critical_threshold: float = 0.9
    hard_ceiling: float = 1.0

    @model_validator(mode="after")
    def validate_ordering(self) -> BudgetPolicyConfig:
        if not (self.warning_threshold <= self.critical_threshold <= self.hard_ceiling):
            msg = (
                f"Budget thresholds must be ordered: "
                f"warning ({self.warning_threshold}) <= "
                f"critical ({self.critical_threshold}) <= "
                f"hard_ceiling ({self.hard_ceiling})"
            )
            raise ValueError(msg)
        return self


class LabMeetingTriggersConfig(BaseModel):
    consecutive_failures: int = 3
    score_plateau_rounds: int = 2
    scheduled_interval: int | None = None


class LabMeetingConfig(BaseModel):
    enabled: bool = True
    triggers: LabMeetingTriggersConfig = LabMeetingTriggersConfig()
    participants: str = "auto"
    max_discussion_rounds: int = 5


def load_yaml_config(path: Path) -> dict[str, Any]:
    """Load a YAML config file. Returns empty dict if file doesn't exist."""
    if not path.exists():
        return {}
    with open(path) as f:
        data = yaml.safe_load(f)
    return data if data is not None else {}


class Settings(BaseSettings):
    """Top-level application settings. Supports layered overrides."""

    model_config = SettingsConfigDict(
        env_prefix="AGENTLABX_",
        env_nested_delimiter="__",
    )

    server: ServerConfig = ServerConfig()
    llm: LLMConfig = LLMConfig()
    pipeline: PipelineConfig = PipelineConfig()
    execution: ExecutionConfig = ExecutionConfig()
    storage: StorageConfig = StorageConfig()
    budget_policy: BudgetPolicyConfig = BudgetPolicyConfig()
    lab_meeting: LabMeetingConfig = LabMeetingConfig()

    @classmethod
    def from_yaml(cls, path: Path) -> Settings:
        """Create Settings from a YAML file, with defaults for missing fields."""
        data = load_yaml_config(path)
        return cls.model_validate(data)

    def merge_session_overrides(self, overrides: dict[str, Any]) -> Settings:
        """Return a new Settings with session-specific overrides merged in.

        Does not mutate the original. Only overrides fields present in the dict.
        """
        base_data = self.model_dump()
        for key, value in overrides.items():
            if key in base_data and isinstance(value, dict):
                base_data[key].update(value)
            else:
                base_data[key] = value
        return Settings.model_validate(base_data)
