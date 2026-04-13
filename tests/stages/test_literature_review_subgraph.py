"""literature_review runs via subgraph and produces a StagePlan."""
from __future__ import annotations

import pytest

from agentlabx.core.state import create_initial_state
from agentlabx.stages.base import StageContext
from agentlabx.stages.literature_review import LiteratureReviewStage
from agentlabx.stages.subgraph import StageSubgraphBuilder


def test_literature_review_build_plan_itemises_topic_survey_and_recent_papers():
    stage = LiteratureReviewStage()
    state = create_initial_state(
        session_id="s1",
        user_id="u1",
        research_topic="chain of thought for MATH",
    )
    plan = stage.build_plan(state, feedback=None)
    # Expect at least two todo items on a fresh invocation
    assert len(plan["items"]) >= 2
    assert any(i["id"] == "lit:topic-survey" for i in plan["items"])
    assert any(i["id"] == "lit:recent-papers" for i in plan["items"])
    # No feedback → no feedback item
    assert all(i["id"] != "lit:feedback-driven" for i in plan["items"])


def test_literature_review_build_plan_adds_feedback_item_when_feedback_given():
    stage = LiteratureReviewStage()
    state = create_initial_state(
        session_id="s1", user_id="u1", research_topic="t"
    )
    plan = stage.build_plan(state, feedback="need more RL methods")
    feedback_items = [i for i in plan["items"] if i["id"] == "lit:feedback-driven"]
    assert len(feedback_items) == 1
    assert feedback_items[0]["status"] == "todo"
    assert feedback_items[0]["source"] == "feedback"
    assert "RL methods" in feedback_items[0]["description"]


def test_literature_review_build_plan_marks_topic_survey_done_when_prior_output_exists():
    stage = LiteratureReviewStage()
    state = create_initial_state(
        session_id="s1", user_id="u1", research_topic="t"
    )
    # Simulate prior run having produced a LitReviewResult
    from agentlabx.core.state import LitReviewResult

    state["literature_review"] = [
        LitReviewResult(papers=[{"title": "foo"}], summary="prior summary")
    ]
    plan = stage.build_plan(state, feedback=None)

    topic_item = next(i for i in plan["items"] if i["id"] == "lit:topic-survey")
    assert topic_item["status"] == "done"
    assert topic_item["existing_artifact_ref"] is not None


def test_literature_review_build_plan_does_not_bypass_when_feedback_is_given():
    """Even with prior output, feedback forces re-execution."""
    stage = LiteratureReviewStage()
    state = create_initial_state(
        session_id="s1", user_id="u1", research_topic="t"
    )
    from agentlabx.core.state import LitReviewResult

    state["literature_review"] = [
        LitReviewResult(papers=[{"title": "foo"}], summary="prior")
    ]
    plan = stage.build_plan(state, feedback="need more on X")

    topic_item = next(i for i in plan["items"] if i["id"] == "lit:topic-survey")
    # Feedback means we should still re-survey — not bypass
    assert topic_item["status"] == "todo"


@pytest.mark.asyncio
async def test_literature_review_runs_through_subgraph_produces_stage_plan():
    """End-to-end: subgraph invocation records the plan in state."""
    stage = LiteratureReviewStage()
    compiled = StageSubgraphBuilder().compile(stage)
    state = create_initial_state(
        session_id="s1", user_id="u1", research_topic="cot math"
    )
    state["current_stage"] = "literature_review"

    # Registry-less context → run() returns early with backtrack status,
    # but build_plan still runs + writes stage_plans.
    result = await compiled.ainvoke(
        {
            "state": state,
            "context": StageContext(settings={}, event_bus=None, registry=None),
        },
        config={"configurable": {"thread_id": "t1"}},
    )
    assert "literature_review" in result["state"]["stage_plans"]
    assert len(result["state"]["stage_plans"]["literature_review"]) == 1
    assert len(result["state"]["stage_plans"]["literature_review"][0]["items"]) >= 2
