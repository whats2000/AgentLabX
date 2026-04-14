"""B3 regression: when every stage in a session fails, session resolves to
'failed', not 'completed'."""
from __future__ import annotations

import pytest


class AlwaysFailingProvider:
    """LLM provider stub that raises on every invocation."""

    is_mock = True  # Prevents PIAgent construction in executor

    async def ainvoke(self, *args, **kwargs):
        raise RuntimeError("simulated LLM auth failure")

    async def invoke(self, *args, **kwargs):
        raise RuntimeError("simulated LLM auth failure")

    async def query(self, *args, **kwargs):
        raise RuntimeError("simulated LLM auth failure")

    # BaseLLMProvider interface stubs
    @property
    def name(self) -> str:
        return "always_failing"


@pytest.mark.asyncio
async def test_session_fails_when_every_stage_errors():
    from agentlabx.core.session import SessionManager, SessionStatus
    from agentlabx.server.deps import build_default_registry
    from agentlabx.server.executor import PipelineExecutor
    import tempfile
    from pathlib import Path

    registry = build_default_registry()
    session_manager = SessionManager()

    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tmp:
        db_path = tmp.name
    try:
        executor = PipelineExecutor(
            registry=registry,
            session_manager=session_manager,
            llm_provider=AlwaysFailingProvider(),
            checkpoint_db_path=db_path,
        )
        await executor.initialize()

        # Use 2-stage sequence; very tight iteration cap so the pipeline exits quickly.
        # Each stage will raise on the first agent call → StageRunner records a
        # StageError in-band → graph.ainvoke() still returns normally → B3 bug causes
        # session.complete() when session.fail() should be called instead.
        session = session_manager.create_session(
            research_topic="failtest",
            user_id="harness",
            config_overrides={
                "pipeline": {
                    "default_sequence": ["literature_review", "plan_formulation"],
                    "max_total_iterations": 2,
                },
            },
        )
        running = await executor.start_session(session)

        # Await pipeline completion. The task may finish cleanly (B3 path) or with
        # an exception — either way, final session.status is the invariant we assert.
        try:
            await running.task
        except Exception:
            pass

        # INVARIANT: after all stages errored, session must be FAILED not COMPLETED.
        assert session.status == SessionStatus.FAILED, (
            f"B3 regression: expected session.status==FAILED after all stages errored; "
            f"got {session.status!r}. "
            f"session.complete() was called when session.fail() should have been."
        )

        await executor.close()
    finally:
        Path(db_path).unlink(missing_ok=True)


# ---------------------------------------------------------------------------
# Contract unit tests
# ---------------------------------------------------------------------------

from tests.harness.contracts.base import HarnessTrace
from tests.harness.contracts.transition import (
    SESSION_COMPLETION_REQUIRES_SUCCESS,
    TRANSITION_EVENTS_WELL_FORMED,
)


def test_session_completion_contract_fails_on_complete_after_all_fail():
    trace = HarnessTrace(test_id="t")
    trace.record_event({"type": "stage_started", "data": {"stage": "a"}})
    trace.record_event({"type": "stage_started", "data": {"stage": "b"}})
    trace.record_event({"type": "stage_failed", "data": {"stage": "a"}})
    trace.record_event({"type": "stage_failed", "data": {"stage": "b"}})
    trace.record_event({"type": "session_completed"})
    result = SESSION_COMPLETION_REQUIRES_SUCCESS.run(trace)
    assert not result.passed


def test_session_completion_contract_ok_without_completion():
    trace = HarnessTrace(test_id="t")
    trace.record_event({"type": "stage_failed", "data": {"stage": "a"}})
    # No session_completed event
    result = SESSION_COMPLETION_REQUIRES_SUCCESS.run(trace)
    assert result.passed


def test_transition_events_well_formed_ok():
    trace = HarnessTrace(test_id="t")
    trace.record_event({
        "type": "stage_transitioned",
        "data": {"from_stage": "a", "to_stage": "b", "reason": "default_sequence"},
    })
    assert TRANSITION_EVENTS_WELL_FORMED.run(trace).passed


def test_transition_events_well_formed_fails_on_missing_reason():
    trace = HarnessTrace(test_id="t")
    trace.record_event({
        "type": "stage_transitioned",
        "data": {"from_stage": "a", "to_stage": "b"},
    })
    assert not TRANSITION_EVENTS_WELL_FORMED.run(trace).passed
