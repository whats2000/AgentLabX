"""StageRunner accumulates backtrack cost + plumbs feedback into state."""
import pytest

from agentlabx.core.state import CostTracker, create_initial_state
from agentlabx.stages.base import BaseStage, StageContext, StageResult
from agentlabx.stages.runner import StageRunner


class _FakeStage(BaseStage):
    name = "fake"
    description = "fake"
    required_agents: list[str] = []
    required_tools: list[str] = []
    zone = "discovery"

    def __init__(self, cost_delta: float, status: str, feedback: str | None):
        self._cost_delta = cost_delta
        self._status = status
        self._feedback = feedback

    async def run(self, state, context):
        # Simulate the stage incurring cost during its run
        state["cost_tracker"].add_usage(
            tokens_in=100, tokens_out=50, cost=self._cost_delta
        )
        return StageResult(
            output={},
            status=self._status,
            next_hint="literature_review" if self._status == "backtrack" else None,
            reason="test",
            feedback=self._feedback,
        )


@pytest.mark.asyncio
async def test_backtrack_status_accumulates_cost_delta_and_writes_feedback():
    state = create_initial_state(
        session_id="s1", user_id="u1", research_topic="t"
    )
    state["current_stage"] = "experimentation"
    state["cost_tracker"] = CostTracker(total_cost=10.0)

    runner = StageRunner(
        _FakeStage(cost_delta=3.5, status="backtrack", feedback="need RL methods"),
        context=StageContext(settings={}, event_bus=None, registry=None),
    )
    update = await runner.run(state)

    assert update["backtrack_cost_spent"] == pytest.approx(3.5)
    assert update["backtrack_feedback"] == "need RL methods"


@pytest.mark.asyncio
async def test_non_backtrack_status_does_not_accumulate_or_write():
    state = create_initial_state(
        session_id="s1", user_id="u1", research_topic="t"
    )
    state["current_stage"] = "experimentation"
    state["cost_tracker"] = CostTracker(total_cost=10.0)

    runner = StageRunner(
        _FakeStage(cost_delta=5.0, status="done", feedback=None),
        context=StageContext(settings={}, event_bus=None, registry=None),
    )
    update = await runner.run(state)

    assert "backtrack_cost_spent" not in update
    assert "backtrack_feedback" not in update
