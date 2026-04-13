"""Backtrack round-trip: counter increment, partial rollback, routing, transition_log."""
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
async def test_backtrack_round_trip(registry, monkeypatch):
    """Experimentation backtracks to literature_review; both stages re-run and complete."""
    calls: dict[str, int] = {
        "literature_review": 0,
        "plan_formulation": 0,
        "experimentation": 0,
    }

    async def fake_run(self, state):
        name = self.stage.name
        calls[name] = calls.get(name, 0) + 1
        update = {
            "current_stage": name,
            "stage_iterations": {
                **state.get("stage_iterations", {}),
                name: state.get("stage_iterations", {}).get(name, 0) + 1,
            },
            "total_iterations": state.get("total_iterations", 0) + 1,
        }
        if name == "experimentation" and calls["experimentation"] == 1:
            update["next_stage"] = "literature_review"
            update["backtrack_feedback"] = "need RL methods"
            return update
        update["next_stage"] = None
        return update

    monkeypatch.setattr(runner_mod.StageRunner, "run", fake_run)

    seq = ["literature_review", "plan_formulation", "experimentation"]
    graph = PipelineBuilder(
        registry=registry, preferences=SessionPreferences()
    ).build(stage_sequence=seq)

    state = create_initial_state(
        session_id="s1",
        user_id="u1",
        research_topic="t",
        default_sequence=seq,
        max_total_iterations=10,
    )

    result = await graph.ainvoke(
        state, config={"configurable": {"thread_id": "t1"}}
    )

    # Counter incremented for the backtrack edge
    assert (
        result["backtrack_attempts"].get("experimentation->literature_review")
        == 1
    )

    # Target stage actually re-ran — this is what a real backtrack looks like
    assert calls["literature_review"] >= 2

    # transition_log contains the backtrack edge with triggered_by="agent"
    backtrack_entries = [
        t for t in result["transition_log"]
        if t.from_stage == "experimentation"
        and t.to_stage == "literature_review"
    ]
    assert len(backtrack_entries) == 1
    assert backtrack_entries[0].triggered_by == "agent"
