"""PIAgent — updated for Plan 7C advisor API.

Plan 6B tests that validated the TransitionHandler-wrapping path and
PIDecision shape are replaced here with advisor-API equivalents.
_parse_decision robustness tests are retained (same method, same behaviour).
"""
from __future__ import annotations

import pytest

from agentlabx.agents.pi_agent import ConsultKind, PIAdvice, PIAgent
from agentlabx.core.state import create_initial_state

SEQUENCE = [
    "literature_review",
    "plan_formulation",
    "experimentation",
    "report_writing",
    "peer_review",
]


@pytest.fixture()
def advisor():
    return PIAgent(llm_provider=None, confidence_threshold=0.6)


@pytest.fixture()
def base_state():
    return create_initial_state(
        session_id="s1",
        user_id="u1",
        research_topic="test",
        default_sequence=SEQUENCE,
    )


class TestPIAgent:
    async def test_no_llm_returns_rule_fallback(self, advisor, base_state):
        advice = await advisor.consult_escalation(
            ConsultKind.BACKTRACK_LIMIT,
            base_state,
            context={
                "origin": "literature_review",
                "target": "plan_formulation",
                "attempts": 2,
                "max_attempts": 2,
                "rule_fallback": "plan_formulation",
            },
        )
        assert advice.next_stage == "plan_formulation"
        assert advice.used_fallback is True

    async def test_high_threshold_forces_fallback(self, base_state):
        advisor = PIAgent(llm_provider=None, confidence_threshold=1.1)
        advice = await advisor.consult_escalation(
            ConsultKind.BACKTRACK_LIMIT,
            base_state,
            context={
                "origin": "experimentation",
                "target": "plan_formulation",
                "attempts": 1,
                "max_attempts": 2,
                "rule_fallback": "plan_formulation",
            },
        )
        assert advice.next_stage is not None
        assert advice.used_fallback is True

    async def test_advice_written_to_state(self, advisor, base_state):
        await advisor.consult_escalation(
            ConsultKind.BACKTRACK_LIMIT,
            base_state,
            context={
                "origin": "experimentation",
                "target": "plan_formulation",
                "attempts": 1,
                "max_attempts": 2,
                "rule_fallback": "plan_formulation",
            },
        )
        assert len(base_state["pi_decisions"]) == 1

    async def test_negative_result_checkpoint(self, advisor, base_state):
        advice = await advisor.consult_escalation(
            ConsultKind.NEGATIVE_RESULT,
            base_state,
            context={
                "origin": "experimentation",
                "hypothesis_id": "H1",
                "rule_fallback": "results_interpretation",
            },
        )
        assert isinstance(advice, PIAdvice)
        assert advice.checkpoint == ConsultKind.NEGATIVE_RESULT
        assert advice.used_fallback is True


class TestPIAdvice:
    def test_create_advice(self):
        a = PIAdvice(
            checkpoint=ConsultKind.BACKTRACK_LIMIT,
            next_stage="experimentation",
            reasoning="Research progressing well",
            confidence=0.85,
        )
        assert a.confidence == 0.85
        assert a.used_fallback is False

    def test_used_fallback_default_false(self):
        a = PIAdvice(
            checkpoint=ConsultKind.NEGATIVE_RESULT,
            next_stage=None,
            reasoning="Refuted",
            confidence=0.5,
        )
        assert a.used_fallback is False


class TestParseDecision:
    def test_valid_json_parsed(self):
        agent = PIAgent(llm_provider=None)
        result = agent._parse_decision(
            '{"next_stage": "experimentation", "confidence": 0.9, "reasoning": "ok"}'
        )
        assert result["next_stage"] == "experimentation"
        assert result["confidence"] == 0.9

    def test_markdown_wrapped_json_extracted(self):
        agent = PIAgent(llm_provider=None)
        result = agent._parse_decision(
            "Sure! Here is the JSON:\n```json\n"
            '{"next_stage": "report_writing", "confidence": 0.7, "reasoning": "done"}'
            "\n```"
        )
        assert result["next_stage"] == "report_writing"

    def test_unparseable_returns_empty(self):
        agent = PIAgent(llm_provider=None)
        result = agent._parse_decision("This is not JSON at all.")
        assert result == {}
