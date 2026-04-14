"""Capture serialized LLM prompts from the event bus into a HarnessTrace.

Subscribes to the `agent_llm_request` event (emitted by TracedLLMProvider via the
shared event bus). The event is received via HarnessSession._on_bus_event as:

{
    "type": "agent_llm_request",
    "source": "<agent_name>",
    "data": {
        "model": "...",
        "prompt": "...",
        "system_prompt": "...",
        "temperature": 0.0,
        "is_mock": bool,
        "turn_id": "...",
        "parent_turn_id": "...",
    },
    "timestamp": "...",
}

Note: The real event is missing "messages", "tools", "node", "stage" fields
(architectural limitations noted in reality check / Plan 8 T4).
"""
from __future__ import annotations

from typing import Any

from tests.harness.contracts.base import HarnessTrace


def capture_llm_event(event: dict[str, Any], trace: HarnessTrace) -> None:
    """Map a single bus event to a trace prompt record if it's an LLM request.

    Extracts available fields from the real event structure. Missing fields
    ("messages", "tools", "node", "stage") are filled with defaults.
    """
    if event.get("type") != "agent_llm_request":
        return

    data = event.get("data", {})
    trace.record_prompt(
        node=event.get("node", ""),  # Not available in real event
        stage=event.get("stage", ""),  # Not available in real event
        agent=event.get("source", ""),  # Real event uses "source" for agent name
        messages=event.get("messages", []),  # Not available in real event
        system=data.get("system_prompt"),
        tools=event.get("tools", []),  # Not available in real event
    )
