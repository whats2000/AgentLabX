"""Tests for LiteLLMProvider.

These tests use mocking since real API calls require keys. One integration test
is marked with @pytest.mark.skipif and skipped unless ANTHROPIC_API_KEY is set.
"""

from __future__ import annotations

import os
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from agentlabx.providers.llm.litellm_provider import LiteLLMProvider


class TestLiteLLMProvider:
    async def test_query_calls_acompletion(self):
        provider = LiteLLMProvider()
        mock_response = MagicMock()
        mock_response.choices = [MagicMock(message=MagicMock(content="Hello"))]
        mock_response.usage.prompt_tokens = 10
        mock_response.usage.completion_tokens = 5
        mock_response.model = "anthropic/claude-sonnet-4-6"

        with patch(
            "agentlabx.providers.llm.litellm_provider.acompletion",
            new_callable=AsyncMock,
            return_value=mock_response,
        ):
            with patch(
                "agentlabx.providers.llm.litellm_provider.completion_cost",
                return_value=0.0025,
            ):
                response = await provider.query(
                    model="anthropic/claude-sonnet-4-6",
                    prompt="Hello world",
                )
        assert response.content == "Hello"
        assert response.tokens_in == 10
        assert response.tokens_out == 5
        assert response.cost == 0.0025

    async def test_query_includes_system_prompt(self):
        provider = LiteLLMProvider()
        mock_response = MagicMock()
        mock_response.choices = [MagicMock(message=MagicMock(content="response"))]
        mock_response.usage.prompt_tokens = 1
        mock_response.usage.completion_tokens = 1
        mock_response.model = "test"

        acompletion_mock = AsyncMock(return_value=mock_response)
        with patch("agentlabx.providers.llm.litellm_provider.acompletion", acompletion_mock):
            with patch(
                "agentlabx.providers.llm.litellm_provider.completion_cost",
                return_value=0.0,
            ):
                await provider.query(
                    model="test",
                    prompt="user msg",
                    system_prompt="you are a helper",
                )
        call_kwargs = acompletion_mock.call_args.kwargs
        messages = call_kwargs["messages"]
        assert messages[0] == {"role": "system", "content": "you are a helper"}
        assert messages[1] == {"role": "user", "content": "user msg"}

    async def test_retry_on_rate_limit(self):
        from litellm import RateLimitError

        provider = LiteLLMProvider(max_retries=2, retry_delay=0.01)
        mock_response = MagicMock()
        mock_response.choices = [MagicMock(message=MagicMock(content="ok"))]
        mock_response.usage.prompt_tokens = 1
        mock_response.usage.completion_tokens = 1
        mock_response.model = "test"

        call_count = {"n": 0}

        async def flaky_acompletion(**kwargs):
            call_count["n"] += 1
            if call_count["n"] < 2:
                raise RateLimitError("rate limited", llm_provider="test", model="test")
            return mock_response

        with patch("agentlabx.providers.llm.litellm_provider.acompletion", flaky_acompletion):
            with patch(
                "agentlabx.providers.llm.litellm_provider.completion_cost",
                return_value=0.0,
            ):
                response = await provider.query(model="test", prompt="hi")
        assert response.content == "ok"
        assert call_count["n"] == 2

    @pytest.mark.skipif(
        not os.getenv("GEMINI_API_KEY"),
        reason="GEMINI_API_KEY not set",
    )
    async def test_real_api_call(self):
        provider = LiteLLMProvider()
        response = await provider.query(
            model="gemini/gemini-3.1-flash-lite-preview",
            prompt="Say 'hello' in one word.",
            temperature=0.0,
        )
        assert len(response.content) > 0
        assert response.tokens_in > 0
