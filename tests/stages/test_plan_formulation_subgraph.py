"""plan_formulation migration to plan-driven hooks (Plan 7E B1)."""
from __future__ import annotations

import pytest

from agentlabx.core.state import create_initial_state
from agentlabx.stages.plan_formulation import PlanFormulationStage


def test_plan_formulation_build_plan_itemizes_research_plan_tasks():
    stage = PlanFormulationStage()
    state = create_initial_state(
        session_id="s1", user_id="u1", research_topic="test topic"
    )
    plan = stage.build_plan(state, feedback=None)
    assert len(plan["items"]) >= 3
    ids = {i["id"] for i in plan["items"]}
    assert "plan:goals" in ids
    assert "plan:methodology" in ids
    assert "plan:hypotheses" in ids


def test_plan_formulation_build_plan_adds_feedback_item_when_feedback_given():
    stage = PlanFormulationStage()
    state = create_initial_state(
        session_id="s1", user_id="u1", research_topic="t"
    )
    plan = stage.build_plan(state, feedback="revise methodology for bigger scale")
    feedback_items = [i for i in plan["items"] if i["source"] == "feedback"]
    assert len(feedback_items) >= 1
    assert "revise methodology" in feedback_items[0]["description"]


def test_plan_formulation_build_plan_marks_goals_done_when_prior_plan_exists():
    stage = PlanFormulationStage()
    state = create_initial_state(
        session_id="s1", user_id="u1", research_topic="t"
    )
    from agentlabx.core.state import ResearchPlan

    state["plan"] = [
        ResearchPlan(
            goals=["g1"], methodology="m", hypotheses=["h1"],
            full_text="prior plan",
        )
    ]
    plan = stage.build_plan(state, feedback=None)
    goals_item = next(i for i in plan["items"] if i["id"] == "plan:goals")
    assert goals_item["status"] == "done"
    assert goals_item["existing_artifact_ref"] == "plan[-1]"


def test_plan_formulation_build_plan_does_not_mark_done_when_feedback_given():
    """Feedback forces re-execution even with prior plan."""
    stage = PlanFormulationStage()
    state = create_initial_state(
        session_id="s1", user_id="u1", research_topic="t"
    )
    from agentlabx.core.state import ResearchPlan

    state["plan"] = [
        ResearchPlan(
            goals=["g1"], methodology="m", hypotheses=["h1"],
            full_text="prior plan",
        )
    ]
    plan = stage.build_plan(state, feedback="pivot to larger datasets")
    goals_item = next(i for i in plan["items"] if i["id"] == "plan:goals")
    assert goals_item["status"] == "todo"  # not bypassed because feedback present
