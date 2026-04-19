from __future__ import annotations

from enum import StrEnum
from pathlib import Path

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class BindMode(StrEnum):
    LOOPBACK = "loopback"
    LAN = "lan"


class TLSConfigurationError(Exception):
    """LAN bind requires a valid TLS cert + key pair."""


class AppSettings(BaseSettings):  # type: ignore[explicit-any]
    model_config = SettingsConfigDict(env_prefix="AGENTLABX_", extra="ignore")

    workspace: Path = Field(default_factory=lambda: Path.home() / ".agentlabx")
    bind_mode: BindMode = BindMode.LOOPBACK
    bind_host: str = "127.0.0.1"
    bind_port: int = 8765
    tls_cert: Path | None = None
    tls_key: Path | None = None
    session_max_age_seconds: int = 60 * 60 * 12  # 12 hours
    remember_me_max_age_seconds: int = 60 * 60 * 24 * 30  # 30 days

    # LiteLLM provider names that run locally and need no API key.
    # Override via env: AGENTLABX_LOCAL_PROVIDERS='["ollama","vllm","custom_llm"]'
    local_providers: tuple[str, ...] = ("ollama", "ollama_chat", "vllm")

    @property
    def db_path(self) -> Path:
        return self.workspace / "agentlabx.db"

    @property
    def audit_log_path(self) -> Path:
        return self.workspace / "events" / "audit.jsonl"

    @model_validator(mode="after")
    def _validate_bind_and_tls(self) -> AppSettings:
        if self.bind_mode is BindMode.LAN:
            if self.tls_cert is None or self.tls_key is None:
                raise TLSConfigurationError("LAN bind requires tls_cert and tls_key")
            if not self.tls_cert.exists() or not self.tls_key.exists():
                raise TLSConfigurationError(
                    f"TLS cert/key not found: {self.tls_cert} / {self.tls_key}"
                )
        return self
