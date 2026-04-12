"""Subprocess execution backend — runs Python code in a subprocess with reproducibility capture."""

from __future__ import annotations

import asyncio
import hashlib
import platform
import sys
import time
from datetime import UTC, datetime
from pathlib import Path

from agentlabx.core.state import ReproducibilityRecord
from agentlabx.providers.execution.base import BaseExecutionBackend, ExecutionResult


class SubprocessBackend(BaseExecutionBackend):
    """Executes Python code in a subprocess.

    Captures stdout, stderr, exit code, and execution time. Optionally captures
    reproducibility metadata (seed, environment hash, run command).
    """

    async def execute(
        self,
        *,
        code: str,
        workspace: Path,
        timeout: int = 120,
    ) -> ExecutionResult:
        """Execute code as a Python subprocess."""
        workspace.mkdir(parents=True, exist_ok=True)

        script_path = workspace / "_exec_script.py"
        script_path.write_text(code, encoding="utf-8")

        start_time = time.monotonic()
        try:
            proc = await asyncio.create_subprocess_exec(
                sys.executable,
                str(script_path),
                cwd=str(workspace),
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            try:
                stdout_bytes, stderr_bytes = await asyncio.wait_for(
                    proc.communicate(),
                    timeout=timeout,
                )
                stdout = stdout_bytes.decode("utf-8", errors="replace")
                stderr = stderr_bytes.decode("utf-8", errors="replace")
                exit_code = proc.returncode or 0
            except TimeoutError:
                proc.kill()
                await proc.wait()
                return ExecutionResult(
                    success=False,
                    stdout="",
                    stderr=f"Execution timeout after {timeout}s",
                    exit_code=-1,
                    execution_time=time.monotonic() - start_time,
                )
        finally:
            try:
                script_path.unlink()
            except FileNotFoundError:
                pass

        execution_time = time.monotonic() - start_time
        return ExecutionResult(
            success=exit_code == 0,
            stdout=stdout,
            stderr=stderr,
            exit_code=exit_code,
            execution_time=execution_time,
        )

    async def cleanup(self, workspace: Path) -> None:
        """Remove temporary execution artifacts. Leaves user files intact."""
        temp_files = [workspace / "_exec_script.py"]
        for f in temp_files:
            if f.exists():
                try:
                    f.unlink()
                except OSError:
                    pass

    async def capture_reproducibility(
        self,
        *,
        code: str,
        workspace: Path,
        seed: int = 42,
    ) -> ReproducibilityRecord:
        """Capture reproducibility metadata for an execution."""
        env_hash = self._hash_environment()
        run_command = f"python -c {code!r}"

        deps_snapshot: dict[str, str] = {}
        try:
            proc = await asyncio.create_subprocess_exec(
                sys.executable,
                "-m",
                "pip",
                "freeze",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.DEVNULL,
            )
            stdout_bytes, _ = await asyncio.wait_for(proc.communicate(), timeout=15)
            for line in stdout_bytes.decode("utf-8", errors="replace").splitlines():
                if "==" in line:
                    name, version = line.split("==", 1)
                    deps_snapshot[name.strip()] = version.strip()
        except (TimeoutError, OSError):
            pass

        return ReproducibilityRecord(
            random_seed=seed,
            environment_hash=env_hash,
            run_command=run_command,
            container_image=None,
            git_ref=None,
            dependencies_snapshot=deps_snapshot,
            timestamp=datetime.now(UTC),
        )

    def _hash_environment(self) -> str:
        """Hash of Python version + platform + key env vars."""
        components = [
            sys.version,
            platform.platform(),
            platform.python_implementation(),
        ]
        h = hashlib.sha256("|".join(components).encode()).hexdigest()
        return h[:16]
