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

    @classmethod
    def from_config(
        cls,
        config: AgentConfig,
        mock_responses: list[str] | deque[str] | None = None,
        *,
        llm_provider: Any = None,
        model: str = "claude-sonnet-4-6",
    ) -> ConfigAgent:
        """Instantiate a ConfigAgent from an AgentConfig.

        Pass llm_provider to enable real LLM inference (requires Plan 3 Task 10
        to fully wire the inference path). Without it, the agent returns stubs.
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
        )

    async def inference(self, prompt: str, context: AgentContext) -> str:
        """Run inference. Precedence: mock_responses > stub.

        Plan 3 Task 10 extends this to call llm_provider.query() between the
        mock_responses and stub branches so real LLM inference engages when a
        provider is injected and no scripted responses remain.
        """
        if self._mock_responses:
            response = self._mock_responses.popleft()
        else:
            response = f"[{self.name}] stub response to: {prompt[:50]}"

        # Append user + assistant turn to conversation history
        self.conversation_history.append({"role": "user", "content": prompt})
        self.conversation_history.append({"role": "assistant", "content": response})

        # Truncate: keep last max_history_length pairs (each pair = 2 entries)
        max_entries = self.max_history_length * 2
        if len(self.conversation_history) > max_entries:
            self.conversation_history = self.conversation_history[-max_entries:]

        return response
