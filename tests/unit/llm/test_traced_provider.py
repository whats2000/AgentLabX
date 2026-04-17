from __future__ import annotations

import pytest

from agentlabx.events.bus import Event, EventBus
from agentlabx.llm.budget import BudgetTracker
from agentlabx.llm.protocol import BudgetExceededError, LLMRequest, LLMResponse, MessageRole
from agentlabx.llm.traced_provider import TracedLLMProvider

# --- Inline test stub (not shipped in production) ---


class _StubProvider:
    """Minimal in-test stub satisfying BaseLLMProvider for TracedLLMProvider tests."""

    def __init__(
        self,
        *,
        content: str = "stub response",
        prompt_tokens: int = 0,
        completion_tokens: int = 0,
    ) -> None:
        self._content = content
        self._prompt_tokens = prompt_tokens
        self._completion_tokens = completion_tokens
        self.call_count: int = 0

    async def complete(self, request: LLMRequest) -> LLMResponse:
        self.call_count += 1
        return LLMResponse(
            content=self._content,
            model=request.model,
            prompt_tokens=self._prompt_tokens,
            completion_tokens=self._completion_tokens,
            total_tokens=self._prompt_tokens + self._completion_tokens,
            cost_usd=0.0,
        )


# --- Helpers ---


async def _collect_events(bus: EventBus, kind: str) -> list[Event]:
    collected: list[Event] = []

    async def handler(event: Event) -> None:
        collected.append(event)

    bus.subscribe(kind, handler)
    return collected


# --- Tests ---


@pytest.mark.asyncio
async def test_traced_emits_llm_called_event() -> None:
    bus = EventBus()
    events = await _collect_events(bus, "llm.called")
    inner = _StubProvider(content="traced response", prompt_tokens=100, completion_tokens=50)
    traced = TracedLLMProvider(inner=inner, bus=bus)
    req = LLMRequest(
        model="test-provider/test-model",
        messages=[{"role": MessageRole.USER, "content": "Hello world"}],
    )
    resp = await traced.complete(req)

    assert resp.content == "traced response"
    assert len(events) == 1
    evt = events[0]
    assert evt.kind == "llm.called"
    assert evt.payload["model"] == "test-provider/test-model"
    assert evt.payload["prompt_tokens"] == 100
    assert evt.payload["completion_tokens"] == 50
    assert evt.payload["total_tokens"] == 150
    assert evt.payload["cost_usd"] == 0.0


@pytest.mark.asyncio
async def test_traced_redacts_prompt_preview() -> None:
    bus = EventBus()
    events = await _collect_events(bus, "llm.called")
    inner = _StubProvider()
    traced = TracedLLMProvider(inner=inner, bus=bus, prompt_preview_length=10)
    long_message = "A" * 100
    req = LLMRequest(
        model="m",
        messages=[{"role": MessageRole.USER, "content": long_message}],
    )
    await traced.complete(req)

    assert len(events) == 1
    preview = events[0].payload["prompt_preview"]
    assert isinstance(preview, str)
    assert len(preview) <= 13  # 10 chars + "..."
    assert preview.endswith("...")


@pytest.mark.asyncio
async def test_traced_short_prompt_not_truncated() -> None:
    bus = EventBus()
    events = await _collect_events(bus, "llm.called")
    inner = _StubProvider()
    traced = TracedLLMProvider(inner=inner, bus=bus, prompt_preview_length=100)
    req = LLMRequest(
        model="m",
        messages=[{"role": MessageRole.USER, "content": "short"}],
    )
    await traced.complete(req)

    assert events[0].payload["prompt_preview"] == "short"


@pytest.mark.asyncio
async def test_traced_with_budget_records_cost() -> None:
    bus = EventBus()
    budget = BudgetTracker(cap_usd=10.0)
    inner = _StubProvider(prompt_tokens=10, completion_tokens=5)
    traced = TracedLLMProvider(inner=inner, bus=bus, budget=budget)
    req = LLMRequest(
        model="m",
        messages=[{"role": MessageRole.USER, "content": "hi"}],
    )
    await traced.complete(req)
    assert budget.call_count == 1


@pytest.mark.asyncio
async def test_traced_with_budget_raises_before_call() -> None:
    bus = EventBus()
    budget = BudgetTracker(cap_usd=1.0)
    budget.record(cost_usd=2.0)  # already over budget
    inner = _StubProvider()
    traced = TracedLLMProvider(inner=inner, bus=bus, budget=budget)
    req = LLMRequest(
        model="m",
        messages=[{"role": MessageRole.USER, "content": "hi"}],
    )
    with pytest.raises(BudgetExceededError):
        await traced.complete(req)
    assert inner.call_count == 0  # inner was never called


@pytest.mark.asyncio
async def test_traced_emits_error_event_on_failure() -> None:
    bus = EventBus()
    events = await _collect_events(bus, "llm.error")

    class _FailingProvider:
        async def complete(self, request: LLMRequest) -> LLMResponse:
            raise RuntimeError("LLM exploded")

    traced = TracedLLMProvider(inner=_FailingProvider(), bus=bus)  # type: ignore[arg-type]
    req = LLMRequest(
        model="m",
        messages=[{"role": MessageRole.USER, "content": "hi"}],
    )
    with pytest.raises(RuntimeError, match="LLM exploded"):
        await traced.complete(req)

    assert len(events) == 1
    assert events[0].payload["error"] == "LLM exploded"
    assert events[0].payload["model"] == "m"


@pytest.mark.asyncio
async def test_traced_passes_through_response_unchanged() -> None:
    bus = EventBus()
    inner = _StubProvider(content="exact content", prompt_tokens=42, completion_tokens=17)
    traced = TracedLLMProvider(inner=inner, bus=bus)
    req = LLMRequest(
        model="test-model",
        messages=[{"role": MessageRole.USER, "content": "hi"}],
    )
    resp = await traced.complete(req)
    assert resp.content == "exact content"
    assert resp.prompt_tokens == 42
    assert resp.completion_tokens == 17
    assert resp.total_tokens == 59
    assert resp.model == "test-model"
