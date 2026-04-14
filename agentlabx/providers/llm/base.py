"""Base LLM provider contract."""

from __future__ import annotations

from abc import ABC, abstractmethod

from pydantic import BaseModel


class LLMResponse(BaseModel):
    content: str
    tokens_in: int
    tokens_out: int
    model: str | None = None
    cost: float


class BaseLLMProvider(ABC):
    # Plugin metadata — subclasses override. Surfaced by /api/plugins.
    name: str = "llm_provider"
    description: str = ""
    is_mock: bool = False

    @abstractmethod
    async def query(
        self, *, model: str | None, prompt: str, system_prompt: str = "", temperature: float = 0.0
    ) -> LLMResponse: ...
