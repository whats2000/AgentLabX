from __future__ import annotations

from agentlabx.llm.protocol import LLMRequest, LLMResponse, MessageRole


def test_llm_request_construction() -> None:
    req = LLMRequest(
        model="test-provider/test-model",
        messages=[
            {"role": MessageRole.SYSTEM, "content": "You are helpful."},
            {"role": MessageRole.USER, "content": "Hello"},
        ],
        temperature=0.7,
        max_tokens=1024,
    )
    assert req.model == "test-provider/test-model"
    assert len(req.messages) == 2
    assert req.temperature == 0.7
    assert req.max_tokens == 1024


def test_llm_request_defaults() -> None:
    req = LLMRequest(
        model="test-provider/default-model",
        messages=[{"role": MessageRole.USER, "content": "Hi"}],
    )
    assert req.temperature is None
    assert req.max_tokens is None
    assert req.system_prompt is None


def test_llm_response_construction() -> None:
    resp = LLMResponse(
        content="Hello there!",
        model="test-provider/test-model",
        prompt_tokens=10,
        completion_tokens=5,
        total_tokens=15,
        cost_usd=0.0003,
    )
    assert resp.content == "Hello there!"
    assert resp.prompt_tokens == 10
    assert resp.completion_tokens == 5
    assert resp.total_tokens == 15
    assert resp.cost_usd == 0.0003


def test_llm_response_zero_cost_allowed() -> None:
    resp = LLMResponse(
        content="ok",
        model="local-model",
        prompt_tokens=0,
        completion_tokens=0,
        total_tokens=0,
        cost_usd=0.0,
    )
    assert resp.cost_usd == 0.0


def test_message_role_values() -> None:
    assert MessageRole.SYSTEM == "system"
    assert MessageRole.USER == "user"
    assert MessageRole.ASSISTANT == "assistant"
