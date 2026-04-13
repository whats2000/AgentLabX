"""Shared pytest fixtures for the AgentLabX test suite."""

from __future__ import annotations

import pytest

from agentlabx.agents.base import MemoryScope
from agentlabx.agents.config_loader import AgentConfig
from agentlabx.core.registry import PluginRegistry, PluginType


@pytest.fixture
def sample_agent_config():
    return AgentConfig(
        name="phd_student",
        role="phd student",
        system_prompt="You are a PhD.",
        memory_scope=MemoryScope(read=["*"], summarize={}, write=["plan"]),
        tools=[],
        phases=[],
    )


@pytest.fixture
def sample_registry(sample_agent_config):
    r = PluginRegistry()
    r.register(PluginType.AGENT, sample_agent_config.name, sample_agent_config)
    return r
