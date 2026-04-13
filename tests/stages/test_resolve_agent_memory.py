"""Tests for resolve_agent memory hydration from pipeline state (Task A7)."""

from __future__ import annotations

from agentlabx.stages._helpers import resolve_agent


def test_resolve_agent_hydrates_from_state(sample_registry):
    state = {
        "agent_memory": {
            "phd_student": {
                "working_memory": {"focus": "MATH"},
                "notes": ["found 3 relevant papers"],
                "last_active_stage": "literature_review",
                "turn_count": 7,
            }
        }
    }
    agent = resolve_agent(sample_registry, "phd_student", state=state)
    assert agent.working_memory == {"focus": "MATH"}
    assert agent.notes == ["found 3 relevant papers"]
    assert agent.turn_count == 7
    assert agent.last_active_stage == "literature_review"
    assert agent.dirty is False


def test_resolve_agent_with_no_prior_memory(sample_registry):
    state = {"agent_memory": {}}
    agent = resolve_agent(sample_registry, "phd_student", state=state)
    assert agent.working_memory == {}
    assert agent.notes == []
    assert agent.turn_count == 0


def test_resolve_agent_state_none_still_works(sample_registry):
    """Backward-compat: state kwarg is optional."""
    agent = resolve_agent(sample_registry, "phd_student")
    assert agent.working_memory == {}
    assert agent.notes == []
