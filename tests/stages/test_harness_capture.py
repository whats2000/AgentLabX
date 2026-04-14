from __future__ import annotations

from tests.harness.contracts.base import HarnessTrace
from tests.harness.harness.capture import capture_llm_event


def test_capture_maps_llm_request_to_trace():
    """Test capturing a real agent_llm_request event from the event bus.

    Real event structure (from HarnessSession._on_bus_event):
    {
        "type": "agent_llm_request",
        "source": "agent_name",
        "data": {
            "prompt": "...",
            "system_prompt": "...",
            ...
        },
        "timestamp": "..."
    }

    Note: The real event is missing "messages", "tools", "node", "stage" fields.
    These are architectural limitations noted in the reality check.
    """
    trace = HarnessTrace(test_id="t1")
    event = {
        "type": "agent_llm_request",
        "source": "phd_student",
        "data": {
            "model": "claude-sonnet-4-6",
            "prompt": "hello",
            "system_prompt": "You are a PhD student.",
            "temperature": 0.0,
            "is_mock": False,
            "turn_id": "turn123",
            "parent_turn_id": None,
        },
        "timestamp": "2026-04-15T10:00:00+00:00",
    }
    capture_llm_event(event, trace)
    assert len(trace.prompts) == 1
    # Extract what we can from the real event structure
    assert trace.prompts[0]["agent"] == "phd_student"


def test_capture_ignores_non_llm_events():
    trace = HarnessTrace(test_id="t1")
    capture_llm_event({"type": "stage_started"}, trace)
    assert len(trace.prompts) == 0
