"""peer_review migration (Plan 7E B3)."""
from __future__ import annotations

from agentlabx.core.state import ReviewResult, create_initial_state
from agentlabx.stages.peer_review import PeerReviewStage


def test_peer_review_build_plan_itemizes_check_novelty_clarity_recommendation():
    stage = PeerReviewStage()
    state = create_initial_state(session_id="s1", user_id="u1", research_topic="t")
    plan = stage.build_plan(state, feedback=None)
    ids = {i["id"] for i in plan["items"]}
    assert "review:baselines-check" in ids
    assert "review:novelty" in ids
    assert "review:clarity" in ids
    assert "review:recommendation" in ids


def test_peer_review_build_plan_feedback_item():
    stage = PeerReviewStage()
    state = create_initial_state(session_id="s1", user_id="u1", research_topic="t")
    plan = stage.build_plan(state, feedback="weight novelty higher")
    fb = [i for i in plan["items"] if i["source"] == "feedback"]
    assert len(fb) >= 1


def test_peer_review_prior_bypass_marks_recommendation_done():
    stage = PeerReviewStage()
    state = create_initial_state(session_id="s1", user_id="u1", research_topic="t")
    state["review"] = [
        ReviewResult(
            decision="accept",
            scores={"novelty": 4.5, "clarity": 4.0},
            feedback="solid work",
            reviewer_id="r1",
        )
    ]
    plan = stage.build_plan(state, feedback=None)
    rec = next(i for i in plan["items"] if i["id"] == "review:recommendation")
    assert rec["status"] == "done"
    assert rec["existing_artifact_ref"] == "review[-1]"
