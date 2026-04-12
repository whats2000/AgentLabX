"""Code executor tool using execution backend with reproducibility capture."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from pydantic import BaseModel

from agentlabx.providers.execution.base import BaseExecutionBackend
from agentlabx.tools.base import BaseTool, ToolResult


class CodeExecutorConfig(BaseModel):
    code: str
    workspace: str
    timeout: int = 120
    seed: int = 42


class CodeExecutor(BaseTool):
    name = "code_executor"
    description = (
        "Execute Python code in an isolated workspace. Returns stdout, stderr, exit_code,"
        " and reproducibility metadata."
    )
    config_schema = CodeExecutorConfig

    def __init__(self, backend: BaseExecutionBackend) -> None:
        self.backend = backend

    async def execute(self, **kwargs: Any) -> ToolResult:
        code = kwargs.get("code", "")
        workspace = Path(kwargs.get("workspace", "."))
        timeout = kwargs.get("timeout", 120)
        seed = kwargs.get("seed", 42)
        if not code:
            return ToolResult(success=False, error="code is required")
        try:
            result = await self.backend.execute(code=code, workspace=workspace, timeout=timeout)
            repro = None
            if hasattr(self.backend, "capture_reproducibility"):
                repro = await self.backend.capture_reproducibility(
                    code=code,
                    workspace=workspace,
                    seed=seed,
                )
            return ToolResult(
                success=result.success,
                data={
                    "stdout": result.stdout,
                    "stderr": result.stderr,
                    "exit_code": result.exit_code,
                    "execution_time": result.execution_time,
                    "reproducibility": repro.model_dump() if repro else None,
                },
                error=result.stderr if not result.success else None,
            )
        except Exception as e:
            return ToolResult(success=False, error=str(e))
