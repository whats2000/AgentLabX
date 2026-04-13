"""Retry gate: per-edge limit + cost fraction, with decide() owning fallback."""
from __future__ import annotations

from agentlabx.core.session import SessionPreferences
from agentlabx.core.state import CostTracker, create_initial_state
from agentlabx.stages.transition import TransitionHandler


def _state(current="experimentation", hint="literature_review"):
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
    s["current_stage"] = current
    s["next_stage"] = hint
    return s


def test_within_per_edge_limit_backtracks():
    s = _state()
    s["backtrack_attempts"] = {"experimentation->literature_review": 1}

    h = TransitionHandler(
        preferences=SessionPreferences(max_backtrack_attempts_per_edge=2)
    )
    d = h.decide(s)

    assert d.action == "backtrack"
    assert d.next_stage == "literature_review"


def test_at_per_edge_limit_escalates_with_concrete_fallback_target():
    s = _state()
    s["backtrack_attempts"] = {"experimentation->literature_review": 2}

    h = TransitionHandler(
        preferences=SessionPreferences(max_backtrack_attempts_per_edge=2)
    )
    d = h.decide(s)

    assert d.action == "backtrack_limit_exceeded"
    assert d.needs_approval is True
    assert d.next_stage == "peer_review"  # next-in-sequence after experimentation
    assert "per-edge" in d.reason.lower()


def test_cost_fraction_exceeded_escalates_with_fallback():
    s = _state()
    s["backtrack_attempts"] = {"experimentation->literature_review": 0}
    s["backtrack_cost_spent"] = 100.0
    s["cost_tracker"] = CostTracker(total_cost=200.0)  # 50% > 0.4

    h = TransitionHandler(
        preferences=SessionPreferences(
            max_backtrack_attempts_per_edge=5,
            max_backtrack_cost_fraction=0.4,
        )
    )
    d = h.decide(s)

    assert d.action == "backtrack_limit_exceeded"
    assert d.needs_approval is True
    assert d.next_stage == "peer_review"
    assert "cost" in d.reason.lower()


def test_zero_budget_does_not_divide_by_zero():
    s = _state()
    s["backtrack_attempts"] = {}
    s["cost_tracker"] = CostTracker()  # total_cost = 0

    h = TransitionHandler(
        preferences=SessionPreferences(max_backtrack_cost_fraction=0.4)
    )
    d = h.decide(s)

    assert d.action == "backtrack"
    assert d.next_stage == "literature_review"


def test_dual_exceeded_returns_per_edge_message_first():
    """When both gates trip, per-edge reason wins (first-trigger message semantic)."""
    s = _state()
    s["backtrack_attempts"] = {"experimentation->literature_review": 3}
    s["backtrack_cost_spent"] = 100.0
    s["cost_tracker"] = CostTracker(total_cost=200.0)  # also 50% > 0.4

    h = TransitionHandler(
        preferences=SessionPreferences(
            max_backtrack_attempts_per_edge=2,
            max_backtrack_cost_fraction=0.4,
        )
    )
    d = h.decide(s)

    assert d.action == "backtrack_limit_exceeded"
    assert d.needs_approval is True
    assert "per-edge" in d.reason.lower()
    assert "cost" not in d.reason.lower()
