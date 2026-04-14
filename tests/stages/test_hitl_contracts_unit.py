from __future__ import annotations

from tests.harness.contracts.base import HarnessTrace
from tests.harness.contracts.hitl import (
    CHECKPOINT_REACHED_INCLUDES_CONTROL_MODE,
    CHECKPOINT_APPROVE_ROUND_TRIP,
    APPROVE_409_WHEN_NO_EXECUTOR,
)


def test_control_mode_contract_passes_when_present():
    trace = HarnessTrace(test_id="t")
    trace.record_event({
        "type": "checkpoint_reached",
        "data": {"stage": "experimentation", "control_mode": "approve"},
    })
    assert CHECKPOINT_REACHED_INCLUDES_CONTROL_MODE.run(trace).passed


def test_control_mode_contract_fails_when_missing():
    trace = HarnessTrace(test_id="t")
    trace.record_event({
        "type": "checkpoint_reached",
        "data": {"stage": "experimentation"},
    })
    assert not CHECKPOINT_REACHED_INCLUDES_CONTROL_MODE.run(trace).passed


def test_control_mode_contract_ok_when_no_checkpoint_at_all():
    trace = HarnessTrace(test_id="t")
    assert CHECKPOINT_REACHED_INCLUDES_CONTROL_MODE.run(trace).passed


def test_round_trip_contract_passes_on_full_cycle():
    trace = HarnessTrace(test_id="t")
    trace.record_event({"type": "checkpoint_reached", "data": {"control_mode": "approve"}})
    trace.record_http(
        method="POST",
        path="/api/sessions/abc/checkpoint/approve",
        status=200,
        body={"ok": True},
    )
    trace.record_event({"type": "pipeline_resumed"})
    assert CHECKPOINT_APPROVE_ROUND_TRIP.run(trace).passed


def test_round_trip_contract_fails_when_no_resume_after_200():
    trace = HarnessTrace(test_id="t")
    trace.record_event({"type": "checkpoint_reached", "data": {"control_mode": "approve"}})
    trace.record_http(
        method="POST",
        path="/api/sessions/abc/checkpoint/approve",
        status=200,
        body={"ok": True},
    )
    # No pipeline_resumed event
    assert not CHECKPOINT_APPROVE_ROUND_TRIP.run(trace).passed


def test_round_trip_contract_ok_when_no_checkpoint():
    trace = HarnessTrace(test_id="t")
    assert CHECKPOINT_APPROVE_ROUND_TRIP.run(trace).passed


def test_409_contract_passes_on_correct_409():
    trace = HarnessTrace(test_id="t")
    trace.record_http(
        method="POST",
        path="/api/sessions/abc/checkpoint/approve",
        status=409,
        body={"detail": "no executor"},
    )
    assert APPROVE_409_WHEN_NO_EXECUTOR.run(trace).passed


def test_409_contract_fails_on_silent_200_with_no_executor_detail():
    trace = HarnessTrace(test_id="t")
    trace.record_http(
        method="POST",
        path="/api/sessions/abc/checkpoint/approve",
        status=200,
        body={"detail": "no executor"},
    )
    assert not APPROVE_409_WHEN_NO_EXECUTOR.run(trace).passed


def test_409_contract_ok_when_no_approve_calls():
    trace = HarnessTrace(test_id="t")
    assert APPROVE_409_WHEN_NO_EXECUTOR.run(trace).passed
