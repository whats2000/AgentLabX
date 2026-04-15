import pytest
from unittest.mock import AsyncMock, MagicMock
from agentlabx.core.turn_context import TurnContext, push_turn
from agentlabx.tools.traced import TracedTool


class _FakeResult:
    def __init__(self, success=True, data=None, error=None):
        self.success, self.data, self.error = success, data, error


@pytest.fixture
def inner():
    t = MagicMock()
    t.name = "arxiv_search"
    t.execute = AsyncMock(return_value=_FakeResult(success=True, data={"hits": 3}))
    return t


@pytest.mark.asyncio
async def test_traced_tool_emits_call_and_result(inner):
    emitted = []
    bus = MagicMock(); bus.emit = AsyncMock(side_effect=lambda e: emitted.append(e))
    storage = MagicMock(); storage.append_agent_turn = AsyncMock(return_value=1)
    tt = TracedTool(inner=inner, event_bus=bus, storage=storage)

    ctx = TurnContext(turn_id="T1", agent="phd", stage="lit", is_mock=False, session_id="s")
    with push_turn(ctx):
        r = await tt.execute(query="LLM")
    assert r.success
    assert [e.type for e in emitted] == ["agent_tool_call", "agent_tool_result"]
    assert ctx.tool_call_count == 1
    assert storage.append_agent_turn.await_count == 2


@pytest.mark.asyncio
async def test_traced_tool_emits_events_without_turn_context(inner):
    """Stage-level tool calls (no TurnContext) must still emit agent_tool_call events
    so the harness can observe tool usage even outside agent inference."""
    from agentlabx.core.events import EventBus, Event

    bus = EventBus()
    captured: list[Event] = []

    async def grab(event: Event):
        captured.append(event)

    bus.subscribe("agent_tool_call", grab)
    bus.subscribe("agent_tool_result", grab)

    storage = MagicMock()
    storage.append_agent_turn = AsyncMock()

    tt = TracedTool(inner=inner, event_bus=bus, storage=storage)

    # No TurnContext pushed — simulates a stage calling a tool directly
    result = await tt.execute(query="super resolution")

    call_events = [e for e in captured if e.type == "agent_tool_call"]
    result_events = [e for e in captured if e.type == "agent_tool_result"]
    assert len(call_events) == 1
    assert len(result_events) == 1
    assert call_events[0].data["tool"] == "arxiv_search"
    assert result_events[0].data["tool"] == "arxiv_search"
    assert result_events[0].data["success"] is True
    # stage and turn_id are None for context-free calls
    assert call_events[0].data["stage"] is None
    assert call_events[0].data["turn_id"] is None
    # source is "stage" sentinel when no agent is attributed
    assert call_events[0].source == "stage"
    # Storage must NOT be called when no session context
    storage.append_agent_turn.assert_not_called()


@pytest.mark.asyncio
async def test_traced_tool_delegates_attribute_access(inner):
    """Attributes like name, description passthrough to inner tool."""
    tt = TracedTool(inner=inner, event_bus=MagicMock(), storage=MagicMock())
    assert tt.name == "arxiv_search"


@pytest.mark.asyncio
async def test_traced_tool_records_error_on_failure(inner):
    inner.execute = AsyncMock(return_value=_FakeResult(success=False, data=None, error="rate limited"))
    emitted = []
    bus = MagicMock(); bus.emit = AsyncMock(side_effect=lambda e: emitted.append(e))
    storage = MagicMock(); storage.append_agent_turn = AsyncMock(return_value=1)
    tt = TracedTool(inner=inner, event_bus=bus, storage=storage)

    ctx = TurnContext(turn_id="T1", agent="a", stage="s", is_mock=False, session_id="sess")
    with push_turn(ctx):
        r = await tt.execute(query="x")
    assert not r.success
    result_event = emitted[-1]
    assert result_event.type == "agent_tool_result"
    assert result_event.data["success"] is False
    assert result_event.data["error"] == "rate limited"
