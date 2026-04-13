"""TransitionHandler consults PI advisor on Priority-3 escalation."""
from __future__ import annotations

import pytest

from agentlabx.agents.pi_agent import ConsultKind, PIAdvice, PIAgent
from agentlabx.core.session import SessionPreferences
from agentlabx.core.state import create_initial_state
from agentlabx.stages.transition import TransitionHandler


def _state_at_retry_limit():
    s = create_initial_state(
        session_id="s1",
        user_id="u1",
        research_topic="t",
        default_sequence=[
            "literature_review",
            "plan_formulation",
            "experimentation",
            "peer_review",
        ],
    )
    s["current_stage"] = "experimentation"
    s["next_stage"] = "literature_review"
    s["backtrack_attempts"] = {"experimentation->literature_review": 2}
    return s


@pytest.mark.asyncio
async def test_decide_async_without_advisor_matches_sync_decide():
    """decide_async with advisor=None returns the same TransitionDecision as decide()."""
    h = TransitionHandler(
        preferences=SessionPreferences(max_backtrack_attempts_per_edge=2),
    )
    s = _state_at_retry_limit()

    sync = h.decide(s)
    async_ = await h.decide_async(s)

    assert async_.action == sync.action == "backtrack_limit_exceeded"
    assert async_.next_stage == sync.next_stage == "peer_review"
    assert async_.reason == sync.reason
    assert async_.needs_approval == sync.needs_approval


@pytest.mark.asyncio
async def test_decide_async_with_confident_advisor_uses_advice_target(monkeypatch):
    """High-confidence advice overrides the rule-based fallback."""
    advisor = PIAgent(llm_provider=None)

    async def fake_consult(checkpoint, state, context):
        advice = PIAdvice(
            checkpoint=checkpoint,
            next_stage="plan_formulation",
            reasoning="pivot the hypothesis",
            confidence=0.9,
            used_fallback=False,
        )
        return await advisor._finalize(advice, state)

    monkeypatch.setattr(advisor, "consult_escalation", fake_consult)

    h = TransitionHandler(
        preferences=SessionPreferences(max_backtrack_attempts_per_edge=2),
        pi_advisor=advisor,
    )
    d = await h.decide_async(_state_at_retry_limit())

    assert d.action == "backtrack_limit_exceeded"
    assert d.next_stage == "plan_formulation"
    assert "PI advisor" in d.reason
    assert "pivot the hypothesis" in d.reason
    assert d.needs_approval is True


@pytest.mark.asyncio
async def test_decide_async_with_low_confidence_advisor_falls_back_to_rule(monkeypatch):
    advisor = PIAgent(llm_provider=None, confidence_threshold=0.6)

    async def fake_consult(checkpoint, state, context):
        # Advisor returns used_fallback=True when confidence < threshold
        advice = PIAdvice(
            checkpoint=checkpoint,
            next_stage=context.get("rule_fallback"),
            reasoning="uncertain",
            confidence=0.3,
            used_fallback=True,
        )
        return await advisor._finalize(advice, state)

    monkeypatch.setattr(advisor, "consult_escalation", fake_consult)

    h = TransitionHandler(
        preferences=SessionPreferences(max_backtrack_attempts_per_edge=2),
        pi_advisor=advisor,
    )
    d = await h.decide_async(_state_at_retry_limit())

    # Rule fallback wins when advisor defers
    assert d.action == "backtrack_limit_exceeded"
    assert d.next_stage == "peer_review"  # rule fallback, NOT advice
    assert "PI advisor" not in d.reason


@pytest.mark.asyncio
async def test_decide_async_only_consults_advisor_on_backtrack_limit_exceeded(monkeypatch):
    """Advisor is NOT consulted on other action types (advance, backtrack, etc.)."""
    advisor = PIAgent(llm_provider=None)
    consult_calls: list = []

    async def track_consult(checkpoint, state, context):
        consult_calls.append(checkpoint)
        advice = PIAdvice(
            checkpoint=checkpoint,
            next_stage="elsewhere",
            reasoning="should not be called",
            confidence=0.9,
            used_fallback=False,
        )
        return advice

    monkeypatch.setattr(advisor, "consult_escalation", track_consult)

    h = TransitionHandler(
        preferences=SessionPreferences(),
        pi_advisor=advisor,
    )
    # Ordinary advance — no retry limit hit
    state = create_initial_state(
        session_id="s1", user_id="u1", research_topic="t",
        default_sequence=["literature_review", "plan_formulation", "experimentation"],
    )
    state["current_stage"] = "literature_review"
    state["next_stage"] = "plan_formulation"

    d = await h.decide_async(state)
    assert d.action == "advance"
    assert consult_calls == []  # advisor was NOT consulted
