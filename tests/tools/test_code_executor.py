"""Tests for code executor tool."""

from __future__ import annotations

import pytest

from agentlabx.providers.execution.subprocess_backend import SubprocessBackend
from agentlabx.tools.code_executor import CodeExecutor


class TestCodeExecutor:
    @pytest.mark.asyncio
    async def test_execute_simple_code(self, tmp_path):
        backend = SubprocessBackend()
        tool = CodeExecutor(backend=backend)
        result = await tool.execute(
            code='print("hello")',
            workspace=str(tmp_path),
            timeout=30,
        )
        assert result.success is True
        assert "hello" in result.data["stdout"]
        assert result.data["exit_code"] == 0

    @pytest.mark.asyncio
    async def test_execute_failing_code(self, tmp_path):
        backend = SubprocessBackend()
        tool = CodeExecutor(backend=backend)
        result = await tool.execute(
            code="import sys; sys.exit(1)",
            workspace=str(tmp_path),
            timeout=30,
        )
        assert result.success is False
        assert result.data["exit_code"] == 1

    @pytest.mark.asyncio
    async def test_captures_reproducibility(self, tmp_path):
        backend = SubprocessBackend()
        tool = CodeExecutor(backend=backend)
        result = await tool.execute(
            code='print("repro test")',
            workspace=str(tmp_path),
            timeout=30,
            seed=99,
        )
        assert result.success is True
        repro = result.data["reproducibility"]
        assert repro is not None
        assert repro["random_seed"] == 99
        assert "environment_hash" in repro

    @pytest.mark.asyncio
    async def test_missing_code_returns_error(self, tmp_path):
        backend = SubprocessBackend()
        tool = CodeExecutor(backend=backend)
        result = await tool.execute(workspace=str(tmp_path))
        assert result.success is False
        assert "code is required" in result.error
