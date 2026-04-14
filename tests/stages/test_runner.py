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

    async def test_stage_output_merged_into_update(self, initial_state):
        """Stage output keys are merged into the update dict so LangGraph reducers apply."""
        from agentlabx.core.state import LitReviewResult

        class LitReviewProducer(BaseStage):
            name = "lit_producer"
            description = "Produces literature review output"
            required_agents = []
            required_tools = []

            async def run(self, state, context):
                result = LitReviewResult(
                    papers=[{"title": "Test paper"}],
                    summary="Test summary",
                )
                return StageResult(
                    output={"literature_review": [result]},
                    status="done",
                    reason="Lit review produced",
                )

        runner = StageRunner(LitReviewProducer())
        update = await runner.run(initial_state)
        # Output key should be present in update so LangGraph reducer can append
        assert "literature_review" in update
        assert len(update["literature_review"]) == 1
        assert update["literature_review"][0].summary == "Test summary"

    async def test_runner_tracking_overrides_stage_output(self, initial_state):
        """Runner-owned fields (current_stage) always win over stage output."""

        class MaliciousStage(BaseStage):
            name = "correct_name"
            description = "Tries to set current_stage to wrong value"
            required_agents = []
            required_tools = []

            async def run(self, state, context):
                return StageResult(
                    output={"current_stage": "WRONG", "total_iterations": 999},
                    status="done",
                    reason="test",
                )

        runner = StageRunner(MaliciousStage())
        update = await runner.run(initial_state)
        assert update["current_stage"] == "correct_name"
        assert update["total_iterations"] == 1

    async def test_multiple_output_keys_all_merged(self, initial_state):
        """A stage can write to multiple state keys at once."""
        from agentlabx.core.state import Hypothesis, ResearchPlan

        class PlanProducer(BaseStage):
            name = "plan_producer"
            description = "Produces plan and hypotheses"
            required_agents = []
            required_tools = []

            async def run(self, state, context):
                plan = ResearchPlan(
                    goals=["Goal 1"],
                    methodology="Method",
                    hypotheses=["H1"],
                    full_text="text",
                )
                hyp = Hypothesis(
                    id="H1",
                    statement="test hypothesis",
                    status="active",
                    created_at_stage="plan_producer",
                )
                return StageResult(
                    output={"plan": [plan], "hypotheses": [hyp]},
                    status="done",
                    reason="done",
                )

        runner = StageRunner(PlanProducer())
        update = await runner.run(initial_state)
        assert "plan" in update
        assert "hypotheses" in update
        assert len(update["plan"]) == 1
        assert len(update["hypotheses"]) == 1

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


class TestStageRunnerEvents:
    @pytest.fixture()
    def initial_state(self):
        return create_initial_state(session_id="s1", user_id="u1", research_topic="test")

    async def test_emits_stage_started_event(self, initial_state):
        from agentlabx.core.events import Event, EventBus

        bus = EventBus()
        received: list[Event] = []

        async def handler(event: Event) -> None:
            received.append(event)

        bus.subscribe("stage_started", handler)

        ctx = StageContext(settings={}, event_bus=bus, registry=None)
        runner = StageRunner(SuccessStage(), context=ctx)
        await runner.run(initial_state)
        assert len(received) == 1
        assert received[0].data["stage"] == "success_stage"

    async def test_emits_stage_completed_on_success(self, initial_state):
        from agentlabx.core.events import Event, EventBus

        bus = EventBus()
        received: list[Event] = []

        async def handler(event: Event) -> None:
            received.append(event)

        bus.subscribe("stage_completed", handler)

        ctx = StageContext(settings={}, event_bus=bus, registry=None)
        runner = StageRunner(SuccessStage(), context=ctx)
        await runner.run(initial_state)
        assert len(received) == 1
        assert received[0].data["status"] == "done"

    async def test_emits_stage_failed_on_exception(self, initial_state):
        from agentlabx.core.events import Event, EventBus

        bus = EventBus()
        received: list[Event] = []

        async def handler(event: Event) -> None:
            received.append(event)

        bus.subscribe("stage_failed", handler)

        ctx = StageContext(settings={}, event_bus=bus, registry=None)
        runner = StageRunner(FailingStage(), context=ctx)
        await runner.run(initial_state)
        assert len(received) == 1
        assert "Stage crashed" in received[0].data["message"]

    async def test_failed_does_not_emit_completed(self, initial_state):
        """Fix K: stage_completed and stage_failed are mutually exclusive."""
        from agentlabx.core.events import Event, EventBus

        bus = EventBus()
        received_completed: list[Event] = []
        received_failed: list[Event] = []

        async def on_completed(event: Event) -> None:
            received_completed.append(event)

        async def on_failed(event: Event) -> None:
            received_failed.append(event)

        bus.subscribe("stage_completed", on_completed)
        bus.subscribe("stage_failed", on_failed)

        ctx = StageContext(settings={}, event_bus=bus, registry=None)
        runner = StageRunner(FailingStage(), context=ctx)
        await runner.run(initial_state)
        assert len(received_failed) == 1
        assert len(received_completed) == 0  # Never both

    async def test_paused_event_blocks_execution(self, initial_state):
        """Fix A: paused_event.wait() blocks stage.run when cleared."""
        import asyncio

        paused_event = asyncio.Event()
        # Don't set it — starts in cleared (paused) state
        ctx = StageContext(
            settings={},
            event_bus=None,
            registry=None,
            paused_event=paused_event,
        )
        runner = StageRunner(SuccessStage(), context=ctx)

        # Start the runner — it should block on paused_event.wait()
        task = asyncio.create_task(runner.run(initial_state))
        # Give it a moment to reach the wait
        await asyncio.sleep(0.05)
        assert not task.done()

        # Resume by setting the event
        paused_event.set()
        result = await asyncio.wait_for(task, timeout=2.0)
        assert result["current_stage"] == "success_stage"

    async def test_paused_event_none_runs_immediately(self, initial_state):
        """paused_event=None → no pause support, runs through."""
        ctx = StageContext(settings={}, event_bus=None, registry=None, paused_event=None)
        runner = StageRunner(SuccessStage(), context=ctx)
        result = await runner.run(initial_state)
        assert result["current_stage"] == "success_stage"

    async def test_runner_clears_internal_node_cursor_on_exit(self, initial_state):
        """StageRunner sets current_stage_internal_node=None after subgraph exits."""
        runner = StageRunner(SuccessStage())
        update = await runner.run(initial_state)
        assert update["current_stage_internal_node"] is None
