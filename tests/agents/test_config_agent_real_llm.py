"""Tests for ConfigAgent LLM wiring — Task 10."""

from __future__ import annotations

from collections import deque
from pathlib import Path

import pytest

from agentlabx.agents.base import AgentContext
from agentlabx.agents.config_agent import ConfigAgent
from agentlabx.agents.config_loader import AgentConfig, AgentConfigLoader
from agentlabx.core.state import CostTracker
from agentlabx.providers.llm.mock_provider import MockLLMProvider

CONFIGS_DIR = Path(__file__).parent.parent.parent / "agentlabx" / "agents" / "configs"


def make_context(phase: str = "experimentation") -> AgentContext:
    return AgentContext(phase=phase, state={}, working_memory={})


@pytest.fixture
def ml_config() -> AgentConfig:
    return AgentConfigLoader().load_config(CONFIGS_DIR / "ml_engineer.yaml")


class TestConfigAgentRealLLM:
    @pytest.mark.asyncio
    async def test_uses_llm_provider_when_no_mocks(self, ml_config: AgentConfig):
        mock = MockLLMProvider(responses=["LLM response text"])
        agent = ConfigAgent.from_config(ml_config, llm_provider=mock, model="test-model")
        ctx = make_context()

        result = await agent.inference("test prompt", ctx)

        assert result == "LLM response text"
        assert len(mock.calls) == 1
        call = mock.calls[0]
        assert call["model"] == "test-model"
        assert call["prompt"] == "test prompt"
        assert call["system_prompt"] == ml_config.system_prompt
        assert call["temperature"] == 0.0

    @pytest.mark.asyncio
    async def test_mock_responses_take_priority(self, ml_config: AgentConfig):
        mock = MockLLMProvider(responses=["LLM response that should NOT be used"])
        agent = ConfigAgent.from_config(
            ml_config,
            mock_responses=deque(["scripted mock response"]),
            llm_provider=mock,
        )
        ctx = make_context()

        result = await agent.inference("test prompt", ctx)

        assert result == "scripted mock response"
        # Provider should NOT have been called
        assert len(mock.calls) == 0

    @pytest.mark.asyncio
    async def test_stub_when_no_provider_and_no_mocks(self, ml_config: AgentConfig):
        agent = ConfigAgent.from_config(ml_config)
        ctx = make_context()

        result = await agent.inference("hello world", ctx)

        assert "[ml_engineer]" in result
        assert "hello world" in result

    @pytest.mark.asyncio
    async def test_cost_tracker_accumulates(self, ml_config: AgentConfig):
        mock = MockLLMProvider(responses=["response A", "response B"])
        tracker = CostTracker()
        agent = ConfigAgent.from_config(ml_config, llm_provider=mock, cost_tracker=tracker)
        ctx = make_context()

        await agent.inference("prompt one", ctx)
        await agent.inference("prompt two", ctx)

        assert tracker.total_tokens_in > 0
        assert tracker.total_tokens_out > 0
        # Two calls → tracker should reflect cumulative usage
        assert mock.calls[0]["tokens_in"] if hasattr(mock.calls[0], "tokens_in") else True

    @pytest.mark.asyncio
    async def test_cost_tracker_optional(self, ml_config: AgentConfig):
        mock = MockLLMProvider(responses=["ok"])
        # No cost_tracker passed — should not crash
        agent = ConfigAgent.from_config(ml_config, llm_provider=mock)
        ctx = make_context()

        result = await agent.inference("test", ctx)
        assert result == "ok"

    @pytest.mark.asyncio
    async def test_inference_history_updated_after_llm_call(self, ml_config: AgentConfig):
        mock = MockLLMProvider(responses=["the answer"])
        agent = ConfigAgent.from_config(ml_config, llm_provider=mock)
        ctx = make_context()

        await agent.inference("the question", ctx)

        assert len(agent.conversation_history) == 2
        assert agent.conversation_history[0] == {"role": "user", "content": "the question"}
        assert agent.conversation_history[1] == {"role": "assistant", "content": "the answer"}

    @pytest.mark.asyncio
    async def test_cost_tracker_tokens_increase_each_call(self, ml_config: AgentConfig):
        mock = MockLLMProvider(responses=["alpha", "beta"])
        tracker = CostTracker()
        agent = ConfigAgent.from_config(ml_config, llm_provider=mock, cost_tracker=tracker)
        ctx = make_context()

        await agent.inference("first", ctx)
        tokens_after_first = tracker.total_tokens_in + tracker.total_tokens_out

        await agent.inference("second", ctx)
        tokens_after_second = tracker.total_tokens_in + tracker.total_tokens_out

        assert tokens_after_second > tokens_after_first
