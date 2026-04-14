from __future__ import annotations

from tests.harness.contracts.base import HarnessTrace
from tests.harness.contracts.pi_advisor import (
    PI_VERDICT_IN_VOCAB,
    PI_EMITS_AGENT_TURN,
)


def test_verdict_contract_passes_on_approve():
    trace = HarnessTrace(test_id="t")
    trace.record_event({"type": "pi_verdict", "data": {"verdict": "approve"}})
    assert PI_VERDICT_IN_VOCAB.run(trace).passed


def test_verdict_contract_fails_on_garbage():
    trace = HarnessTrace(test_id="t")
    trace.record_event({"type": "pi_verdict", "data": {"verdict": "sure thing boss"}})
    assert not PI_VERDICT_IN_VOCAB.run(trace).passed


def test_verdict_contract_ok_when_no_verdict_event():
    """When no PI verdict was issued, the contract vacuously passes."""
    trace = HarnessTrace(test_id="t")
    assert PI_VERDICT_IN_VOCAB.run(trace).passed


def test_turn_contract_passes_when_turn_surrounds_verdict():
    trace = HarnessTrace(test_id="t")
    trace.record_event({"type": "pi_agent_turn_started"})
    trace.record_event({"type": "pi_verdict", "data": {"verdict": "approve"}})
    trace.record_event({"type": "pi_agent_turn_completed"})
    assert PI_EMITS_AGENT_TURN.run(trace).passed


def test_turn_contract_fails_when_verdict_without_turn():
    trace = HarnessTrace(test_id="t")
    trace.record_event({"type": "pi_verdict", "data": {"verdict": "revise"}})
    # No pi_agent_turn_started or pi_agent_turn_completed
    assert not PI_EMITS_AGENT_TURN.run(trace).passed


def test_turn_contract_ok_when_no_verdicts_at_all():
    trace = HarnessTrace(test_id="t")
    assert PI_EMITS_AGENT_TURN.run(trace).passed
