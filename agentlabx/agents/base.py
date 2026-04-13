"""Base agent contract with differentiated memory scopes."""

from __future__ import annotations

import fnmatch
from abc import ABC, abstractmethod
from typing import Any

from pydantic import BaseModel

from agentlabx.tools.base import BaseTool


class MemoryScope(BaseModel):
    read: list[str] = []
    write: list[str] = []
    summarize: dict[str, str] = {}

    def can_read(self, key: str) -> bool:
        return any(fnmatch.fnmatch(key, pattern) for pattern in self.read)

    def can_write(self, key: str) -> bool:
        return key in self.write


class AgentContext(BaseModel):
    phase: str
    state: dict[str, Any]
    working_memory: dict[str, Any]
    session_id: str | None = None
    model_config = {"arbitrary_types_allowed": True}


class BaseAgent(ABC):
    def __init__(
        self,
        *,
        name: str,
        role: str,
        system_prompt: str,
        tools: list[BaseTool],
        memory_scope: MemoryScope,
    ) -> None:
        self.name = name
        self.role = role
        self.system_prompt = system_prompt
        self.tools = tools
        self.memory_scope = memory_scope
        self.conversation_history: list[dict[str, str]] = []
        self.working_memory: dict[str, Any] = {}
        self.notes: list[str] = []
        self.turn_count: int = 0
        self.last_active_stage: str = ""
        self.dirty: bool = False

    @abstractmethod
    async def inference(self, prompt: str, context: AgentContext) -> str: ...

    def get_context(self, phase: str) -> str:
        return self.system_prompt

    def reset(self) -> None:
        self.conversation_history.clear()
        self.working_memory.clear()
        self.notes = []
        self.turn_count = 0
        self.last_active_stage = ""
        self.dirty = False

    def add_note(self, note: str) -> None:
        self.notes.append(note)
        self.dirty = True

    def mark_dirty(self) -> None:
        self.dirty = True

    def snapshot_memory(self) -> dict:
        """Return an AgentMemoryRecord-shaped dict."""
        return {
            "working_memory": dict(self.working_memory),
            "notes": list(self.notes),
            "last_active_stage": self.last_active_stage,
            "turn_count": self.turn_count,
        }

    def load_memory(self, record: dict) -> None:
        self.working_memory = dict(record.get("working_memory", {}))
        self.notes = list(record.get("notes", []))
        self.last_active_stage = record.get("last_active_stage", "")
        self.turn_count = int(record.get("turn_count", 0))
        self.dirty = False
