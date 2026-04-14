"""Unit tests for contract base types — pure dataclass behavior, no live model."""
from __future__ import annotations

from tests.harness.contracts.base import Contract, ContractResult, HarnessTrace, Severity


def test_contract_result_ok():
    r = ContractResult.ok("enter_emits_event")
    assert r.passed is True
    assert r.contract_id == "enter_emits_event"
    assert r.severity is None


def test_contract_result_fail():
    r = ContractResult.fail(
        "enter_emits_event",
        severity=Severity.P1,
        actual="no event",
        expected="stage_internal_node_changed(enter)",
    )
    assert r.passed is False
    assert r.severity is Severity.P1
    assert "no event" in r.detail


def test_harness_trace_records_events():
    trace = HarnessTrace(test_id="t1")
    trace.record_event({"type": "stage_started", "stage": "literature_review"})
    assert len(trace.events) == 1
    assert trace.events[0]["type"] == "stage_started"


def test_harness_trace_records_prompt():
    trace = HarnessTrace(test_id="t1")
    trace.record_prompt(
        node="work",
        stage="literature_review",
        agent="phd_student",
        messages=[{"role": "user", "content": "hi"}],
    )
    assert len(trace.prompts) == 1
    assert trace.prompts[0]["node"] == "work"


def test_contract_invokes_check():
    def check(trace: HarnessTrace) -> ContractResult:
        if any(e.get("type") == "stage_started" for e in trace.events):
            return ContractResult.ok("stage_started_present")
        return ContractResult.fail("stage_started_present", severity=Severity.P1)

    c = Contract(id="stage_started_present", check=check)
    trace = HarnessTrace(test_id="t1")
    trace.record_event({"type": "stage_started"})
    result = c.run(trace)
    assert result.passed
