"""Tests for MockLLMProvider."""

from __future__ import annotations

from agentlabx.providers.llm.mock_provider import MockLLMProvider


class TestMockLLMProvider:
    async def test_scripted_responses(self):
        provider = MockLLMProvider(responses=["response 1", "response 2"])
        r1 = await provider.query(model="mock", prompt="hello")
        assert r1.content == "response 1"
        r2 = await provider.query(model="mock", prompt="hi again")
        assert r2.content == "response 2"

    async def test_token_tracking(self):
        provider = MockLLMProvider(responses=["test response"])
        r = await provider.query(model="mock", prompt="test prompt")
        assert r.tokens_in > 0
        assert r.tokens_out > 0
        assert r.cost == 0.0

    async def test_default_response_when_empty(self):
        provider = MockLLMProvider(responses=[])
        r = await provider.query(model="mock", prompt="anything")
        assert "mock" in r.content.lower()

    async def test_records_calls(self):
        provider = MockLLMProvider(responses=["a", "b"])
        await provider.query(model="mock", prompt="first")
        await provider.query(model="mock", prompt="second")
        assert len(provider.calls) == 2
        assert provider.calls[0]["prompt"] == "first"

    async def test_artificial_delay_invokes_sleep(self, monkeypatch):
        seen: list[float] = []

        async def _fake_sleep(seconds: float):
            seen.append(seconds)

        monkeypatch.setattr(
            "agentlabx.providers.llm.mock_provider.asyncio.sleep",
            _fake_sleep,
        )

        provider = MockLLMProvider(responses=["ok"], artificial_delay_seconds=1.0)
        await provider.query(model="mock", prompt="first")

        assert seen == [1.0]
