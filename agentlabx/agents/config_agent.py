"""ConfigAgent: a generic agent instantiated from an AgentConfig (YAML-loaded)."""

from __future__ import annotations

from collections import deque
from typing import Any

from agentlabx.agents.base import AgentContext, BaseAgent, MemoryScope
from agentlabx.agents.config_loader import AgentConfig


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

    @classmethod
    def from_config(
        cls,
        config: AgentConfig,
        mock_responses: list[str] | deque[str] | None = None,
        *,
        llm_provider: Any = None,
        model: str = "claude-sonnet-4-6",
        cost_tracker: Any = None,
    ) -> ConfigAgent:
        """Instantiate a ConfigAgent from an AgentConfig.

        Pass llm_provider to enable real LLM inference. Without it, the agent
        returns stubs (Plan 2 behavior). Pass cost_tracker to accumulate usage.
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
        )

    async def inference(self, prompt: str, context: AgentContext) -> str:
        """Run inference. Precedence: mock_responses > llm_provider > stub."""
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
