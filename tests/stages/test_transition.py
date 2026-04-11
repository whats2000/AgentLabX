"""Tests for TransitionHandler — priority-based pipeline routing."""

from __future__ import annotations

import pytest

from agentlabx.core.session import SessionPreferences
from agentlabx.core.state import create_initial_state
from agentlabx.stages.transition import TransitionDecision, TransitionHandler


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

DEFAULT_SEQ = [
    "literature_review",
    "plan_formulation",
    "data_exploration",
    "data_preparation",
    "experimentation",
    "results_interpretation",
    "report_writing",
    "peer_review",
]


def make_state(**overrides):
    """Create a base state and apply overrides."""
    state = create_initial_state(session_id="s1", user_id="u1", research_topic="test")
    state.update(overrides)
    return state


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestTransitionHandler:
    def test_advance_to_next_in_sequence(self):
        state = make_state(
            current_stage="literature_review",
            next_stage=None,
            default_sequence=DEFAULT_SEQ,
            completed_stages=[],
        )
        decision = TransitionHandler().decide(state)
        assert decision.next_stage == "plan_formulation"
        assert decision.action == "advance"

    def test_human_override_takes_priority(self):
        """human_override wins over everything else — even iteration limits."""
        state = make_state(
            current_stage="literature_review",
            next_stage="peer_review",
            human_override="experimentation",
            total_iterations=999,
            max_total_iterations=5,
            default_sequence=DEFAULT_SEQ,
            completed_stages=[],
        )
        decision = TransitionHandler().decide(state)
        assert decision.next_stage == "experimentation"
        assert decision.action == "human_override"

    def test_stage_hint_respected_backtrack(self):
        """Backtrack from peer_review to experimentation follows hint."""
        state = make_state(
            current_stage="peer_review",
            next_stage="experimentation",
            human_override=None,
            default_sequence=DEFAULT_SEQ,
            completed_stages=[],
        )
        decision = TransitionHandler().decide(state)
        assert decision.next_stage == "experimentation"
        assert decision.action == "backtrack"

    def test_stage_hint_respected_forward(self):
        """Forward hint is followed with action='advance'."""
        state = make_state(
            current_stage="literature_review",
            next_stage="data_exploration",
            human_override=None,
            default_sequence=DEFAULT_SEQ,
            completed_stages=[],
        )
        decision = TransitionHandler().decide(state)
        assert decision.next_stage == "data_exploration"
        assert decision.action == "advance"

    def test_end_when_all_stages_complete(self):
        state = make_state(
            current_stage="peer_review",
            next_stage=None,
            human_override=None,
            default_sequence=DEFAULT_SEQ,
            completed_stages=list(DEFAULT_SEQ),
        )
        decision = TransitionHandler().decide(state)
        assert decision.next_stage is None
        assert decision.action == "complete"

    def test_max_iterations_forces_advance(self):
        """Stage wants to repeat (self-loop hint) but has hit iteration limit."""
        state = make_state(
            current_stage="experimentation",
            next_stage="experimentation",  # self-loop hint
            human_override=None,
            default_sequence=DEFAULT_SEQ,
            completed_stages=[],
            stage_iterations={"experimentation": 3},
            max_stage_iterations={"experimentation": 3},
        )
        decision = TransitionHandler().decide(state)
        assert decision.action == "forced_advance"
        assert decision.next_stage == "results_interpretation"

    def test_total_iterations_limit_completes(self):
        state = make_state(
            current_stage="literature_review",
            next_stage=None,
            human_override=None,
            default_sequence=DEFAULT_SEQ,
            completed_stages=[],
            total_iterations=50,
            max_total_iterations=50,
        )
        decision = TransitionHandler().decide(state)
        assert decision.action == "complete"
        assert decision.next_stage is None

    def test_hitl_approve_triggers_checkpoint(self):
        """Stage control 'approve' sets needs_approval=True."""
        prefs = SessionPreferences(stage_controls={"experimentation": "approve"})
        state = make_state(
            current_stage="experimentation",
            next_stage=None,
            human_override=None,
            default_sequence=DEFAULT_SEQ,
            completed_stages=[],
        )
        decision = TransitionHandler(preferences=prefs).decide(state)
        assert decision.needs_approval is True

    def test_hitl_edit_triggers_checkpoint(self):
        """Stage control 'edit' also sets needs_approval=True."""
        prefs = SessionPreferences(stage_controls={"plan_formulation": "edit"})
        state = make_state(
            current_stage="plan_formulation",
            next_stage=None,
            human_override=None,
            default_sequence=DEFAULT_SEQ,
            completed_stages=[],
        )
        decision = TransitionHandler(preferences=prefs).decide(state)
        assert decision.needs_approval is True

    def test_auto_mode_no_checkpoint(self):
        """Default auto preferences produce no approval needed."""
        state = make_state(
            current_stage="literature_review",
            next_stage=None,
            human_override=None,
            default_sequence=DEFAULT_SEQ,
            completed_stages=[],
        )
        decision = TransitionHandler().decide(state)
        assert decision.needs_approval is False

    def test_backtrack_control_approve_triggers_checkpoint(self):
        """backtrack_control='approve' requires approval on backtrack transitions."""
        prefs = SessionPreferences(backtrack_control="approve")
        state = make_state(
            current_stage="peer_review",
            next_stage="experimentation",
            human_override=None,
            default_sequence=DEFAULT_SEQ,
            completed_stages=[],
        )
        decision = TransitionHandler(preferences=prefs).decide(state)
        assert decision.action == "backtrack"
        assert decision.needs_approval is True

    def test_backtrack_control_auto_no_checkpoint(self):
        """backtrack_control='auto' never requires approval for backtrack."""
        prefs = SessionPreferences(backtrack_control="auto")
        state = make_state(
            current_stage="peer_review",
            next_stage="experimentation",
            human_override=None,
            default_sequence=DEFAULT_SEQ,
            completed_stages=[],
        )
        decision = TransitionHandler(preferences=prefs).decide(state)
        assert decision.action == "backtrack"
        assert decision.needs_approval is False

    def test_total_iterations_priority_over_stage_hint(self):
        """Total iterations limit takes priority over stage hint."""
        state = make_state(
            current_stage="experimentation",
            next_stage="data_preparation",
            human_override=None,
            default_sequence=DEFAULT_SEQ,
            completed_stages=[],
            total_iterations=50,
            max_total_iterations=50,
        )
        decision = TransitionHandler().decide(state)
        assert decision.action == "complete"

    def test_skip_already_completed_stages(self):
        """Advance skips completed stages to find next uncompleted."""
        state = make_state(
            current_stage="literature_review",
            next_stage=None,
            human_override=None,
            default_sequence=DEFAULT_SEQ,
            completed_stages=["plan_formulation"],
        )
        decision = TransitionHandler().decide(state)
        # plan_formulation is done, so it skips to data_exploration
        assert decision.next_stage == "data_exploration"

    def test_unknown_current_stage_starts_from_beginning(self):
        """Unknown current_stage falls back to first in sequence."""
        state = make_state(
            current_stage="nonexistent_stage",
            next_stage=None,
            human_override=None,
            default_sequence=DEFAULT_SEQ,
            completed_stages=[],
        )
        decision = TransitionHandler().decide(state)
        assert decision.next_stage == "literature_review"
        assert decision.action == "advance"
