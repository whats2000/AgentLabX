"""transition_node output contracts — session completion / fail semantics +
transition event well-formedness."""
from __future__ import annotations

from tests.harness.contracts.base import Contract, ContractResult, HarnessTrace, Severity


def _session_completion_requires_success(trace: HarnessTrace) -> ContractResult:
    cid = "transition.session_completion_requires_success"
    completions = trace.events_of_type("session_completed")
    failed_stages = trace.events_of_type("stage_failed")
    if completions and failed_stages:
        started = trace.events_of_type("stage_started")
        if started and len(failed_stages) >= len(started):
            return ContractResult.fail(
                cid,
                severity=Severity.P1,
                detail=(
                    f"session completed with {len(failed_stages)} stage_failed events "
                    f"({len(started)} stages started) — B3 regression"
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
    for e in trace.events_of_type("stage_transitioned"):
        data = e.get("data") or {}
        # tolerate either nested-data or flat shape
        from_stage = data.get("from_stage") or e.get("from_stage")
        to_stage = data.get("to_stage") or e.get("to_stage")
        reason = data.get("reason") or e.get("reason")
        if not (from_stage and to_stage and reason):
            return ContractResult.fail(
                cid,
                severity=Severity.P1,
                detail=f"stage_transitioned event missing from_stage/to_stage/reason: {e}",
            )
    return ContractResult.ok(cid)


TRANSITION_EVENTS_WELL_FORMED = Contract(
    id="transition.events_well_formed",
    check=_transition_events_well_formed,
    description="Every stage_transitioned event carries from_stage, to_stage, reason",
)
