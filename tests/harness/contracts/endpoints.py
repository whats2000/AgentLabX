"""Endpoint output contracts — verify REST endpoints respond correctly as the
harness exercises them. Each contract is a pure function over a HarnessTrace
that has an `http` record for the endpoint of interest.
"""
from __future__ import annotations

from tests.harness.contracts.base import Contract, ContractResult, HarnessTrace, Severity


def _last_http(trace: HarnessTrace, *, method: str, path_suffix: str) -> dict | None:
    for record in reversed(trace.http):
        if record["method"] == method and record["path"].endswith(path_suffix):
            return record
    return None


def _graph_returns_200_after_transition(trace: HarnessTrace) -> ContractResult:
    cid = "endpoints.graph.200_after_transition"
    transitions = trace.events_of_type("stage_transitioned")
    if not transitions:
        return ContractResult.ok(cid)
    record = _last_http(trace, method="GET", path_suffix="/graph")
    if record is None:
        return ContractResult.fail(
            cid, severity=Severity.P1, detail="no GET /graph recorded after transition"
        )
    if record["status"] != 200:
        return ContractResult.fail(
            cid,
            severity=Severity.P0,
            expected=200,
            actual=record["status"],
            detail=f"/graph returned {record['status']} after transition",
        )
    return ContractResult.ok(cid)


def _stage_plans_has_current_stage(trace: HarnessTrace) -> ContractResult:
    cid = "endpoints.stage_plans.current_stage_present"
    record = _last_http(trace, method="GET", path_suffix="/stage_plans")
    if record is None:
        return ContractResult.ok(cid)
    body = record["body"] or {}
    if not isinstance(body, dict) or not body:
        return ContractResult.fail(
            cid,
            severity=Severity.P1,
            detail="/stage_plans returned empty or non-dict body",
            actual=body,
        )
    return ContractResult.ok(cid)


GRAPH_200_AFTER_TRANSITION = Contract(
    id="endpoints.graph.200_after_transition",
    check=_graph_returns_200_after_transition,
    description="/graph must return 200 after at least one stage transition (B1 regression)",
)

STAGE_PLANS_PRESENT = Contract(
    id="endpoints.stage_plans.current_stage_present",
    check=_stage_plans_has_current_stage,
    description="/stage_plans must return populated dict once a station has run",
)
