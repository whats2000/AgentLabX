"""Tests for StageRunner — reducer-aware LangGraph node wrapper."""

from __future__ import annotations

import pytest

from agentlabx.core.state import create_initial_state
from agentlabx.stages.base import BaseStage, StageContext, StageResult
from agentlabx.stages.runner import StageRunner


class SuccessStage(BaseStage):
    name = "success_stage"
    description = "Always succeeds"
    required_agents = []
    required_tools = []

    async def run(self, state, context):
        return StageResult(output={"key": "value"}, status="done", reason="Success")


class BacktrackStage(BaseStage):
    name = "backtrack_stage"
    description = "Always backtracks"
    required_agents = []
    required_tools = []

    async def run(self, state, context):
        return StageResult(
            output={},
            status="backtrack",
            next_hint="plan_formulation",
            reason="Data quality issues",
            feedback="Need better data",
        )


class FailingStage(BaseStage):
    name = "failing_stage"
    description = "Always fails"
    required_agents = []
    required_tools = []

    async def run(self, state, context):
        raise RuntimeError("Stage crashed")


class TestStageRunner:
    @pytest.fixture()
    def initial_state(self):
        return create_initial_state(session_id="s1", user_id="u1", research_topic="test")

    async def test_run_successful_stage(self, initial_state):
        runner = StageRunner(SuccessStage())
        update = await runner.run(initial_state)
        assert update["current_stage"] == "success_stage"
        assert update["total_iterations"] == 1
        assert "success_stage" in update["stage_iterations"]

    async def test_run_backtrack_stage(self, initial_state):
        runner = StageRunner(BacktrackStage())
        update = await runner.run(initial_state)
        assert update["next_stage"] == "plan_formulation"

    async def test_run_failing_stage_captures_error(self, initial_state):
        runner = StageRunner(FailingStage())
        update = await runner.run(initial_state)
        assert len(update["errors"]) == 1
        assert "Stage crashed" in update["errors"][0].message

    async def test_returns_partial_update(self, initial_state):
        """Verify runner returns partial dict, not full state spread."""
        runner = StageRunner(SuccessStage())
        update = await runner.run(initial_state)
        # Should NOT contain identity fields (those don't change)
        assert "session_id" not in update
        assert "user_id" not in update
        assert "research_topic" not in update

    async def test_stage_iterations_increment(self, initial_state):
        runner = StageRunner(SuccessStage())
        update1 = await runner.run(initial_state)
        assert update1["stage_iterations"]["success_stage"] == 1
        # Simulate merging update1 into state for second run
        merged = {**initial_state, **update1}
        update2 = await runner.run(merged)
        assert update2["stage_iterations"]["success_stage"] == 2
        assert update2["total_iterations"] == 2

    async def test_error_has_correct_type(self, initial_state):
        runner = StageRunner(FailingStage())
        update = await runner.run(initial_state)
        error = update["errors"][0]
        assert error.error_type == "RuntimeError"
        assert error.stage == "failing_stage"
        assert error.recovered is False

    async def test_success_stage_no_errors_key(self, initial_state):
        """Successful runs should not include 'errors' in partial update."""
        runner = StageRunner(SuccessStage())
        update = await runner.run(initial_state)
        assert "errors" not in update

    async def test_success_stage_next_stage_none(self, initial_state):
        """Stage with no hint returns next_stage=None."""
        runner = StageRunner(SuccessStage())
        update = await runner.run(initial_state)
        assert update["next_stage"] is None

    async def test_custom_context_passed_through(self, initial_state):
        """Custom StageContext is forwarded to stage.run()."""
        received_context: list[StageContext] = []

        class ContextCaptureStage(BaseStage):
            name = "ctx_capture"
            description = "Captures context"
            required_agents = []
            required_tools = []

            async def run(self, state, context):
                received_context.append(context)
                return StageResult(output={}, status="done", reason="ok")

        custom_ctx = StageContext(settings={"key": "val"}, event_bus=None, registry=None)
        runner = StageRunner(ContextCaptureStage(), context=custom_ctx)
        await runner.run(initial_state)
        assert received_context[0].settings == {"key": "val"}
