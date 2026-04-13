"""Tests for PIAgent LLM wiring — updated for Plan 7C advisor API."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from agentlabx.agents.config_loader import AgentConfigLoader
from agentlabx.agents.pi_agent import ConsultKind, PIAdvice, PIAgent
from agentlabx.core.state import create_initial_state
from agentlabx.providers.llm.mock_provider import MockLLMProvider

CONFIGS_DIR = Path(__file__).parent.parent.parent / "agentlabx" / "agents" / "configs"

SEQUENCE = [
    "literature_review",
    "plan_formulation",
    "experimentation",
    "report_writing",
    "peer_review",
]

_CONTEXT = {
    "origin": "literature_review",
    "target": "plan_formulation",
    "attempts": 1,
    "max_attempts": 2,
    "rule_fallback": "plan_formulation",
}


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
def pi_config():
    return AgentConfigLoader().load_config(CONFIGS_DIR / "pi_agent.yaml")


def make_high_confidence_response(next_stage: str = "plan_formulation") -> str:
    return json.dumps(
        {
            "next_stage": next_stage,
            "confidence": 0.9,
            "reasoning": "Strong evidence supports this direction.",
        }
    )


def make_low_confidence_response() -> str:
    return json.dumps(
        {
            "next_stage": "plan_formulation",
            "confidence": 0.3,
            "reasoning": "Uncertain about direction.",
        }
    )


class TestPIAgentLLMPath:
    @pytest.mark.asyncio
    async def test_high_confidence_accepts_llm_suggestion(self, base_state):
        mock = MockLLMProvider(responses=[make_high_confidence_response("plan_formulation")])
        agent = PIAgent(llm_provider=mock, confidence_threshold=0.6)

        advice = await agent.consult_escalation(ConsultKind.BACKTRACK_LIMIT, base_state, _CONTEXT)

        assert advice.confidence == 0.9
        assert advice.used_fallback is False
        assert advice.next_stage == "plan_formulation"

    @pytest.mark.asyncio
    async def test_llm_overrides_rule_fallback(self, base_state):
        mock = MockLLMProvider(responses=[make_high_confidence_response("experimentation")])
        agent = PIAgent(llm_provider=mock, confidence_threshold=0.6)

        advice = await agent.consult_escalation(
            ConsultKind.BACKTRACK_LIMIT,
            base_state,
            {**_CONTEXT, "rule_fallback": "plan_formulation"},
        )

        assert advice.next_stage == "experimentation"
        assert advice.used_fallback is False

    @pytest.mark.asyncio
    async def test_low_confidence_falls_back(self, base_state):
        mock = MockLLMProvider(responses=[make_low_confidence_response()])
        agent = PIAgent(llm_provider=mock, confidence_threshold=0.6)

        advice = await agent.consult_escalation(ConsultKind.BACKTRACK_LIMIT, base_state, _CONTEXT)

        assert advice.used_fallback is True
        assert advice.next_stage == _CONTEXT["rule_fallback"]

    @pytest.mark.asyncio
    async def test_llm_error_falls_back(self, base_state):
        class ErrorProvider(MockLLMProvider):
            async def query(self, **kwargs):  # type: ignore[override]
                msg = "network error"
                raise RuntimeError(msg)

        agent = PIAgent(llm_provider=ErrorProvider())

        advice = await agent.consult_escalation(ConsultKind.BACKTRACK_LIMIT, base_state, _CONTEXT)

        assert advice.used_fallback is True
        assert advice.confidence == 0.0
        assert "LLM error" in advice.reasoning

    @pytest.mark.asyncio
    async def test_markdown_wrapped_json_still_parses(self, base_state):
        raw_json = make_high_confidence_response()
        wrapped = f"```json\n{raw_json}\n```"
        mock = MockLLMProvider(responses=[wrapped])
        agent = PIAgent(llm_provider=mock, confidence_threshold=0.6)

        advice = await agent.consult_escalation(ConsultKind.BACKTRACK_LIMIT, base_state, _CONTEXT)

        assert advice.confidence == 0.9
        assert advice.used_fallback is False

    @pytest.mark.asyncio
    async def test_malformed_json_falls_back(self, base_state):
        mock = MockLLMProvider(responses=["not json at all"])
        agent = PIAgent(llm_provider=mock, confidence_threshold=0.6)

        advice = await agent.consult_escalation(ConsultKind.BACKTRACK_LIMIT, base_state, _CONTEXT)

        # Malformed JSON → parsed returns {} → confidence defaults to 0.5 < 0.6 → fallback
        assert advice.used_fallback is True

    @pytest.mark.asyncio
    async def test_confidence_threshold_from_config(self, pi_config):
        agent = PIAgent(pi_agent_config=pi_config)

        assert agent.confidence_threshold == 0.6

    @pytest.mark.asyncio
    async def test_explicit_threshold_overrides_config(self, pi_config):
        agent = PIAgent(pi_agent_config=pi_config, confidence_threshold=0.8)

        assert agent.confidence_threshold == 0.8

    @pytest.mark.asyncio
    async def test_multiple_calls_accumulate_in_state(self, base_state):
        mock = MockLLMProvider(responses=[make_high_confidence_response()] * 2)
        agent = PIAgent(llm_provider=mock, confidence_threshold=0.6)

        await agent.consult_escalation(ConsultKind.BACKTRACK_LIMIT, base_state, _CONTEXT)
        await agent.consult_escalation(ConsultKind.BACKTRACK_LIMIT, base_state, _CONTEXT)

        assert len(base_state["pi_decisions"]) == 2

    @pytest.mark.asyncio
    async def test_memory_scope_loaded_from_yaml(self, pi_config):
        agent = PIAgent(pi_agent_config=pi_config)

        # pi_agent.yaml has summarize entries
        assert "literature_review" in agent._memory_scope.summarize

    @pytest.mark.asyncio
    async def test_no_llm_uses_rule_fallback(self, base_state):
        """No llm_provider → rule-based fallback with used_fallback=True."""
        agent = PIAgent(llm_provider=None)

        advice = await agent.consult_escalation(ConsultKind.BACKTRACK_LIMIT, base_state, _CONTEXT)

        assert advice.used_fallback is True
        assert advice.next_stage == _CONTEXT["rule_fallback"]
