"""Tests for PIAgent.decide() event emission and state persistence (Plan 6B Task B7)."""
from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, MagicMock

from agentlabx.agents.pi_agent import PIAgent, PIDecision
from agentlabx.core.session import SessionPreferences
from agentlabx.stages.transition import TransitionHandler

SEQUENCE = ["plan_formulation", "experimentation"]


def _make_handler() -> TransitionHandler:
    return TransitionHandler()


def _base_state() -> dict:
    return {
        "pi_decisions": [],
        "current_stage": "plan_formulation",
        "default_sequence": SEQUENCE,
        "completed_stages": ["plan_formulation"],
        "stage_iterations": {},
        "total_iterations": 0,
        "cost_tracker": MagicMock(total_cost=0.0),
        "max_stage_iterations": {},
        "max_total_iterations": 50,
        "stage_config": {},
        "human_override": None,
        "next_stage": None,
    }


@pytest.mark.asyncio
async def test_decide_emits_pi_decision_and_appends_to_state():
    """decide() emits pi_decision event AND persists to state["pi_decisions"]."""
    bus = MagicMock()
    bus.emit = AsyncMock()

    pi = PIAgent(transition_handler=_make_handler(), llm_provider=None, event_bus=bus)
    state = _base_state()
    prefs = SessionPreferences()

    decision = await pi.decide(state, prefs, budget_warning=False)
    assert isinstance(decision, PIDecision)

    # Event was emitted exactly once
    bus.emit.assert_awaited_once()
    emitted_event = bus.emit.await_args_list[0].args[0]
    assert emitted_event.type == "pi_decision"

    # State was updated
    assert len(state["pi_decisions"]) == 1
    persisted = state["pi_decisions"][0]
    assert persisted["action"] == decision.action
    assert "decision_id" in persisted
    assert "ts" in persisted


@pytest.mark.asyncio
async def test_decide_without_event_bus_still_persists_to_state():
    """If no event_bus is provided, skip emit but still append to state (backward compat)."""
    pi = PIAgent(transition_handler=_make_handler(), llm_provider=None)  # no event_bus
    state = _base_state()
    prefs = SessionPreferences()

    await pi.decide(state, prefs, budget_warning=False)
    assert len(state["pi_decisions"]) == 1


@pytest.mark.asyncio
async def test_decide_persists_decision_id_and_ts_fields():
    """Persisted dict includes decision_id (hex) and ts (ISO datetime string)."""
    pi = PIAgent(transition_handler=_make_handler(), llm_provider=None)
    state = _base_state()

    await pi.decide(state, SessionPreferences())
    persisted = state["pi_decisions"][0]

    assert isinstance(persisted["decision_id"], str)
    assert len(persisted["decision_id"]) == 32  # uuid4().hex is 32 hex chars
    assert isinstance(persisted["ts"], str)
    assert "T" in persisted["ts"]  # ISO format has T separator


@pytest.mark.asyncio
async def test_decide_multiple_calls_accumulate_in_state():
    """Each call appends a new entry; state list grows with each decision."""
    pi = PIAgent(transition_handler=_make_handler(), llm_provider=None)
    state = _base_state()
    # Ensure completed_stages lets us advance multiple times
    state["completed_stages"] = ["plan_formulation"]

    await pi.decide(state, SessionPreferences())
    await pi.decide(state, SessionPreferences())

    assert len(state["pi_decisions"]) == 2
    # decision_ids must be unique
    ids = [d["decision_id"] for d in state["pi_decisions"]]
    assert len(set(ids)) == 2


@pytest.mark.asyncio
async def test_decide_event_data_matches_persisted_dict():
    """Event data payload matches what was appended to state."""
    bus = MagicMock()
    bus.emit = AsyncMock()

    pi = PIAgent(transition_handler=_make_handler(), llm_provider=None, event_bus=bus)
    state = _base_state()

    await pi.decide(state, SessionPreferences())

    emitted_data = bus.emit.await_args_list[0].args[0].data
    persisted = state["pi_decisions"][0]
    assert emitted_data == persisted
