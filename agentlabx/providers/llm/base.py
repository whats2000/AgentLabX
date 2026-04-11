"""Base LLM provider contract."""
from __future__ import annotations
from abc import ABC, abstractmethod
from pydantic import BaseModel


class LLMResponse(BaseModel):
    content: str
    tokens_in: int
    tokens_out: int
    model: str
    cost: float


class BaseLLMProvider(ABC):
    @abstractmethod
    async def query(self, *, model: str, prompt: str, system_prompt: str = "", temperature: float = 0.0) -> LLMResponse: ...
