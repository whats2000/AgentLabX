"""Base code agent contract for external code generation."""
from __future__ import annotations
from abc import ABC, abstractmethod
from pathlib import Path
from pydantic import BaseModel


class CodeContext(BaseModel):
    task_description: str
    references: list[str]
    imports: list[str]


class CodeResult(BaseModel):
    success: bool
    files: list[str]
    explanation: str
    error: str | None = None


class BaseCodeAgent(ABC):
    name: str
    supports_streaming: bool

    @abstractmethod
    async def generate(self, task: str, context: CodeContext, workspace: Path) -> CodeResult: ...

    @abstractmethod
    async def edit(self, instruction: str, files: list[Path], context: CodeContext) -> CodeResult: ...

    @abstractmethod
    async def debug(self, error: str, files: list[Path], execution_log: str) -> CodeResult: ...
