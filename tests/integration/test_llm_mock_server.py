"""Integration tests: LiteLLMProvider → LiteLLM → HTTP → mock LLM server."""

from __future__ import annotations

import pytest

from agentlabx.events.bus import Event, EventBus
from agentlabx.llm.litellm_provider import LiteLLMProvider
from agentlabx.llm.protocol import LLMRequest, LLMResponse, MessageRole
from agentlabx.llm.traced_provider import TracedLLMProvider
from tests.conftest import MockLLMService

pytestmark = pytest.mark.integration


@pytest.mark.asyncio
async def test_litellm_provider_against_mock_server(
    mock_llm_server: MockLLMService,
) -> None:
    provider = LiteLLMProvider(
        api_key="mock-key",
        api_base=mock_llm_server.base_url,
    )
    req = LLMRequest(
        model="openai/mock-model",
        messages=[{"role": MessageRole.USER, "content": "Hello mock"}],
    )
    resp = await provider.complete(req)

    assert isinstance(resp, LLMResponse)
    assert resp.content == "This is a mock response."
    assert resp.prompt_tokens > 0
    assert resp.completion_tokens > 0
    assert resp.total_tokens == resp.prompt_tokens + resp.completion_tokens


@pytest.mark.asyncio
async def test_mock_server_deterministic(
    mock_llm_server: MockLLMService,
) -> None:
    provider = LiteLLMProvider(
        api_key="mock-key",
        api_base=mock_llm_server.base_url,
    )
    req = LLMRequest(
        model="openai/mock-model",
        messages=[{"role": MessageRole.USER, "content": "determinism check"}],
    )
    r1 = await provider.complete(req)
    r2 = await provider.complete(req)

    assert r1.content == r2.content
    assert r1.prompt_tokens == r2.prompt_tokens
    assert r1.completion_tokens == r2.completion_tokens


@pytest.mark.asyncio
async def test_mock_server_custom_response(
    mock_llm_server: MockLLMService,
) -> None:
    mock_llm_server.state.response_map["special input"] = "special output"
    provider = LiteLLMProvider(
        api_key="mock-key",
        api_base=mock_llm_server.base_url,
    )
    req = LLMRequest(
        model="openai/mock-model",
        messages=[{"role": MessageRole.USER, "content": "special input"}],
    )
    resp = await provider.complete(req)
    assert resp.content == "special output"


@pytest.mark.asyncio
async def test_traced_provider_with_mock_server(
    mock_llm_server: MockLLMService,
) -> None:
    bus = EventBus()
    events: list[Event] = []

    async def collect(event: Event) -> None:
        events.append(event)

    bus.subscribe("llm.called", collect)

    inner = LiteLLMProvider(
        api_key="mock-key",
        api_base=mock_llm_server.base_url,
    )
    traced = TracedLLMProvider(inner=inner, bus=bus)
    req = LLMRequest(
        model="openai/mock-model",
        messages=[{"role": MessageRole.USER, "content": "traced mock call"}],
    )
    resp = await traced.complete(req)

    assert resp.content == "This is a mock response."
    assert len(events) == 1
    evt = events[0]
    assert int(evt.payload["prompt_tokens"]) > 0  # type: ignore[arg-type]
    assert int(evt.payload["completion_tokens"]) > 0  # type: ignore[arg-type]
    assert evt.payload["prompt_preview"] == "traced mock call"


@pytest.mark.asyncio
async def test_mock_server_records_history(
    mock_llm_server: MockLLMService,
) -> None:
    provider = LiteLLMProvider(
        api_key="mock-key",
        api_base=mock_llm_server.base_url,
    )
    req = LLMRequest(
        model="openai/mock-model",
        messages=[{"role": MessageRole.USER, "content": "track this"}],
    )
    await provider.complete(req)
    await provider.complete(req)

    assert len(mock_llm_server.state.history) == 2
    assert mock_llm_server.state.history[0].messages[-1].content == "track this"


@pytest.mark.asyncio
async def test_litellm_retries_on_429(
    mock_llm_server: MockLLMService,
) -> None:
    mock_llm_server.state.fail_next_n = 1
    provider = LiteLLMProvider(
        api_key="mock-key",
        api_base=mock_llm_server.base_url,
        retry_count=2,
    )
    req = LLMRequest(
        model="openai/mock-model",
        messages=[{"role": MessageRole.USER, "content": "retry me"}],
    )
    resp = await provider.complete(req)
    assert resp.content == "This is a mock response."


@pytest.mark.asyncio
async def test_litellm_provider_with_system_prompt(
    mock_llm_server: MockLLMService,
) -> None:
    provider = LiteLLMProvider(
        api_key="mock-key",
        api_base=mock_llm_server.base_url,
    )
    req = LLMRequest(
        model="openai/mock-model",
        messages=[{"role": MessageRole.USER, "content": "hello"}],
        system_prompt="You are a test assistant.",
    )
    resp = await provider.complete(req)
    assert isinstance(resp, LLMResponse)
    last_req = mock_llm_server.state.history[-1]
    assert last_req.messages[0].role == "system"
    assert last_req.messages[0].content == "You are a test assistant."


@pytest.mark.asyncio
async def test_litellm_provider_with_message_dataclass(
    mock_llm_server: MockLLMService,
) -> None:
    from agentlabx.llm.protocol import Message

    provider = LiteLLMProvider(
        api_key="mock-key",
        api_base=mock_llm_server.base_url,
    )
    req = LLMRequest(
        model="openai/mock-model",
        messages=[Message(role=MessageRole.USER, content="dataclass msg")],
    )
    resp = await provider.complete(req)
    assert resp.content == "This is a mock response."
    last_req = mock_llm_server.state.history[-1]
    assert last_req.messages[-1].content == "dataclass msg"
