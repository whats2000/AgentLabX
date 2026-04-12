"""Tests for SubprocessBackend."""

from __future__ import annotations

from pathlib import Path

from agentlabx.core.state import ReproducibilityRecord
from agentlabx.providers.execution.subprocess_backend import SubprocessBackend


class TestSubprocessBackend:
    async def test_simple_execution(self, tmp_path: Path):
        backend = SubprocessBackend()
        result = await backend.execute(code="print('hello')", workspace=tmp_path)
        assert result.success is True
        assert "hello" in result.stdout
        assert result.exit_code == 0
        assert result.execution_time > 0

    async def test_exit_code_captured(self, tmp_path: Path):
        backend = SubprocessBackend()
        result = await backend.execute(code="import sys; sys.exit(1)", workspace=tmp_path)
        assert result.success is False
        assert result.exit_code == 1

    async def test_stderr_captured(self, tmp_path: Path):
        backend = SubprocessBackend()
        result = await backend.execute(
            code="import sys; print('err', file=sys.stderr); sys.exit(0)",
            workspace=tmp_path,
        )
        assert "err" in result.stderr

    async def test_timeout_terminates(self, tmp_path: Path):
        backend = SubprocessBackend()
        result = await backend.execute(
            code="import time; time.sleep(10)",
            workspace=tmp_path,
            timeout=2,
        )
        assert result.success is False
        assert "timeout" in result.stderr.lower() or result.exit_code != 0

    async def test_working_directory(self, tmp_path: Path):
        backend = SubprocessBackend()
        result = await backend.execute(
            code="import os; print(os.getcwd())",
            workspace=tmp_path,
        )
        # Normalize paths — Windows may have different case (e.g. AppData vs appdata)
        assert str(tmp_path).lower() in result.stdout.lower()

    async def test_cleanup(self, tmp_path: Path):
        backend = SubprocessBackend()
        await backend.execute(code="print('hi')", workspace=tmp_path)
        # Cleanup should not raise
        await backend.cleanup(tmp_path)

    async def test_capture_reproducibility(self, tmp_path: Path):
        backend = SubprocessBackend()
        rec = await backend.capture_reproducibility(
            code="print('test')",
            workspace=tmp_path,
            seed=42,
        )
        assert isinstance(rec, ReproducibilityRecord)
        assert rec.random_seed == 42
        assert len(rec.environment_hash) > 0
        assert "print" in rec.run_command
