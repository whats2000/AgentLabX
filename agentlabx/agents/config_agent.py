"""ConfigAgent: a generic agent instantiated from an AgentConfig (YAML-loaded)."""

from __future__ import annotations

from collections import deque
from typing import Any

from agentlabx.agents.base import AgentContext, BaseAgent, MemoryScope
from agentlabx.agents.config_loader import AgentConfig


class ConfigAgent(BaseAgent):
    """Generic agent created from an AgentConfig. Supports mock responses for testing."""

    def __init__(
        self,
        *,
        name: str,
        role: str,
        system_prompt: str,
        tools: list[Any],
        memory_scope: MemoryScope,
        max_history_length: int = 10,
        mock_responses: deque[str] | None = None,
    ) -> None:
        super().__init__(
            name=name,
            role=role,
            system_prompt=system_prompt,
            tools=tools,
            memory_scope=memory_scope,
        )
        self.max_history_length = max_history_length
        self._mock_responses: deque[str] | None = mock_responses

    @classmethod
    def from_config(
        cls,
        config: AgentConfig,
        mock_responses: deque[str] | None = None,
    ) -> ConfigAgent:
        """Instantiate a ConfigAgent from an AgentConfig."""
        return cls(
            name=config.name,
            role=config.role,
            system_prompt=config.system_prompt,
            tools=[],  # Tool names stored in config; actual tool objects resolved later
            memory_scope=config.memory_scope,
            max_history_length=config.conversation_history_length,
            mock_responses=mock_responses,
        )

    async def inference(self, prompt: str, context: AgentContext) -> str:
        """Run inference. Uses mock_responses deque if available, else returns a stub."""
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
