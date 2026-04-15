"""transition_node output contracts — session completion / fail semantics +
transition event well-formedness."""
from __future__ import annotations

from tests.harness.contracts.base import Contract, ContractResult, HarnessTrace, Severity


def _session_completion_requires_success(trace: HarnessTrace) -> ContractResult:
    cid = "transition.session_completion_requires_success"
    starts = trace.events_of_type("stage_started")
    completes = trace.events_of_type("stage_completed")
    fails = trace.events_of_type("stage_failed")
    session_failed = trace.events_of_type("session_failed")

    if not starts:
        return ContractResult.ok(cid)  # no stages ran, nothing to check

    # If every started stage failed AND none completed AND no session_failed was surfaced,
    # that's B3: total failure being silently accepted as normal completion.
    if len(fails) >= len(starts) and len(completes) == 0 and not session_failed:
        return ContractResult.fail(
            cid, severity=Severity.P1,
            detail=(
                f"All {len(starts)} stages errored ({len(fails)} stage_failed, "
                f"{len(completes)} stage_completed, no session_failed event) "
                f"— B3 regression: total failure silently accepted"
            ),
        )
    return ContractResult.ok(cid)


SESSION_COMPLETION_REQUIRES_SUCCESS = Contract(
    id="transition.session_completion_requires_success",
    check=_session_completion_requires_success,
    description="Session must not complete if every ran stage failed (B3 regression)",
)


def _transition_events_well_formed(trace: HarnessTrace) -> ContractResult:
    cid = "transition.events_well_formed"
    # Each stage_completed should have a stage name in its data
    for e in trace.events_of_type("stage_completed"):
        data = e.get("data") or {}
        stage = data.get("stage") or e.get("stage")
        if not stage:
            return ContractResult.fail(
                cid, severity=Severity.P1,
                detail=f"stage_completed event missing 'stage' field: {e}",
            )
    # Same for stage_started
    for e in trace.events_of_type("stage_started"):
        data = e.get("data") or {}
        stage = data.get("stage") or e.get("stage")
        if not stage:
            return ContractResult.fail(
                cid, severity=Severity.P1,
                detail=f"stage_started event missing 'stage' field: {e}",
            )
    return ContractResult.ok(cid)


TRANSITION_EVENTS_WELL_FORMED = Contract(
    id="transition.events_well_formed",
    check=_transition_events_well_formed,
    description="Every stage_started and stage_completed event carries a 'stage' field",
)
