from __future__ import annotations

import pytest

from agentlabx.agents.pi_agent import PIAgent, PIDecision
from agentlabx.core.session import SessionPreferences
from agentlabx.core.state import create_initial_state
from agentlabx.stages.transition import TransitionHandler

SEQUENCE = [
    "literature_review",
    "plan_formulation",
    "experimentation",
    "report_writing",
    "peer_review",
]


@pytest.fixture()
def pi_agent():
    handler = TransitionHandler()
    return PIAgent(transition_handler=handler, confidence_threshold=0.6)


@pytest.fixture()
def base_state():
    return create_initial_state(
        session_id="s1",
        user_id="u1",
        research_topic="test",
        default_sequence=SEQUENCE,
    )


class TestPIAgent:
    async def test_advance_with_high_confidence(self, pi_agent, base_state):
        base_state["current_stage"] = "literature_review"
        base_state["completed_stages"] = ["literature_review"]
        decision = await pi_agent.decide(base_state, SessionPreferences())
        assert decision.next_stage == "plan_formulation"
        assert decision.confidence >= 0.6

    async def test_fallback_on_low_confidence(self, pi_agent, base_state):
        base_state["current_stage"] = "literature_review"
        base_state["completed_stages"] = ["literature_review"]
        pi_agent.confidence_threshold = 1.1
        decision = await pi_agent.decide(base_state, SessionPreferences())
        assert decision.next_stage is not None
        assert decision.used_fallback is True

    async def test_tracks_decision_history(self, pi_agent, base_state):
        base_state["current_stage"] = "literature_review"
        base_state["completed_stages"] = ["literature_review"]
        await pi_agent.decide(base_state, SessionPreferences())
        assert len(pi_agent.decision_history) == 1

    async def test_budget_warning(self, pi_agent, base_state):
        base_state["current_stage"] = "experimentation"
        base_state["completed_stages"] = [
            "literature_review",
            "plan_formulation",
            "experimentation",
        ]
        decision = await pi_agent.decide(base_state, SessionPreferences(), budget_warning=True)
        assert decision.budget_note is not None


class TestPIDecision:
    def test_create_decision(self):
        d = PIDecision(
            next_stage="experimentation",
            action="advance",
            reason="Research progressing well",
            confidence=0.85,
        )
        assert d.confidence == 0.85
        assert d.budget_note is None
        assert d.used_fallback is False
