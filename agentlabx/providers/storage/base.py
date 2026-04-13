"""Base storage backend contract."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Literal

AgentTurnKind = Literal["llm_request", "llm_response", "tool_call", "tool_result", "dialogue"]


@dataclass
class AgentTurnRecord:
    session_id: str
    turn_id: str
    agent: str
    stage: str
    kind: AgentTurnKind
    payload: dict
    parent_turn_id: str | None = None
    system_prompt_hash: str | None = None
    tokens_in: int | None = None
    tokens_out: int | None = None
    cost_usd: float | None = None
    is_mock: bool = False
    ts: datetime | None = None  # backend fills if None


class BaseStorageBackend(ABC):
    # Plugin metadata — subclasses override. Surfaced by /api/plugins.
    name: str = "storage_backend"
    description: str = ""

    @abstractmethod
    async def save_state(self, session_id: str, stage: str, state: dict[str, Any]) -> None: ...

    @abstractmethod
    async def load_state(self, session_id: str, stage: str) -> dict[str, Any] | None: ...

    @abstractmethod
    async def save_artifact(
        self, session_id: str, artifact_type: str, name: str, data: bytes
    ) -> str: ...

    @abstractmethod
    async def load_artifact(self, path: str) -> bytes | None: ...

    @abstractmethod
    async def delete_session(self, session_id: str) -> None:
        """Remove all persisted state and artifacts for a session.

        Idempotent — deleting a non-existent session is not an error.
        """
        ...

    @abstractmethod
    async def append_agent_turn(self, record: AgentTurnRecord) -> int:
        """Insert one agent turn. Returns the row id."""

    @abstractmethod
    async def list_agent_turns(
        self,
        session_id: str,
        *,
        agent: str | None = None,
        stage: str | None = None,
        after_ts: datetime | None = None,
        limit: int = 200,
    ) -> list[AgentTurnRecord]:
        """List turns ordered by ts ascending. Filters optional."""
