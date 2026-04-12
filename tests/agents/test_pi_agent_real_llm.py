"""Tests for PIAgent LLM wiring — Task 11."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from agentlabx.agents.config_loader import AgentConfigLoader
from agentlabx.agents.pi_agent import PIAgent
from agentlabx.core.session import SessionPreferences
from agentlabx.core.state import create_initial_state
from agentlabx.providers.llm.mock_provider import MockLLMProvider
from agentlabx.stages.transition import TransitionHandler

CONFIGS_DIR = Path(__file__).parent.parent.parent / "agentlabx" / "agents" / "configs"

SEQUENCE = [
    "literature_review",
    "plan_formulation",
    "experimentation",
    "report_writing",
    "peer_review",
]


@pytest.fixture
def base_state():
    state = create_initial_state(
        session_id="s1",
        user_id="u1",
        research_topic="test topic",
        default_sequence=SEQUENCE,
    )
    state["current_stage"] = "literature_review"
    state["completed_stages"] = ["literature_review"]
    return state


@pytest.fixture
def handler() -> TransitionHandler:
    return TransitionHandler()


@pytest.fixture
def pi_config():
    return AgentConfigLoader().load_config(CONFIGS_DIR / "pi_agent.yaml")


def make_agree_response(confidence: float = 0.9) -> str:
    return json.dumps(
        {
            "agree_with_rule": True,
            "next_stage": "plan_formulation",
            "confidence": confidence,
            "reasoning": "The rule decision is appropriate.",
        }
    )


def make_override_response(next_stage: str = "different_stage", confidence: float = 0.9) -> str:
    return json.dumps(
        {
            "agree_with_rule": False,
            "next_stage": next_stage,
            "confidence": confidence,
            "reasoning": "PI disagrees: we should skip ahead.",
        }
    )


class TestPIAgentLLMPath:
    @pytest.mark.asyncio
    async def test_llm_agrees_with_rule(self, handler, base_state):
        mock = MockLLMProvider(responses=[make_agree_response(confidence=0.9)])
        agent = PIAgent(transition_handler=handler, llm_provider=mock)

        decision = await agent.decide(base_state, SessionPreferences())

        assert decision.confidence == 0.9
        assert decision.used_fallback is False
        # When agree_with_rule=True, action comes from rule handler
        assert decision.action != "pi_override"

    @pytest.mark.asyncio
    async def test_llm_overrides_rule(self, handler, base_state):
        mock = MockLLMProvider(
            responses=[make_override_response(next_stage="different_stage", confidence=0.9)]
        )
        agent = PIAgent(transition_handler=handler, llm_provider=mock)

        decision = await agent.decide(base_state, SessionPreferences())

        assert decision.action == "pi_override"
        assert decision.next_stage == "different_stage"
        assert decision.used_fallback is False

    @pytest.mark.asyncio
    async def test_low_confidence_falls_back(self, handler, base_state):
        # confidence=0.3 < default threshold 0.6 → fallback to rule
        mock = MockLLMProvider(responses=[make_agree_response(confidence=0.3)])
        agent = PIAgent(transition_handler=handler, llm_provider=mock)

        decision = await agent.decide(base_state, SessionPreferences())

        assert decision.used_fallback is True
        # Falls back to rule decision, not pi_override
        assert decision.action != "pi_override"

    @pytest.mark.asyncio
    async def test_llm_error_falls_back(self, handler, base_state):
        class ErrorProvider(MockLLMProvider):
            async def query(self, **kwargs):  # type: ignore[override]
                msg = "network error"
                raise RuntimeError(msg)

        agent = PIAgent(transition_handler=handler, llm_provider=ErrorProvider())

        decision = await agent.decide(base_state, SessionPreferences())

        assert decision.used_fallback is True
        assert decision.confidence == 0.0
        assert "LLM error" in decision.reason

    @pytest.mark.asyncio
    async def test_markdown_wrapped_json_still_parses(self, handler, base_state):
        raw_json = json.dumps(
            {
                "agree_with_rule": True,
                "next_stage": "plan_formulation",
                "confidence": 0.85,
                "reasoning": "Looks good.",
            }
        )
        wrapped = f"```json\n{raw_json}\n```"
        mock = MockLLMProvider(responses=[wrapped])
        agent = PIAgent(transition_handler=handler, llm_provider=mock)

        decision = await agent.decide(base_state, SessionPreferences())

        assert decision.confidence == 0.85
        assert decision.used_fallback is False

    @pytest.mark.asyncio
    async def test_malformed_json_falls_back(self, handler, base_state):
        mock = MockLLMProvider(responses=["not json at all"])
        agent = PIAgent(transition_handler=handler, llm_provider=mock)

        decision = await agent.decide(base_state, SessionPreferences())

        # Malformed JSON → parsed returns {} → confidence defaults to 0.5 < 0.6 → fallback
        assert decision.used_fallback is True

    @pytest.mark.asyncio
    async def test_confidence_threshold_from_config(self, handler, pi_config):
        agent = PIAgent(transition_handler=handler, pi_agent_config=pi_config)

        assert agent.confidence_threshold == 0.6

    @pytest.mark.asyncio
    async def test_explicit_threshold_overrides_config(self, handler, pi_config):
        agent = PIAgent(
            transition_handler=handler,
            pi_agent_config=pi_config,
            confidence_threshold=0.8,
        )

        assert agent.confidence_threshold == 0.8

    @pytest.mark.asyncio
    async def test_decision_history_tracked_llm_path(self, handler, base_state):
        mock = MockLLMProvider(responses=[make_agree_response()])
        agent = PIAgent(transition_handler=handler, llm_provider=mock)

        await agent.decide(base_state, SessionPreferences())
        await agent.decide(base_state, SessionPreferences())

        # Second call — queue is empty, mock returns default
        assert len(agent.decision_history) == 2

    @pytest.mark.asyncio
    async def test_budget_warning_included_in_prompt(self, handler, base_state):
        mock = MockLLMProvider(responses=[make_agree_response()])
        agent = PIAgent(transition_handler=handler, llm_provider=mock)

        decision = await agent.decide(base_state, SessionPreferences(), budget_warning=True)

        assert decision.budget_note == "Budget warning active"
        prompt = mock.calls[0]["prompt"]
        assert "Budget" in prompt or "budget" in prompt

    @pytest.mark.asyncio
    async def test_memory_scope_loaded_from_yaml(self, handler, pi_config):
        agent = PIAgent(transition_handler=handler, pi_agent_config=pi_config)

        # pi_agent.yaml has summarize entries
        assert "literature_review" in agent._memory_scope.summarize

    @pytest.mark.asyncio
    async def test_no_llm_uses_rule_fallback(self, handler, base_state):
        """Plan 2 behavior preserved: no llm_provider → rule-based at 0.85 confidence."""
        agent = PIAgent(transition_handler=handler)

        decision = await agent.decide(base_state, SessionPreferences())

        assert decision.confidence == 0.85
        assert decision.used_fallback is False
