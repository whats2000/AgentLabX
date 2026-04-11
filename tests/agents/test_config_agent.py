"""Tests for ConfigAgent — generic agent instantiated from YAML config."""

from __future__ import annotations

from collections import deque
from pathlib import Path

import pytest

from agentlabx.agents.config_agent import ConfigAgent
from agentlabx.agents.config_loader import AgentConfig, AgentConfigLoader
from agentlabx.agents.base import AgentContext, MemoryScope

CONFIGS_DIR = Path(__file__).parent.parent.parent / "agentlabx" / "agents" / "configs"


def make_context(phase: str = "experimentation") -> AgentContext:
    return AgentContext(phase=phase, state={}, working_memory={})


@pytest.fixture
def ml_config() -> AgentConfig:
    return AgentConfigLoader().load_config(CONFIGS_DIR / "ml_engineer.yaml")


@pytest.fixture
def phd_config() -> AgentConfig:
    return AgentConfigLoader().load_config(CONFIGS_DIR / "phd_student.yaml")


class TestConfigAgent:
    def test_create_from_config(self, ml_config):
        agent = ConfigAgent.from_config(ml_config)
        assert agent.name == "ml_engineer"
        assert agent.role == ml_config.role
        assert agent.memory_scope == ml_config.memory_scope

    def test_conversation_history_length(self, ml_config):
        agent = ConfigAgent.from_config(ml_config)
        assert agent.max_history_length == 15

    @pytest.mark.asyncio
    async def test_inference_with_mock(self, ml_config):
        mock_responses = deque(["mocked response"])
        agent = ConfigAgent.from_config(ml_config, mock_responses=mock_responses)
        ctx = make_context()
        result = await agent.inference("test prompt", ctx)
        assert result == "mocked response"

    @pytest.mark.asyncio
    async def test_inference_appends_to_history(self, ml_config):
        mock_responses = deque(["resp1", "resp2"])
        agent = ConfigAgent.from_config(ml_config, mock_responses=mock_responses)
        ctx = make_context()
        await agent.inference("first prompt", ctx)
        await agent.inference("second prompt", ctx)
        # Each call appends user + assistant = 2 entries; 2 calls = 4 entries
        assert len(agent.conversation_history) == 4
        assert agent.conversation_history[0]["role"] == "user"
        assert agent.conversation_history[1]["role"] == "assistant"

    @pytest.mark.asyncio
    async def test_history_truncation(self, ml_config):
        # Create config with max_history_length=2 (means max 2 pairs = 4 entries)
        config_data = ml_config.model_dump()
        config_data["conversation_history_length"] = 2
        config = AgentConfig(**config_data)

        mock_responses = deque(["r1", "r2", "r3"])
        agent = ConfigAgent.from_config(config, mock_responses=mock_responses)
        ctx = make_context()

        await agent.inference("p1", ctx)
        await agent.inference("p2", ctx)
        await agent.inference("p3", ctx)

        # max_history_length=2 means keep last 2 pairs (4 entries max)
        assert len(agent.conversation_history) <= 4

    def test_reset(self, phd_config):
        agent = ConfigAgent.from_config(phd_config)
        agent.conversation_history.append({"role": "user", "content": "hello"})
        agent.working_memory["key"] = "value"
        agent.reset()
        assert agent.conversation_history == []
        assert agent.working_memory == {}
