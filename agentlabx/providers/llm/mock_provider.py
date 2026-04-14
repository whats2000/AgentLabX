"""Mock LLM provider for testing — returns scripted responses."""

from __future__ import annotations

import asyncio
from collections import deque
from typing import Any

from agentlabx.providers.llm.base import BaseLLMProvider, LLMResponse


class MockLLMProvider(BaseLLMProvider):
    """Returns scripted responses in order. Tracks call history for assertions."""

    name = "mock"
    description = (
        "Scripted responses for tests and --mock-llm local dev. "
        "Zero cost, zero network — returns canned strings in call order."
    )
    is_mock: bool = True

    def __init__(
        self,
        responses: list[str] | None = None,
        artificial_delay_seconds: float = 0.0,
    ) -> None:
        self._responses: deque[str] = deque(responses or [])
        self._artificial_delay_seconds = max(0.0, float(artificial_delay_seconds))
        self.calls: list[dict[str, Any]] = []

    async def query(
        self,
        *,
        model: str,
        prompt: str,
        system_prompt: str = "",
        temperature: float = 0.0,
    ) -> LLMResponse:
        self.calls.append(
            {
                "model": model,
                "prompt": prompt,
                "system_prompt": system_prompt,
                "temperature": temperature,
            }
        )

        if self._artificial_delay_seconds > 0:
            await asyncio.sleep(self._artificial_delay_seconds)

        if self._responses:
            content = self._responses.popleft()
        else:
            content = f"[mock] response to: {prompt[:50]}"

        return LLMResponse(
            content=content,
            tokens_in=max(1, len(prompt) // 4),
            tokens_out=max(1, len(content) // 4),
            model=model,
            cost=0.0,
        )
