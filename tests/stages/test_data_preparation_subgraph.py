"""data_preparation migration (Plan 7E B2)."""
from __future__ import annotations

from agentlabx.core.state import create_initial_state
from agentlabx.stages.data_preparation import DataPreparationStage


def test_data_preparation_build_plan_itemizes_clean_features_code():
    stage = DataPreparationStage()
    state = create_initial_state(session_id="s1", user_id="u1", research_topic="t")
    plan = stage.build_plan(state, feedback=None)
    ids = {i["id"] for i in plan["items"]}
    assert "prep:clean" in ids
    assert "prep:features" in ids
    assert "prep:pipeline-code" in ids


def test_data_preparation_build_plan_feedback_item():
    stage = DataPreparationStage()
    state = create_initial_state(session_id="s1", user_id="u1", research_topic="t")
    plan = stage.build_plan(state, feedback="fix float precision bug")
    fb = [i for i in plan["items"] if i["source"] == "feedback"]
    assert len(fb) >= 1


def test_data_preparation_prior_bypass_marks_pipeline_code_done():
    stage = DataPreparationStage()
    state = create_initial_state(session_id="s1", user_id="u1", research_topic="t")
    state["dataset_code"] = ["# prior prep code"]
    plan = stage.build_plan(state, feedback=None)
    code = next(i for i in plan["items"] if i["id"] == "prep:pipeline-code")
    assert code["status"] == "done"
    assert code["existing_artifact_ref"] == "dataset_code[-1]"
