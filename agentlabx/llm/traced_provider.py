from __future__ import annotations

from agentlabx.events.bus import Event, EventBus
from agentlabx.llm.budget import BudgetTracker
from agentlabx.llm.protocol import BaseLLMProvider, LLMRequest, LLMResponse, MessageRole


class TracedLLMProvider:
    """Wraps any BaseLLMProvider with event emission, prompt redaction, and budget tracking."""

    def __init__(
        self,
        *,
        inner: BaseLLMProvider,
        bus: EventBus,
        budget: BudgetTracker | None = None,
        prompt_preview_length: int = 80,
    ) -> None:
        self._inner = inner
        self._bus = bus
        self._budget = budget
        self._preview_len = prompt_preview_length

    def _extract_prompt_preview(self, request: LLMRequest) -> str:
        """Extract the last user message content, truncated for the event payload."""
        text = ""
        for msg in reversed(request.messages):
            role = msg["role"] if isinstance(msg, dict) else msg.role
            content = msg["content"] if isinstance(msg, dict) else msg.content
            if role == MessageRole.USER:
                text = content
                break

        if len(text) > self._preview_len:
            return text[: self._preview_len] + "..."
        return text

    async def complete(self, request: LLMRequest) -> LLMResponse:
        # Pre-call budget check (concurrency-safe)
        if self._budget is not None:
            await self._budget.check_async()

        try:
            response = await self._inner.complete(request)
        except Exception as exc:
            await self._bus.emit(
                Event(
                    kind="llm.error",
                    payload={
                        "model": request.model,
                        "error": str(exc),
                        "prompt_preview": self._extract_prompt_preview(request),
                    },
                )
            )
            raise

        # Record cost in budget tracker (concurrency-safe)
        if self._budget is not None:
            await self._budget.record_async(cost_usd=response.cost_usd)

        # Emit success event
        await self._bus.emit(
            Event(
                kind="llm.called",
                payload={
                    "model": response.model,
                    "prompt_tokens": response.prompt_tokens,
                    "completion_tokens": response.completion_tokens,
                    "total_tokens": response.total_tokens,
                    "cost_usd": response.cost_usd,
                    "prompt_preview": self._extract_prompt_preview(request),
                },
            )
        )

        return response
