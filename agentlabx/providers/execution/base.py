"""Base execution backend contract."""

from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path

from pydantic import BaseModel


class ExecutionResult(BaseModel):
    success: bool
    stdout: str
    stderr: str
    exit_code: int
    execution_time: float


class BaseExecutionBackend(ABC):
    # Plugin metadata — subclasses override. Surfaced by /api/plugins.
    name: str = "execution_backend"
    description: str = ""

    @abstractmethod
    async def execute(
        self, *, code: str, workspace: Path, timeout: int = 120
    ) -> ExecutionResult: ...

    @abstractmethod
    async def cleanup(self, workspace: Path) -> None: ...
