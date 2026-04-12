"""Base storage backend contract."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any


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
