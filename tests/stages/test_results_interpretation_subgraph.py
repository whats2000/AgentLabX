"""results_interpretation migration (Plan 7E B3)."""
from __future__ import annotations

from agentlabx.core.state import create_initial_state
from agentlabx.stages.results_interpretation import ResultsInterpretationStage


def test_interp_build_plan_itemizes_metrics_hypotheses_narrative():
    stage = ResultsInterpretationStage()
    state = create_initial_state(session_id="s1", user_id="u1", research_topic="t")
    plan = stage.build_plan(state, feedback=None)
    ids = {i["id"] for i in plan["items"]}
    assert "interp:metrics" in ids
    assert "interp:hypothesis-updates" in ids
    assert "interp:narrative" in ids


def test_interp_build_plan_feedback_item():
    stage = ResultsInterpretationStage()
    state = create_initial_state(session_id="s1", user_id="u1", research_topic="t")
    plan = stage.build_plan(state, feedback="reconsider hypothesis 2")
    fb = [i for i in plan["items"] if i["source"] == "feedback"]
    assert len(fb) >= 1


def test_interp_prior_bypass_marks_narrative_done():
    stage = ResultsInterpretationStage()
    state = create_initial_state(session_id="s1", user_id="u1", research_topic="t")
    state["interpretation"] = ["Initial narrative analysis"]
    plan = stage.build_plan(state, feedback=None)
    narrative = next(i for i in plan["items"] if i["id"] == "interp:narrative")
    assert narrative["status"] == "done"
    assert narrative["existing_artifact_ref"] == "interpretation[-1]"


def test_interp_feedback_prevents_bypass():
    stage = ResultsInterpretationStage()
    state = create_initial_state(session_id="s1", user_id="u1", research_topic="t")
    state["interpretation"] = ["prior"]
    plan = stage.build_plan(state, feedback="reconsider")
    narrative = next(i for i in plan["items"] if i["id"] == "interp:narrative")
    assert narrative["status"] == "todo"
