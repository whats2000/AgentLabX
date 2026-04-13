"""PIAgent.consult_escalation — advisor consulted at specific checkpoints."""
from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from agentlabx.agents.pi_agent import ConsultKind, PIAdvice, PIAgent
from agentlabx.core.state import create_initial_state


@pytest.mark.asyncio
async def test_consult_escalation_no_llm_returns_rule_based_fallback():
    """Without an LLM provider, advisor emits a low-confidence used_fallback advice."""
    advisor = PIAgent(llm_provider=None)
    state = create_initial_state(session_id="s1", user_id="u1", research_topic="t")

    advice = await advisor.consult_escalation(
        ConsultKind.BACKTRACK_LIMIT,
        state,
        context={
            "origin": "experimentation",
            "target": "literature_review",
            "attempts": 2,
            "max_attempts": 2,
            "rule_fallback": "peer_review",
        },
    )

    assert isinstance(advice, PIAdvice)
    assert advice.checkpoint == ConsultKind.BACKTRACK_LIMIT
    assert advice.next_stage == "peer_review"  # defaults to rule fallback
    assert advice.used_fallback is True


@pytest.mark.asyncio
async def test_consult_escalation_high_confidence_advice_overrides_rule_fallback():
    """With an LLM returning confident JSON, advice.next_stage wins over rule fallback."""
    mock_provider = AsyncMock()

    class _Resp:
        content = (
            '{"next_stage": "plan_formulation", "confidence": 0.9, '
            '"reasoning": "pivot the hypothesis"}'
        )

    mock_provider.query = AsyncMock(return_value=_Resp())
    mock_provider.is_mock = False

    advisor = PIAgent(llm_provider=mock_provider, confidence_threshold=0.6)
    state = create_initial_state(session_id="s1", user_id="u1", research_topic="t")

    advice = await advisor.consult_escalation(
        ConsultKind.BACKTRACK_LIMIT,
        state,
        context={
            "origin": "experimentation",
            "target": "literature_review",
            "attempts": 2,
            "max_attempts": 2,
            "rule_fallback": "peer_review",
        },
    )

    assert advice.next_stage == "plan_formulation"
    assert advice.used_fallback is False
    assert advice.confidence >= 0.6


@pytest.mark.asyncio
async def test_consult_escalation_low_confidence_falls_back_to_rule():
    mock_provider = AsyncMock()

    class _Resp:
        content = (
            '{"next_stage": "plan_formulation", "confidence": 0.3, '
            '"reasoning": "uncertain"}'
        )

    mock_provider.query = AsyncMock(return_value=_Resp())

    advisor = PIAgent(llm_provider=mock_provider, confidence_threshold=0.6)
    state = create_initial_state(session_id="s1", user_id="u1", research_topic="t")

    advice = await advisor.consult_escalation(
        ConsultKind.BACKTRACK_LIMIT,
        state,
        context={"rule_fallback": "peer_review"},
    )

    assert advice.next_stage == "peer_review"  # rule fallback wins
    assert advice.used_fallback is True


@pytest.mark.asyncio
async def test_consult_escalation_writes_pi_decisions_and_emits_event():
    """Every advice invocation appends to state['pi_decisions'] + emits pi_decision event."""
    from agentlabx.core.events import EventBus

    events: list = []
    bus = EventBus()

    async def _collect(e):
        events.append(e)

    bus.subscribe("*", _collect)

    advisor = PIAgent(llm_provider=None, event_bus=bus)
    state = create_initial_state(session_id="s1", user_id="u1", research_topic="t")

    await advisor.consult_escalation(
        ConsultKind.BACKTRACK_LIMIT,
        state,
        context={"rule_fallback": "peer_review"},
    )

    assert len(state["pi_decisions"]) == 1
    assert state["pi_decisions"][0]["next_stage"] == "peer_review"
    assert any(e.type == "pi_decision" for e in events)


@pytest.mark.asyncio
async def test_consult_escalation_negative_result_uses_dedicated_prompt():
    """ConsultKind.NEGATIVE_RESULT asks publish/pivot/redirect — different prompt."""
    mock_provider = AsyncMock()

    class _Resp:
        content = (
            '{"next_stage": "report_writing", "confidence": 0.8, '
            '"reasoning": "negative result worth publishing"}'
        )

    mock_provider.query = AsyncMock(return_value=_Resp())

    advisor = PIAgent(llm_provider=mock_provider, confidence_threshold=0.6)
    state = create_initial_state(session_id="s1", user_id="u1", research_topic="t")

    advice = await advisor.consult_escalation(
        ConsultKind.NEGATIVE_RESULT,
        state,
        context={
            "origin": "experimentation",
            "hypothesis_id": "H1",
            "rule_fallback": "results_interpretation",
        },
    )

    # Prompt for NEGATIVE_RESULT differs — verify via call-args inspection
    call_args = mock_provider.query.await_args
    prompt = call_args.kwargs.get("prompt", call_args.args[1] if len(call_args.args) > 1 else "")
    assert "publish" in prompt.lower() or "pivot" in prompt.lower()
    assert advice.next_stage == "report_writing"
