"""Zone-aware HITL approval (spec §3.3.3).

Defaults:
  within-zone forward/backtrack → silent (no approval)
  cross-zone forward             → silent (notify only, no approval)
  cross-zone backtrack           → approval required
Per-stage controls override ('approve'/'edit' always approve; 'auto' never).
"""
from __future__ import annotations

from agentlabx.core.session import SessionPreferences
from agentlabx.core.state import create_initial_state
from agentlabx.stages.transition import TransitionHandler


def _s(current, hint):
    s = create_initial_state(
        session_id="s1", user_id="u1", research_topic="t"
    )
    s["current_stage"] = current
    s["next_stage"] = hint
    return s


def test_within_zone_forward_no_approval():
    d = TransitionHandler().decide(_s("literature_review", "plan_formulation"))
    assert d.action == "advance"
    assert d.needs_approval is False


def test_within_zone_backtrack_no_approval():
    d = TransitionHandler().decide(_s("plan_formulation", "literature_review"))
    assert d.action == "backtrack"
    assert d.needs_approval is False


def test_cross_zone_backtrack_requires_approval():
    d = TransitionHandler().decide(_s("experimentation", "literature_review"))
    assert d.action == "backtrack"
    assert d.needs_approval is True


def test_cross_zone_forward_no_approval_by_default():
    d = TransitionHandler().decide(_s("plan_formulation", "data_exploration"))
    assert d.action == "advance"
    assert d.needs_approval is False


def test_stage_approve_control_wins_over_zone_default():
    prefs = SessionPreferences()
    prefs.stage_controls["literature_review"] = "approve"
    d = TransitionHandler(preferences=prefs).decide(
        _s("literature_review", "plan_formulation")
    )
    assert d.needs_approval is True


def test_stage_auto_control_wins_over_zone_default():
    prefs = SessionPreferences()
    prefs.stage_controls["experimentation"] = "auto"
    d = TransitionHandler(preferences=prefs).decide(
        _s("experimentation", "literature_review")
    )
    assert d.action == "backtrack"
    assert d.needs_approval is False
