"""Agent config loader: loads YAML agent configs and registers them in the plugin registry."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, Field

from agentlabx.agents.base import MemoryScope
from agentlabx.core.registry import PluginRegistry, PluginType


class AgentConfig(BaseModel):
    """Pydantic model representing a loaded agent YAML configuration."""

    name: str
    role: str
    system_prompt: str
    tools: list[str] = Field(default_factory=list)
    phases: list[str] = Field(default_factory=list)
    memory_scope: MemoryScope = Field(default_factory=MemoryScope)
    conversation_history_length: int = 10
    confidence_threshold: float | None = None

    model_config = {"arbitrary_types_allowed": True}


class AgentConfigLoader:
    """Loads AgentConfig objects from YAML files and registers them in a PluginRegistry."""

    def load_config(self, path: Path) -> AgentConfig:
        """Load a single agent config from a YAML file."""
        with open(path, encoding="utf-8") as f:
            data: dict[str, Any] = yaml.safe_load(f)

        # Parse memory_scope sub-dict if present
        raw_scope = data.pop("memory_scope", {})
        memory_scope = MemoryScope(
            read=raw_scope.get("read", []),
            write=raw_scope.get("write", []),
            summarize=raw_scope.get("summarize", {}),
        )

        return AgentConfig(memory_scope=memory_scope, **data)

    def load_all(self, directory: Path) -> list[AgentConfig]:
        """Load all YAML agent configs from a directory."""
        configs: list[AgentConfig] = []
        for yaml_path in sorted(directory.glob("*.yaml")):
            configs.append(self.load_config(yaml_path))
        return configs

    def register_all(self, configs: list[AgentConfig], registry: PluginRegistry) -> None:
        """Register each AgentConfig instance under PluginType.AGENT in the registry."""
        for config in configs:
            registry.register(PluginType.AGENT, config.name, config)
