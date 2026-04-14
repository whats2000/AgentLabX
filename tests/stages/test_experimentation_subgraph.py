"""experimentation migration (Plan 7E B2) — baseline/main/ablation structure."""
from __future__ import annotations

from datetime import datetime

from agentlabx.core.state import (
    ExperimentResult, ReproducibilityRecord, create_initial_state,
)
from agentlabx.stages.experimentation import ExperimentationStage


def _make_experiment(tag: str) -> ExperimentResult:
    """Minimal ExperimentResult fixture. ExperimentResult.tag holds 'baseline'/'main'/'ablation'."""
    return ExperimentResult(
        tag=tag,  # type: ignore[arg-type]
        metrics={"accuracy": 0.5},
        description=f"{tag} experiment",
        reproducibility=ReproducibilityRecord(
            random_seed=42,
            environment_hash="x",
            run_command="x",
            timestamp=datetime.now(),
        ),
    )


def test_experimentation_build_plan_itemizes_baseline_main_ablation():
    stage = ExperimentationStage()
    state = create_initial_state(session_id="s1", user_id="u1", research_topic="t")
    plan = stage.build_plan(state, feedback=None)
    ids = {i["id"] for i in plan["items"]}
    assert "exp:baseline" in ids
    assert "exp:main" in ids
    assert "exp:ablation" in ids


def test_experimentation_prior_bypass_marks_baseline_done_when_present():
    stage = ExperimentationStage()
    state = create_initial_state(session_id="s1", user_id="u1", research_topic="t")
    state["experiment_results"] = [_make_experiment("baseline")]
    plan = stage.build_plan(state, feedback=None)
    baseline = next(i for i in plan["items"] if i["id"] == "exp:baseline")
    assert baseline["status"] == "done"


def test_experimentation_all_tags_present_all_items_done():
    stage = ExperimentationStage()
    state = create_initial_state(session_id="s1", user_id="u1", research_topic="t")
    state["experiment_results"] = [
        _make_experiment("baseline"),
        _make_experiment("main"),
        _make_experiment("ablation"),
    ]
    plan = stage.build_plan(state, feedback=None)
    statuses = {
        i["id"]: i["status"]
        for i in plan["items"]
        if i["id"].startswith("exp:") and i["id"] != "exp:feedback-driven"
    }
    assert statuses["exp:baseline"] == "done"
    assert statuses["exp:main"] == "done"
    assert statuses["exp:ablation"] == "done"


def test_experimentation_feedback_prevents_all_bypasses():
    stage = ExperimentationStage()
    state = create_initial_state(session_id="s1", user_id="u1", research_topic="t")
    state["experiment_results"] = [_make_experiment("baseline")]
    plan = stage.build_plan(state, feedback="try different seed")
    baseline = next(i for i in plan["items"] if i["id"] == "exp:baseline")
    assert baseline["status"] == "todo"
