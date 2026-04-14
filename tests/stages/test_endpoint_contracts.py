"""Unit tests for endpoint contracts. Pure contract-function tests — no live HTTP."""
from __future__ import annotations

from tests.harness.contracts.base import HarnessTrace
from tests.harness.contracts.endpoints import (
    GRAPH_200_AFTER_TRANSITION,
    STAGE_PLANS_PRESENT,
)


def test_graph_contract_passes_when_http_200_after_transition():
    trace = HarnessTrace(test_id="t")
    trace.record_event({"type": "stage_transitioned"})
    trace.record_http(method="GET", path="/api/sessions/abc/graph", status=200, body={"nodes": [], "edges": []})
    result = GRAPH_200_AFTER_TRANSITION.run(trace)
    assert result.passed


def test_graph_contract_fails_on_500():
    trace = HarnessTrace(test_id="t")
    trace.record_event({"type": "stage_transitioned"})
    trace.record_http(method="GET", path="/api/sessions/abc/graph", status=500, body=None)
    result = GRAPH_200_AFTER_TRANSITION.run(trace)
    assert not result.passed
    assert result.severity.value == "P0"


def test_graph_contract_ok_when_no_transition_yet():
    """Before any transition, absence of /graph call is fine."""
    trace = HarnessTrace(test_id="t")
    result = GRAPH_200_AFTER_TRANSITION.run(trace)
    assert result.passed


def test_stage_plans_contract_fails_on_empty_body():
    trace = HarnessTrace(test_id="t")
    trace.record_http(method="GET", path="/api/sessions/abc/stage_plans", status=200, body={})
    result = STAGE_PLANS_PRESENT.run(trace)
    assert not result.passed


def test_stage_plans_contract_passes_with_populated_body():
    trace = HarnessTrace(test_id="t")
    trace.record_http(
        method="GET",
        path="/api/sessions/abc/stage_plans",
        status=200,
        body={"literature_review": {"items": [{"id": "a"}]}},
    )
    result = STAGE_PLANS_PRESENT.run(trace)
    assert result.passed


def test_stage_plans_contract_ok_when_no_call_yet():
    trace = HarnessTrace(test_id="t")
    result = STAGE_PLANS_PRESENT.run(trace)
    assert result.passed
