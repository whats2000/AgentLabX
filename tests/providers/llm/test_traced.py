# tests/providers/llm/test_traced.py
import pytest
from unittest.mock import AsyncMock, MagicMock
from agentlabx.core.turn_context import TurnContext, push_turn
from agentlabx.providers.llm.traced import TracedLLMProvider
from agentlabx.providers.llm.base import LLMResponse


@pytest.fixture
def inner():
    p = MagicMock()
    p.is_mock = False
    p.name = "litellm"
    p.query = AsyncMock(return_value=LLMResponse(
        content="hi", tokens_in=5, tokens_out=3, model="m", cost=0.01))
    return p


@pytest.mark.asyncio
async def test_traced_provider_emits_events_around_query(inner):
    emitted = []
    bus = MagicMock()
    bus.emit = AsyncMock(side_effect=lambda ev: emitted.append(ev))
    storage = MagicMock()
    storage.append_agent_turn = AsyncMock(return_value=1)

    t = TracedLLMProvider(inner=inner, event_bus=bus, storage=storage)

    ctx = TurnContext(turn_id="T1", agent="phd", stage="lit", is_mock=False, session_id="s1")
    with push_turn(ctx):
        resp = await t.query(model="m", prompt="p", system_prompt="sp", temperature=0.2)
    assert resp.content == "hi"
    types = [e.type for e in emitted]
    assert types == ["agent_llm_request", "agent_llm_response"]
    assert ctx.tokens_in == 5 and ctx.tokens_out == 3
    assert storage.append_agent_turn.await_count == 2


@pytest.mark.asyncio
async def test_traced_provider_bypasses_when_no_turn(inner):
    """If there is no current_turn, the wrapper passes through without tracing."""
    bus = MagicMock(); bus.emit = AsyncMock()
    storage = MagicMock(); storage.append_agent_turn = AsyncMock()
    t = TracedLLMProvider(inner=inner, event_bus=bus, storage=storage)
    await t.query(model="m", prompt="p")
    bus.emit.assert_not_called()
    storage.append_agent_turn.assert_not_called()


@pytest.mark.asyncio
async def test_traced_provider_accumulates_on_turn_context(inner):
    bus = MagicMock(); bus.emit = AsyncMock()
    storage = MagicMock(); storage.append_agent_turn = AsyncMock(return_value=1)
    t = TracedLLMProvider(inner=inner, event_bus=bus, storage=storage)

    ctx = TurnContext(turn_id="T", agent="a", stage="s", is_mock=False, session_id="sess")
    with push_turn(ctx):
        await t.query(model="m", prompt="p1")
        await t.query(model="m", prompt="p2")

    # Two queries, each with tokens_in=5 tokens_out=3 cost=0.01 — accumulate
    assert ctx.tokens_in == 10
    assert ctx.tokens_out == 6
    assert abs(ctx.cost_usd - 0.02) < 1e-9
