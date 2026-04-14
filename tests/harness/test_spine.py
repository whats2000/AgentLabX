"""Phase 1 spine — end-to-end real-LLM test per station.

Each station test drives the live pipeline through one stage, captures a
post-stage snapshot, asserts the stage's contracts, and writes a trace artifact.

Subsequent stations reuse the same session — each station depends on the real
state produced by the previous one (spine chaining).

Mechanical fix applied (T14): _wait_for_stage_transition watches for
`stage_completed` and `stage_failed` events (what the pipeline actually
emits) rather than `stage_transitioned` (which does not exist in the
current pipeline implementation — transition_node only emits
`checkpoint_reached` when HITL approval is needed, not a generic event
on every transition).
"""
from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from tests.harness.contracts.base import HarnessTrace
from tests.harness.contracts.endpoints import (
    GRAPH_200_AFTER_TRANSITION,
    STAGE_PLANS_PRESENT,
)
from tests.harness.contracts.resolve_agent import model_plumbed_contract
from tests.harness.contracts.stage_nodes import (
    enter_emits_event,
    stage_plan_persisted,
    work_emits_agent_turn,
    evaluate_respects_iteration_bound,
)
from tests.harness.contracts.transition import (
    SESSION_COMPLETION_REQUIRES_SUCCESS,
    TRANSITION_EVENTS_WELL_FORMED,
)
from tests.harness.harness.capture import capture_llm_event
from tests.harness.harness.session import HarnessSession
from tests.harness.harness.snapshots import SnapshotStore
from tests.harness.harness.trace import write_trace_artifact


SNAPSHOT_ROOT = Path(__file__).parent / "runs" / "snapshots"
TRACE_ROOT = Path(__file__).parent / "runs" / "traces"


async def _wait_for_stage_transition(session: HarnessSession, from_stage: str, timeout: float = 180.0):
    """Wait for a stage_completed or stage_failed event for the given stage.

    Mechanical fix (T14): the pipeline does NOT emit `stage_transitioned` on every
    transition — transition_node only emits `checkpoint_reached` when HITL approval
    is required. The canonical signal that a stage has finished is `stage_completed`
    (success path) or `stage_failed` (exception path), both emitted by StageRunner.

    Times out if no terminal event for the target stage arrives within `timeout` seconds.
    """
    deadline = asyncio.get_event_loop().time() + timeout
    seen = 0
    while asyncio.get_event_loop().time() < deadline:
        new_events = session.events[seen:]
        for event in new_events:
            etype = event.get("type", "")
            data = event.get("data") or {}
            stage = data.get("stage") or event.get("stage", "")
            if stage == from_stage and etype in ("stage_completed", "stage_failed"):
                return event
        seen = len(session.events)
        await asyncio.sleep(0.5)
    raise asyncio.TimeoutError(
        f"No stage_completed/stage_failed for '{from_stage}' within {timeout}s. "
        f"Events seen: {[e.get('type') for e in session.events[-20:]]}"
    )


@pytest.mark.live_harness
@pytest.mark.asyncio
async def test_spine_literature_review():
    """Phase 1 spine: run literature_review end-to-end against real Gemini flash."""
    SNAPSHOT_ROOT.mkdir(parents=True, exist_ok=True)
    TRACE_ROOT.mkdir(parents=True, exist_ok=True)
    store = SnapshotStore(root=SNAPSHOT_ROOT)

    trace = HarnessTrace(test_id="spine.literature_review")

    async with HarnessSession.boot_live(topic="image super-resolution with diffusion priors") as session:
        # Feed events into trace as they arrive (session.events is already mirrored
        # by the HarnessSession bus-mirror; we just copy to the trace as we go)
        try:
            # The pipeline is already running in a bg task. Wait for literature_review
            # to complete (stage_completed or stage_failed).
            await _wait_for_stage_transition(session, from_stage="literature_review", timeout=240.0)
        finally:
            # Copy all bus events into trace now (single pass)
            for e in session.events:
                trace.record_event(e)
                capture_llm_event(e, trace)

        # Snapshot pipeline state
        pipeline_state = await session.get_state()
        store.save("after_literature_review", pipeline_state)
        trace.snapshot("after_literature_review", pipeline_state)

    # Run contracts
    contracts = [
        enter_emits_event(stage_name="literature_review"),
        stage_plan_persisted(stage_name="literature_review"),
        work_emits_agent_turn(stage_name="literature_review"),
        evaluate_respects_iteration_bound(stage_name="literature_review"),
        model_plumbed_contract(expected_prefix="gemini/"),
        TRANSITION_EVENTS_WELL_FORMED,
        SESSION_COMPLETION_REQUIRES_SUCCESS,
    ]
    results = [c.run(trace) for c in contracts]
    trace.results.extend(results)

    # Write trace artifact regardless of pass/fail (debugging aid)
    artifact = write_trace_artifact(trace, root=TRACE_ROOT)
    print(f"Trace written to: {artifact}")

    failures = [r for r in results if not r.passed]
    assert not failures, (
        f"Contract failures: "
        + "\n".join(f"  - {f.contract_id} [{f.severity.value if f.severity else '?'}]: {f.detail}" for f in failures)
    )
