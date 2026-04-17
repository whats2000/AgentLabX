from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from enum import StrEnum
from typing import Protocol, runtime_checkable


class MessageRole(StrEnum):
    SYSTEM = "system"
    USER = "user"
    ASSISTANT = "assistant"


@dataclass(frozen=True)
class Message:
    role: MessageRole
    content: str


@dataclass(frozen=True)
class LLMRequest:
    """Immutable request to an LLM provider."""

    model: str
    messages: Sequence[dict[str, str] | Message]
    temperature: float | None = None
    max_tokens: int | None = None
    system_prompt: str | None = None


@dataclass(frozen=True)
class LLMResponse:
    """Immutable response from an LLM provider."""

    content: str
    model: str
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int
    cost_usd: float


class BudgetExceededError(Exception):
    """Raised when a per-project cost cap is exceeded."""

    def __init__(self, spent: float, cap: float) -> None:
        self.spent = spent
        self.cap = cap
        super().__init__(f"budget exceeded: spent ${spent:.4f} of ${cap:.4f} cap")


@runtime_checkable
class BaseLLMProvider(Protocol):
    """Interface all LLM providers must satisfy."""

    async def complete(self, request: LLMRequest) -> LLMResponse: ...
