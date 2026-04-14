"""Tracing wrapper around BaseLLMProvider — emits agent_llm_* events and
writes agent_turns rows when a TurnContext is active. Transparent passthrough
when no turn is active (e.g., during startup/tests without pipeline context).
"""

from __future__ import annotations

from agentlabx.core.event_types import EventTypes
from agentlabx.core.events import Event
from agentlabx.core.turn_context import current_turn
from agentlabx.providers.llm.base import BaseLLMProvider, LLMResponse
from agentlabx.providers.storage.base import AgentTurnRecord


class TracedLLMProvider(BaseLLMProvider):
    """Wraps any LLMProvider; emits agent_llm_request/response events
    and writes agent_turns rows when a TurnContext is active."""

    def __init__(self, inner: BaseLLMProvider, event_bus, storage):
        self._inner = inner
        self._bus = event_bus
        self._storage = storage
        self.is_mock = getattr(inner, "is_mock", False)

    @property
    def name(self) -> str:
        return getattr(self._inner, "name", "traced")

    async def query(
        self,
        *,
        model: str | None,
        prompt: str,
        system_prompt: str = "",
        temperature: float = 0.0,
    ) -> LLMResponse:
        ctx = current_turn()
        if ctx is None:
            return await self._inner.query(
                model=model,
                prompt=prompt,
                system_prompt=system_prompt,
                temperature=temperature,
            )

        req_payload = {
            "model": model,
            "prompt": prompt,
            "system_prompt": system_prompt,
            "temperature": temperature,
            "is_mock": self.is_mock,
            "turn_id": ctx.turn_id,
            "parent_turn_id": ctx.parent_turn_id,
        }
        await self._bus.emit(
            Event(
                type=EventTypes.AGENT_LLM_REQUEST,
                data=req_payload,
                source=ctx.agent,
            )
        )
        if ctx.session_id:
            await self._storage.append_agent_turn(
                AgentTurnRecord(
                    session_id=ctx.session_id,
                    turn_id=ctx.turn_id,
                    parent_turn_id=ctx.parent_turn_id,
                    agent=ctx.agent,
                    stage=ctx.stage,
                    kind="llm_request",
                    payload=req_payload,
                    system_prompt_hash=ctx.system_prompt_hash,
                    is_mock=self.is_mock,
                )
            )

        resp = await self._inner.query(
            model=model,
            prompt=prompt,
            system_prompt=system_prompt,
            temperature=temperature,
        )

        resp_payload = {
            "turn_id": ctx.turn_id,
            "content": resp.content,
            "tokens_in": resp.tokens_in,
            "tokens_out": resp.tokens_out,
            "cost_usd": resp.cost,
            "model": resp.model,
            "is_mock": self.is_mock,
        }
        ctx.tokens_in += resp.tokens_in or 0
        ctx.tokens_out += resp.tokens_out or 0
        ctx.cost_usd += resp.cost or 0.0

        await self._bus.emit(
            Event(
                type=EventTypes.AGENT_LLM_RESPONSE,
                data=resp_payload,
                source=ctx.agent,
            )
        )
        if ctx.session_id:
            await self._storage.append_agent_turn(
                AgentTurnRecord(
                    session_id=ctx.session_id,
                    turn_id=ctx.turn_id,
                    parent_turn_id=ctx.parent_turn_id,
                    agent=ctx.agent,
                    stage=ctx.stage,
                    kind="llm_response",
                    payload=resp_payload,
                    tokens_in=resp.tokens_in,
                    tokens_out=resp.tokens_out,
                    cost_usd=resp.cost,
                    is_mock=self.is_mock,
                )
            )
        return resp
