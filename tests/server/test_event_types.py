"""Tests for EventTypes constants."""

from __future__ import annotations


def test_event_type_constants():
    from agentlabx.server.events import EventTypes

    for name in (
        "STAGE_STARTED",
        "STAGE_COMPLETED",
        "STAGE_FAILED",
        "AGENT_TURN_STARTED",
        "AGENT_TURN_COMPLETED",
        "AGENT_LLM_REQUEST",
        "AGENT_LLM_RESPONSE",
        "AGENT_TOOL_CALL",
        "AGENT_TOOL_RESULT",
        "AGENT_DIALOGUE",
        "PI_DECISION",
        "HYPOTHESIS_UPDATE",
        "CHECKPOINT_REACHED",
        "COST_UPDATE",
        "ERROR",
    ):
        assert hasattr(EventTypes, name), f"missing {name}"


def test_deprecated_event_type_removed():
    from agentlabx.server.events import EventTypes

    assert not hasattr(EventTypes, "AGENT_THINKING"), "legacy name must be removed"
