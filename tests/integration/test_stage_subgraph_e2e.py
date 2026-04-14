"""End-to-end: subgraph-based stages + StagePlans + lab_meeting exclusion."""
from __future__ import annotations

import pytest

from agentlabx.core.pipeline import PipelineBuilder
from agentlabx.core.registry import PluginRegistry
from agentlabx.core.session import SessionPreferences
from agentlabx.core.state import create_initial_state
from agentlabx.plugins._builtin import register_builtin_plugins
from agentlabx.stages import runner as runner_mod


@pytest.fixture
def registry():
    r = PluginRegistry()
    register_builtin_plugins(r)
    return r


@pytest.mark.asyncio
async def test_lab_meeting_excluded_from_top_level_graph(registry):
    """Including lab_meeting in the requested sequence must not add a top-level node."""
    seq = [
        "literature_review",
        "plan_formulation",
        "lab_meeting",
        "experimentation",
    ]
    graph = PipelineBuilder(
        registry=registry, preferences=SessionPreferences()
    ).build(stage_sequence=seq)
    node_ids = set(graph.get_graph().nodes)
    assert "lab_meeting" not in node_ids
    assert "literature_review" in node_ids
    assert "experimentation" in node_ids


@pytest.mark.asyncio
async def test_pipeline_run_populates_stage_plans_for_each_executed_stage(
    registry, monkeypatch
):
    """Every stage that runs through the subgraph records a StagePlan entry."""

    # Minimal fake_run to avoid calling real agents; runs each stage once.
    async def fake_run(self, state, context):
        from agentlabx.stages.base import StageResult
        return StageResult(
            output={},
            status="done",
            reason=f"{self.name} ok",
        )

    # Patch each concrete class individually — BaseStage.run is abstract and
    # each concrete stage overrides it, so patching BaseStage alone won't
    # affect subclasses that already defined their own run().
    from agentlabx.stages.literature_review import LiteratureReviewStage
    from agentlabx.stages.plan_formulation import PlanFormulationStage
    from agentlabx.stages.experimentation import ExperimentationStage

    for cls in [LiteratureReviewStage, PlanFormulationStage, ExperimentationStage]:
        monkeypatch.setattr(cls, "run", fake_run)

    seq = ["literature_review", "plan_formulation", "experimentation"]
    graph = PipelineBuilder(
        registry=registry, preferences=SessionPreferences()
    ).build(stage_sequence=seq)

    state = create_initial_state(
        session_id="s1",
        user_id="u1",
        research_topic="cot math",
        default_sequence=seq,
        max_total_iterations=10,
    )

    result = await graph.ainvoke(
        state, config={"configurable": {"thread_id": "t1"}}
    )

    for stage_name in seq:
        assert stage_name in result["stage_plans"], (
            f"Expected stage_plans to include {stage_name!r} after run, "
            f"got keys {list(result['stage_plans'].keys())}"
        )
        assert len(result["stage_plans"][stage_name]) >= 1


@pytest.mark.asyncio
async def test_backtrack_still_works_through_subgraph_stages(registry, monkeypatch):
    """A stage emitting status=backtrack from inside its subgraph still triggers partial rollback + counter increment via the transition handler."""
    calls: dict[str, int] = {
        "literature_review": 0,
        "plan_formulation": 0,
        "experimentation": 0,
    }

    async def fake_run(self, state, context):
        from agentlabx.stages.base import StageResult
        name = self.name
        calls[name] = calls.get(name, 0) + 1
        if name == "experimentation" and calls["experimentation"] == 1:
            return StageResult(
                output={},
                status="backtrack",
                next_hint="literature_review",
                reason="need more lit",
                feedback="need RL methods",
            )
        return StageResult(output={}, status="done", reason=f"{name} ok")

    # Patch each concrete class individually for the same reason as above.
    from agentlabx.stages.literature_review import LiteratureReviewStage
    from agentlabx.stages.plan_formulation import PlanFormulationStage
    from agentlabx.stages.experimentation import ExperimentationStage

    for cls in [LiteratureReviewStage, PlanFormulationStage, ExperimentationStage]:
        monkeypatch.setattr(cls, "run", fake_run)

    seq = ["literature_review", "plan_formulation", "experimentation"]
    graph = PipelineBuilder(
        registry=registry, preferences=SessionPreferences()
    ).build(stage_sequence=seq)

    state = create_initial_state(
        session_id="s1",
        user_id="u1",
        research_topic="cot math",
        default_sequence=seq,
        max_total_iterations=30,
    )

    result = await graph.ainvoke(
        state, config={"configurable": {"thread_id": "t2"}}
    )

    # Backtrack counter must have fired exactly once for the edge
    assert result["backtrack_attempts"].get(
        "experimentation->literature_review"
    ) == 1

    # literature_review ran at least twice (once forward, once on re-entry)
    assert calls["literature_review"] >= 2

    # literature_review stage_plans list should have two entries — one per entry
    assert len(result["stage_plans"]["literature_review"]) >= 2
