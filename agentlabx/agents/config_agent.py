"""ConfigAgent: a generic agent instantiated from an AgentConfig (YAML-loaded)."""

from __future__ import annotations

import hashlib
import time
import uuid
from collections import deque
from typing import Any

from agentlabx.agents.base import AgentContext, BaseAgent, MemoryScope
from agentlabx.agents.config_loader import AgentConfig
from agentlabx.core.events import Event
from agentlabx.core.turn_context import TurnContext, push_turn
from agentlabx.server.events import EventTypes


class ConfigAgent(BaseAgent):
    """Generic agent created from an AgentConfig.

    Supports two inference modes:
    - Mock mode: scripted responses via mock_responses deque (for tests)
    - Real mode: llm_provider is set → Plan 3 Task 10 wires real inference

    When both are None, returns a stub string (Plan 2 behavior).
    """

    def __init__(
        self,
        *,
        name: str,
        role: str,
        system_prompt: str,
        tools: list[Any],
        memory_scope: MemoryScope,
        max_history_length: int = 10,
        mock_responses: list[str] | deque[str] | None = None,
        llm_provider: Any = None,
        model: str = "claude-sonnet-4-6",
        cost_tracker: Any = None,
        event_bus: Any = None,
        storage: Any = None,
    ) -> None:
        super().__init__(
            name=name,
            role=role,
            system_prompt=system_prompt,
            tools=tools,
            memory_scope=memory_scope,
        )
        self.max_history_length = max_history_length
        # Normalize list → deque so callers can pass either type
        self._mock_responses: deque[str] | None = (
            deque(mock_responses) if mock_responses is not None else None
        )
        self.llm_provider = llm_provider
        self.model = model
        self.cost_tracker = cost_tracker
        self._event_bus = event_bus
        self._storage = storage

    @classmethod
    def from_config(
        cls,
        config: AgentConfig,
        mock_responses: list[str] | deque[str] | None = None,
        *,
        llm_provider: Any = None,
        model: str = "claude-sonnet-4-6",
        cost_tracker: Any = None,
        event_bus: Any = None,
        storage: Any = None,
    ) -> ConfigAgent:
        """Instantiate a ConfigAgent from an AgentConfig.

        Pass llm_provider to enable real LLM inference. Without it, the agent
        returns stubs (Plan 2 behavior). Pass cost_tracker to accumulate usage.
        Pass event_bus and storage to enable turn event emission (Plan 6B).
        """
        return cls(
            name=config.name,
            role=config.role,
            system_prompt=config.system_prompt,
            tools=[],  # Tool names stored in config; actual tool objects resolved later
            memory_scope=config.memory_scope,
            max_history_length=config.conversation_history_length,
            mock_responses=mock_responses,
            llm_provider=llm_provider,
            model=model,
            cost_tracker=cost_tracker,
            event_bus=event_bus,
            storage=storage,
        )

    async def inference(self, prompt: str, context: AgentContext) -> str:
        """Run inference with turn event emission.

        Emits agent_turn_started before calling the LLM and agent_turn_completed
        after. Bumps turn_count and last_active_stage regardless of whether an
        event_bus is wired (so those fields are always accurate).

        Error handling: turn_count / last_active_stage / dirty are set BEFORE
        the LLM call so a partial turn is still observable on exception. If
        _run_inference_body raises, agent_turn_completed is NOT emitted (the
        exception propagates to the caller who can decide to retry or abort).
        """
        turn_id = uuid.uuid4().hex
        sp_hash = hashlib.sha1(self.system_prompt.encode("utf-8")).hexdigest()[:12]
        is_mock = bool(getattr(self.llm_provider, "is_mock", False)) or bool(self._mock_responses)

        # AgentContext uses `phase` as the stage identifier
        stage_name: str = getattr(context, "phase", "") or ""
        session_id: str | None = getattr(context, "session_id", None)

        ctx = TurnContext(
            turn_id=turn_id,
            agent=self.name,
            stage=stage_name,
            is_mock=is_mock,
            session_id=session_id,
            system_prompt_hash=sp_hash,
        )
        ctx_keys = (
            sorted(list(getattr(context, "state", {}).keys()))
            if getattr(context, "state", None)
            else []
        )

        start_payload = {
            "turn_id": turn_id,
            "agent": self.name,
            "stage": stage_name,
            "system_prompt_hash": sp_hash,
            "system_prompt_preview": self.system_prompt[:500],
            "assembled_context_keys": ctx_keys,
            "memory_scope_applied": {
                "read": list(self.memory_scope.read),
                "summarize": dict(self.memory_scope.summarize),
                "write": list(self.memory_scope.write),
            },
            "is_mock": is_mock,
        }
        if self._event_bus is not None:
            await self._event_bus.emit(
                Event(
                    type=EventTypes.AGENT_TURN_STARTED,
                    data=start_payload,
                    source=self.name,
                )
            )

        # Bump counters and mark dirty BEFORE running body so even on error the
        # agent's state reflects the attempt.
        self.turn_count += 1
        self.last_active_stage = stage_name
        self.dirty = True
        _t0 = time.perf_counter()

        with push_turn(ctx):
            content = await self._run_inference_body(prompt, context)

        end_payload = {
            "turn_id": turn_id,
            "agent": self.name,
            "stage": stage_name,
            "elapsed_ms": int((time.perf_counter() - _t0) * 1000),
            "tokens_in_total": ctx.tokens_in,
            "tokens_out_total": ctx.tokens_out,
            "cost_usd": ctx.cost_usd,
        }
        if self._event_bus is not None:
            await self._event_bus.emit(
                Event(
                    type=EventTypes.AGENT_TURN_COMPLETED,
                    data=end_payload,
                    source=self.name,
                )
            )
        return content

    async def _run_inference_body(self, prompt: str, context: AgentContext) -> str:
        """Execute the actual inference. Precedence: mock_responses > llm_provider > stub."""
        if self._mock_responses:
            response_text = self._mock_responses.popleft()
        elif self.llm_provider is not None:
            response = await self.llm_provider.query(
                model=self.model,
                prompt=prompt,
                system_prompt=self.system_prompt,
                temperature=0.0,
            )
            response_text = response.content
            # Cost tracking — update shared tracker if present
            if self.cost_tracker is not None:
                self.cost_tracker.add_usage(
                    tokens_in=response.tokens_in,
                    tokens_out=response.tokens_out,
                    cost=response.cost,
                )
        else:
            response_text = f"[{self.name}] stub response to: {prompt[:50]}"

        # Append user + assistant turn to conversation history
        self.conversation_history.append({"role": "user", "content": prompt})
        self.conversation_history.append({"role": "assistant", "content": response_text})

        # Truncate: keep last max_history_length pairs (each pair = 2 entries)
        max_entries = self.max_history_length * 2
        if len(self.conversation_history) > max_entries:
            self.conversation_history = self.conversation_history[-max_entries:]

        return response_text
