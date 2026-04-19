"""Real-LLM integration test for Stage A2 verification gate.

Requires TEST_LLM_MODEL + a matching provider API key in the environment.
See .env.example for setup instructions. pytest-dotenv auto-loads .env.

Skip with: pytest -m "not real_llm"
Run only: pytest -m real_llm
"""

from __future__ import annotations

import os

import pytest

from agentlabx.events.bus import Event, EventBus
from agentlabx.llm.budget import BudgetTracker
from agentlabx.llm.litellm_provider import LiteLLMProvider
from agentlabx.llm.protocol import BudgetExceededError, LLMRequest, LLMResponse, MessageRole
from agentlabx.llm.traced_provider import TracedLLMProvider

# Read from env — pytest-dotenv loads .env automatically.
_MODEL = os.environ.get("TEST_LLM_MODEL", "")

_skip = pytest.mark.skipif(
    not _MODEL,
    reason="TEST_LLM_MODEL not set — see .env.example",
)

pytestmark = [pytest.mark.real_llm, pytest.mark.integration]


@_skip
@pytest.mark.asyncio
async def test_real_llm_call_succeeds() -> None:
    """A2 verification: real call succeeds and returns valid LLMResponse."""
    provider = LiteLLMProvider()
    req = LLMRequest(
        model=_MODEL,
        messages=[{"role": MessageRole.USER, "content": "Reply with exactly: hello"}],
        max_tokens=50,
        temperature=0.0,
    )
    resp = await provider.complete(req)
    assert isinstance(resp, LLMResponse)
    assert len(resp.content) > 0
    assert resp.prompt_tokens > 0
    assert resp.completion_tokens > 0
    assert resp.total_tokens > 0


@_skip
@pytest.mark.asyncio
async def test_real_llm_emits_event_with_cost() -> None:
    """A2 verification: TracedLLMProvider emits LLMCalled with tokens + cost."""
    bus = EventBus()
    events: list[Event] = []

    async def collect(event: Event) -> None:
        events.append(event)

    bus.subscribe("llm.called", collect)

    inner = LiteLLMProvider()
    traced = TracedLLMProvider(inner=inner, bus=bus)
    req = LLMRequest(
        model=_MODEL,
        messages=[{"role": MessageRole.USER, "content": "Say hi"}],
        max_tokens=20,
        temperature=0.0,
    )
    await traced.complete(req)

    assert len(events) == 1
    evt = events[0]
    assert evt.kind == "llm.called"
    prompt_tokens = evt.payload["prompt_tokens"]
    completion_tokens = evt.payload["completion_tokens"]
    total_tokens = evt.payload["total_tokens"]
    cost_usd = evt.payload["cost_usd"]
    assert isinstance(prompt_tokens, int) and prompt_tokens > 0
    assert isinstance(completion_tokens, int) and completion_tokens > 0
    assert isinstance(total_tokens, int) and total_tokens > 0
    # Cost should be a non-negative number (may be 0 for some providers)
    assert isinstance(cost_usd, float)
    assert cost_usd >= 0.0


@_skip
@pytest.mark.asyncio
async def test_real_llm_budget_cap_halts() -> None:
    """A2 verification: budget cap prevents call when exceeded."""
    bus = EventBus()
    budget = BudgetTracker(cap_usd=0.0001)

    inner = LiteLLMProvider()
    traced = TracedLLMProvider(inner=inner, bus=bus, budget=budget)

    # First call should succeed (budget starts at 0)
    req = LLMRequest(
        model=_MODEL,
        messages=[{"role": MessageRole.USER, "content": "Hi"}],
        max_tokens=5,
        temperature=0.0,
    )
    resp1 = await traced.complete(req)
    assert resp1.content

    # Force budget over the cap (some providers report cost=0 for cheap calls)
    if budget.spent_usd <= 0.0001:
        budget.record(cost_usd=1.0)

    with pytest.raises(BudgetExceededError):
        await traced.complete(req)
