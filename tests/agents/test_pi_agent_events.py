"""Tests for PIAgent event emission and state persistence (Plan 7C rewrite of Plan 6B Task B7)."""
from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, MagicMock

from agentlabx.agents.pi_agent import ConsultKind, PIAdvice, PIAgent
from agentlabx.core.state import create_initial_state

SEQUENCE = ["plan_formulation", "experimentation"]

_CONTEXT = {
    "origin": "plan_formulation",
    "target": "experimentation",
    "attempts": 1,
    "max_attempts": 2,
    "rule_fallback": "experimentation",
}


@pytest.mark.asyncio
async def test_consult_emits_pi_decision_and_appends_to_state():
    """consult_escalation() emits pi_decision event AND persists to state['pi_decisions']."""
    bus = MagicMock()
    bus.emit = AsyncMock()

    pi = PIAgent(llm_provider=None, event_bus=bus)
    state = create_initial_state(session_id="s1", user_id="u1", research_topic="test",
                                 default_sequence=SEQUENCE)

    advice = await pi.consult_escalation(ConsultKind.BACKTRACK_LIMIT, state, _CONTEXT)
    assert isinstance(advice, PIAdvice)

    bus.emit.assert_awaited_once()
    emitted_event = bus.emit.await_args_list[0].args[0]
    assert emitted_event.type == "pi_decision"

    assert len(state["pi_decisions"]) == 1
    persisted = state["pi_decisions"][0]
    assert persisted["next_stage"] == advice.next_stage
    assert "decision_id" in persisted
    assert "ts" in persisted


@pytest.mark.asyncio
async def test_consult_without_event_bus_still_persists_to_state():
    """If no event_bus is provided, skip emit but still append to state."""
    pi = PIAgent(llm_provider=None)
    state = create_initial_state(session_id="s1", user_id="u1", research_topic="test")

    await pi.consult_escalation(ConsultKind.BACKTRACK_LIMIT, state, _CONTEXT)
    assert len(state["pi_decisions"]) == 1


@pytest.mark.asyncio
async def test_consult_persists_decision_id_and_ts_fields():
    """Persisted dict includes decision_id (hex) and ts (ISO datetime string)."""
    pi = PIAgent(llm_provider=None)
    state = create_initial_state(session_id="s1", user_id="u1", research_topic="test")

    await pi.consult_escalation(ConsultKind.BACKTRACK_LIMIT, state, _CONTEXT)
    persisted = state["pi_decisions"][0]

    assert isinstance(persisted["decision_id"], str)
    assert len(persisted["decision_id"]) == 32  # uuid4().hex is 32 hex chars
    assert isinstance(persisted["ts"], str)
    assert "T" in persisted["ts"]  # ISO format has T separator


@pytest.mark.asyncio
async def test_consult_multiple_calls_accumulate_in_state():
    """Each call appends a new entry; state list grows with each decision."""
    pi = PIAgent(llm_provider=None)
    state = create_initial_state(session_id="s1", user_id="u1", research_topic="test")

    await pi.consult_escalation(ConsultKind.BACKTRACK_LIMIT, state, _CONTEXT)
    await pi.consult_escalation(ConsultKind.BACKTRACK_LIMIT, state, _CONTEXT)

    assert len(state["pi_decisions"]) == 2
    ids = [d["decision_id"] for d in state["pi_decisions"]]
    assert len(set(ids)) == 2


@pytest.mark.asyncio
async def test_consult_event_data_matches_persisted_dict():
    """Event data payload matches what was appended to state."""
    bus = MagicMock()
    bus.emit = AsyncMock()

    pi = PIAgent(llm_provider=None, event_bus=bus)
    state = create_initial_state(session_id="s1", user_id="u1", research_topic="test")

    await pi.consult_escalation(ConsultKind.BACKTRACK_LIMIT, state, _CONTEXT)

    emitted_data = bus.emit.await_args_list[0].args[0].data
    persisted = state["pi_decisions"][0]
    assert emitted_data == persisted
