"""data_exploration migration (Plan 7E B2)."""
from __future__ import annotations

from agentlabx.core.state import create_initial_state
from agentlabx.stages.data_exploration import DataExplorationStage


def test_data_exploration_build_plan_itemizes_survey_quality_recommendations():
    stage = DataExplorationStage()
    state = create_initial_state(session_id="s1", user_id="u1", research_topic="t")
    plan = stage.build_plan(state, feedback=None)
    ids = {i["id"] for i in plan["items"]}
    assert "eda:survey" in ids
    assert "eda:quality-issues" in ids
    assert "eda:recommendations" in ids


def test_data_exploration_build_plan_adds_feedback_item():
    stage = DataExplorationStage()
    state = create_initial_state(session_id="s1", user_id="u1", research_topic="t")
    plan = stage.build_plan(state, feedback="look for class imbalance")
    feedback = [i for i in plan["items"] if i["source"] == "feedback"]
    assert len(feedback) >= 1
    assert "class imbalance" in feedback[0]["description"]


def test_data_exploration_prior_bypass_marks_survey_done():
    stage = DataExplorationStage()
    state = create_initial_state(session_id="s1", user_id="u1", research_topic="t")
    from agentlabx.core.state import EDAResult

    state["data_exploration"] = [
        EDAResult(findings=["f1"], data_quality_issues=["i1"], recommendations=["r1"])
    ]
    plan = stage.build_plan(state, feedback=None)
    survey = next(i for i in plan["items"] if i["id"] == "eda:survey")
    assert survey["status"] == "done"
    assert survey["existing_artifact_ref"] == "data_exploration[-1]"


def test_data_exploration_feedback_prevents_bypass():
    stage = DataExplorationStage()
    state = create_initial_state(session_id="s1", user_id="u1", research_topic="t")
    from agentlabx.core.state import EDAResult

    state["data_exploration"] = [
        EDAResult(findings=["f1"], data_quality_issues=[], recommendations=[])
    ]
    plan = stage.build_plan(state, feedback="double-check quality")
    survey = next(i for i in plan["items"] if i["id"] == "eda:survey")
    assert survey["status"] == "todo"
