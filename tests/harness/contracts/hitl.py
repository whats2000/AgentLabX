"""HITL contracts — /checkpoint/approve round-trip, 409 guards, control_mode field.

The control_mode field was added to checkpoint_reached events in Plan 7E C1.
The 409 guard was added in Plan 7E A2. Both contracts catch regressions.
"""
from __future__ import annotations

from tests.harness.contracts.base import Contract, ContractResult, HarnessTrace, Severity


def _control_mode_present(trace: HarnessTrace) -> ContractResult:
    cid = "hitl.checkpoint_reached_includes_control_mode"
    for e in trace.events_of_type("checkpoint_reached"):
        data = e.get("data") or {}
        if "control_mode" not in data:
            return ContractResult.fail(
                cid, severity=Severity.P2,
                detail=f"checkpoint_reached missing data.control_mode: {e}",
            )
    return ContractResult.ok(cid)


def _approve_round_trip(trace: HarnessTrace) -> ContractResult:
    cid = "hitl.approve_round_trip"
    if not trace.events_of_type("checkpoint_reached"):
        return ContractResult.ok(cid)
    approve_calls = [
        r for r in trace.http
        if r["method"] == "POST"
        and r["path"].endswith("/checkpoint/approve")
        and r["status"] == 200
    ]
    if not approve_calls:
        return ContractResult.ok(cid)  # checkpoint was hit but not approved; not this contract's concern
    resumes = trace.events_of_type("pipeline_resumed")
    if not resumes:
        return ContractResult.fail(
            cid, severity=Severity.P1,
            detail=(
                "approve POST returned 200 but no pipeline_resumed event followed "
                "(paused_event.set() likely not called)"
            ),
        )
    return ContractResult.ok(cid)


def _approve_409_when_no_executor(trace: HarnessTrace) -> ContractResult:
    cid = "hitl.approve_409_when_no_executor"
    # Look for the anti-pattern: approve returned 200 but body says "no executor"
    bad_calls = [
        r for r in trace.http
        if r["method"] == "POST"
        and r["path"].endswith("/checkpoint/approve")
        and r["status"] == 200
        and isinstance(r.get("body"), dict)
        and r["body"].get("detail") == "no executor"
    ]
    if bad_calls:
        return ContractResult.fail(
            cid, severity=Severity.P1,
            detail=(
                "approve returned 200 when it should have returned 409 "
                "(executor missing — A2 regression)"
            ),
        )
    return ContractResult.ok(cid)


CHECKPOINT_REACHED_INCLUDES_CONTROL_MODE = Contract(
    id="hitl.checkpoint_reached_includes_control_mode",
    check=_control_mode_present,
    description="checkpoint_reached events must carry data.control_mode (Plan 7E C1)",
)

CHECKPOINT_APPROVE_ROUND_TRIP = Contract(
    id="hitl.approve_round_trip",
    check=_approve_round_trip,
    description="After a successful /checkpoint/approve 200, pipeline_resumed must fire",
)

APPROVE_409_WHEN_NO_EXECUTOR = Contract(
    id="hitl.approve_409_when_no_executor",
    check=_approve_409_when_no_executor,
    description="/checkpoint/approve must return 409 (not 200) when no executor (Plan 7E A2)",
)
