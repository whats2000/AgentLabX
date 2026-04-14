"""Subgraph nodes emit stage_internal_node_changed events + update outer state."""
from __future__ import annotations

import pytest

from agentlabx.core.event_types import EventTypes
from agentlabx.core.events import Event, EventBus
from agentlabx.core.state import create_initial_state
from agentlabx.stages.base import BaseStage, StageContext, StageResult
from agentlabx.stages.subgraph import StageSubgraphBuilder


class _EchoStage(BaseStage):
    name = "echo"
    description = "echo"
    required_agents: list[str] = []
    required_tools: list[str] = []
    zone = "discovery"

    async def run(self, state, context):
        return StageResult(output={}, status="done", reason="ok")


@pytest.mark.asyncio
async def test_subgraph_emits_internal_node_changed_events():
    events: list[Event] = []
    bus = EventBus()

    async def collector(e: Event) -> None:
        events.append(e)

    bus.subscribe("*", collector)

    compiled = StageSubgraphBuilder().compile(_EchoStage())
    state = create_initial_state(session_id="s1", user_id="u1", research_topic="t")
    state["current_stage"] = "echo"

    await compiled.ainvoke(
        {
            "state": state,
            "context": StageContext(settings={}, event_bus=bus, registry=None),
        },
        config={"configurable": {"thread_id": "t1"}},
    )

    internal_events = [
        e for e in events if e.type == EventTypes.STAGE_INTERNAL_NODE_CHANGED
    ]
    internal_nodes = [e.data["internal_node"] for e in internal_events]
    # All 5 subgraph nodes emit an event (enter, stage_plan, work, evaluate, decide).
    # Bypass path skips work+evaluate, but echo stage produces todo → work runs.
    for required in ("enter", "stage_plan", "work", "evaluate", "decide"):
        assert required in internal_nodes, (
            f"Expected {required!r} event; got: {internal_nodes}"
        )


@pytest.mark.asyncio
async def test_subgraph_nodes_return_current_internal_node_in_update():
    """Node return dicts propagate current_stage_internal_node through the
    subgraph channel (both in-place state mutation and the typed return dict
    write to the same field; final value is 'decide' at subgraph exit)."""
    compiled = StageSubgraphBuilder().compile(_EchoStage())
    state = create_initial_state(session_id="s1", user_id="u1", research_topic="t")
    state["current_stage"] = "echo"

    result = await compiled.ainvoke(
        {
            "state": state,
            "context": StageContext(settings={}, event_bus=None, registry=None),
        },
        config={"configurable": {"thread_id": "t1"}},
    )

    # After the subgraph exits, state's current_stage_internal_node reflects
    # the last node to write — which is "decide".
    assert result["state"]["current_stage_internal_node"] == "decide"


@pytest.mark.asyncio
async def test_subgraph_emits_event_data_includes_stage_and_session():
    """Event data carries enough context for frontend invalidation."""
    events: list[Event] = []
    bus = EventBus()

    async def collector(e: Event) -> None:
        events.append(e)

    bus.subscribe("*", collector)

    compiled = StageSubgraphBuilder().compile(_EchoStage())
    state = create_initial_state(
        session_id="sess-42", user_id="u1", research_topic="t"
    )
    state["current_stage"] = "echo"

    await compiled.ainvoke(
        {
            "state": state,
            "context": StageContext(settings={}, event_bus=bus, registry=None),
        },
        config={"configurable": {"thread_id": "t1"}},
    )

    internal_events = [
        e for e in events if e.type == EventTypes.STAGE_INTERNAL_NODE_CHANGED
    ]
    for e in internal_events:
        assert e.data.get("session_id") == "sess-42"
        assert e.data.get("stage") == "echo"
        assert e.data.get("internal_node") in {
            "enter", "stage_plan", "work", "evaluate", "decide"
        }
