"""Plan 8 T9b — agent_llm_request event carries stage (and node if available)
from the active TurnContext so harness contracts can filter prompts by stage/node."""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from agentlabx.core.turn_context import TurnContext, push_turn
from agentlabx.core.events import EventBus, Event
from agentlabx.providers.llm.traced import TracedLLMProvider
from agentlabx.providers.llm.base import LLMResponse


@pytest.fixture
def mock_inner():
    inner = MagicMock()
    inner.is_mock = False
    inner.name = "test"
    inner.query = AsyncMock(return_value=LLMResponse(
        content="hi", model="gemini/test", tokens_in=1, tokens_out=1, cost=0.0,
    ))
    return inner


@pytest.mark.asyncio
async def test_agent_llm_request_event_includes_stage(mock_inner):
    bus = EventBus()
    captured: list[Event] = []

    async def grab(event: Event) -> None:
        captured.append(event)

    bus.subscribe("agent_llm_request", grab)

    storage = MagicMock()
    storage.append_agent_turn = AsyncMock()
    traced = TracedLLMProvider(inner=mock_inner, event_bus=bus, storage=storage)

    ctx = TurnContext(
        turn_id="t-1",
        agent="phd_student",
        stage="literature_review",
        is_mock=False,
        parent_turn_id=None,
    )
    with push_turn(ctx):
        await traced.query(model="gemini/test", prompt="hi")

    assert len(captured) == 1
    event = captured[0]
    assert event.data.get("stage") == "literature_review", f"event.data={event.data}"


@pytest.mark.asyncio
async def test_agent_llm_response_event_includes_stage(mock_inner):
    """agent_llm_response should also carry stage for symmetric correlation."""
    bus = EventBus()
    captured: list[Event] = []

    async def grab(event: Event) -> None:
        captured.append(event)

    bus.subscribe("agent_llm_response", grab)

    storage = MagicMock()
    storage.append_agent_turn = AsyncMock()
    traced = TracedLLMProvider(inner=mock_inner, event_bus=bus, storage=storage)

    ctx = TurnContext(
        turn_id="t-2",
        agent="phd_student",
        stage="data_collection",
        is_mock=False,
        parent_turn_id=None,
    )
    with push_turn(ctx):
        await traced.query(model="gemini/test", prompt="hi")

    assert len(captured) == 1
    event = captured[0]
    assert event.data.get("stage") == "data_collection", f"event.data={event.data}"


@pytest.mark.asyncio
async def test_agent_llm_request_event_has_no_stage_without_turn_context(mock_inner):
    """When no TurnContext is active, query short-circuits — no event emitted at all.
    This is the existing bypass behaviour (not a regression)."""
    bus = EventBus()
    captured: list[Event] = []

    async def grab(event: Event) -> None:
        captured.append(event)

    bus.subscribe("agent_llm_request", grab)
    storage = MagicMock()
    storage.append_agent_turn = AsyncMock()
    traced = TracedLLMProvider(inner=mock_inner, event_bus=bus, storage=storage)

    # No TurnContext pushed — TracedLLMProvider bypasses events entirely
    await traced.query(model="gemini/test", prompt="hi")

    # No event emitted when there's no active turn (existing bypass behaviour)
    assert len(captured) == 0
