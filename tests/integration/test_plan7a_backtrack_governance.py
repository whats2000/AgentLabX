"""End-to-end: backtrack governance — counter → escalation → fallback."""
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
async def test_per_edge_limit_escalates_and_forces_advance(registry, monkeypatch):
    """Experimentation always backtracks to literature_review — after hitting
    the per-edge limit, the handler escalates and force-advances to peer_review."""

    async def fake_run(self, state):
        name = self.stage.name
        it = state.get("stage_iterations", {}).get(name, 0) + 1
        update = {
            "current_stage": name,
            "stage_iterations": {**state.get("stage_iterations", {}), name: it},
            "total_iterations": state.get("total_iterations", 0) + 1,
        }
        if name == "experimentation":
            update["next_stage"] = "literature_review"
            update["backtrack_feedback"] = "need more lit"
        else:
            update["next_stage"] = None
        return update

    monkeypatch.setattr(runner_mod.StageRunner, "run", fake_run)

    seq = [
        "literature_review",
        "plan_formulation",
        "experimentation",
        "peer_review",
    ]
    # max_backtrack_attempts_per_edge=0 means zero backtracks are permitted on
    # any edge; the first backtrack request from experimentation immediately
    # triggers escalation.  This exercises the full escalation → forced-advance
    # path without needing the stage to re-execute after each backtrack (which
    # the routing prevents because a backtracked stage is added to
    # completed_stages and therefore skipped on the return journey).
    graph = PipelineBuilder(
        registry=registry,
        preferences=SessionPreferences(max_backtrack_attempts_per_edge=0),
    ).build(stage_sequence=seq)

    state = create_initial_state(
        session_id="s1",
        user_id="u1",
        research_topic="t",
        default_sequence=seq,
        max_total_iterations=30,
    )

    result = await graph.ainvoke(
        state, config={"configurable": {"thread_id": "t1"}}
    )

    # The per-edge gate must have escalated — errors contains the limit trip
    limit_errors = [
        e for e in result["errors"]
        if e.error_type == "backtrack_limit_exceeded"
    ]
    assert limit_errors, "expected a backtrack_limit_exceeded error"
    # The fallback target was peer_review — next in sequence after experimentation
    assert "peer_review" in result["completed_stages"]
