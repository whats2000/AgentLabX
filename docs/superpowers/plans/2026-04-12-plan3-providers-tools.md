# Plan 3: Providers & Tools — Real Backends and Integrations

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement concrete providers and tools — replace Plan 2's mocks with real LLM inference (LiteLLM), real code execution (subprocess with reproducibility capture), real storage (SQLite), and real research tools (ArXiv, HuggingFace, Semantic Scholar, GitHub, LaTeX, code executor). Also upgrade PIAgent and 3 key stages to use real LLM judgment. This is what makes AgentLabX actually usable end-to-end.

**Architecture:** All providers and tools implement the abstract base contracts from Plan 1. LiteLLM wraps all LLM providers behind one interface. Subprocess backend captures reproducibility metadata per execution. SQLite stores session state + checkpoints. ConfigAgent gets real inference via injected LLM provider. PIAgent uses LLM for real confidence judgment. Literature review, plan formulation, and peer review stages get real agent dialogue implementations.

**Tech Stack:** LiteLLM 1.82+, SQLAlchemy 2 (async, for SQLite), arxiv 2.1+, huggingface_hub 0.24+, semanticscholar 0.10+, PyGithub 2.3+, PyPDF2 3.0+, pdflatex binary (system dependency), Python 3.12

**Spec reference:** `docs/superpowers/specs/2026-04-12-agentlabx-platform-design.md` §6, §8, §9, §11

**Depends on:** Plan 1 (base contracts), Plan 2 (pipeline, agents, session manager — 181 tests)

**API keys required:** At least one of: `OPENAI_API_KEY`, `ANTHROPIC_API_KEY`, `GEMINI_API_KEY`, `DEEPSEEK_API_KEY`. Tests use a mock LLM provider so no keys needed for CI.

---

## File Structure

```
agentlabx/
  providers/
    llm/
      litellm_provider.py      # LiteLLMProvider — real LLM inference via LiteLLM
      mock_provider.py          # MockLLMProvider — scripted responses for testing
    execution/
      subprocess_backend.py    # SubprocessBackend — runs code in subprocess with reproducibility capture
    storage/
      sqlite_backend.py         # SQLiteBackend — SQLAlchemy async, sessions + checkpoints + artifacts
      models.py                 # SQLAlchemy ORM models
    code_agent/
      claude_code_agent.py     # ClaudeCodeAgent — delegates to Claude Code SDK
      builtin_agent.py          # BuiltinCodeAgent — fallback direct LLM code generation
  tools/
    arxiv_search.py             # ArXiv paper search with TF-IDF ranking
    hf_dataset_search.py        # HuggingFace dataset search
    semantic_scholar.py         # Semantic Scholar citation search
    github_search.py            # GitHub code search + repo clone
    session_artifact_search.py  # Cross-session code reuse search
    code_executor.py            # Python code execution with reproducibility
    latex_compiler.py           # LaTeX → PDF compilation
  agents/
    config_agent.py             # UPGRADED: real LLM inference via injected provider
    pi_agent.py                 # UPGRADED: real LLM judgment for transitions
  stages/
    literature_review.py        # NEW: real lit review stage (replaces skeleton)
    plan_formulation.py         # NEW: real plan formulation (postdoc + phd dialogue)
    peer_review.py              # NEW: real blind peer review
tests/
  providers/
    test_litellm_provider.py
    test_mock_provider.py
    test_subprocess_backend.py
    test_sqlite_backend.py
    test_claude_code_agent.py
    test_builtin_code_agent.py
  tools/
    test_arxiv_search.py
    test_hf_dataset_search.py
    test_semantic_scholar.py
    test_github_search.py
    test_session_artifact_search.py
    test_code_executor.py
    test_latex_compiler.py
  agents/
    test_config_agent_real_llm.py
    test_pi_agent_real_llm.py
  stages/
    test_literature_review_real.py
    test_plan_formulation_real.py
    test_peer_review_real.py
```

---

### Task 1: Add Plan 3 Dependencies

**Files:**
- Modify: `pyproject.toml`

- [ ] **Step 1: Add dependencies**

```toml
dependencies = [
    # ... existing ...
    "litellm>=1.82,<2.0",
    "sqlalchemy[asyncio]>=2.0,<3.0",
    "aiosqlite>=0.19,<1.0",
    "arxiv>=2.1,<3.0",
    "huggingface-hub>=0.24,<1.0",
    "semanticscholar>=0.10,<1.0",
    "PyGithub>=2.3,<3.0",
    "pypdf>=4.0,<5.0",
    "scikit-learn>=1.4,<2.0",
    "numpy>=1.26,<3.0",
]
```

- [ ] **Step 2: Install**

Run: `cd d:/GitHub/AgentLabX && uv sync --extra dev`

- [ ] **Step 3: Verify imports**

Run: `cd d:/GitHub/AgentLabX && uv run python -c "import litellm, arxiv, huggingface_hub, github, pypdf, sklearn; print('all OK')"`

- [ ] **Step 4: Commit**

```bash
git add pyproject.toml uv.lock
git commit -m "build: add Plan 3 dependencies (litellm, sqlalchemy, research tools)"
```

---

### Task 2: LiteLLM Provider

**Files:**
- Create: `agentlabx/providers/llm/litellm_provider.py`
- Create: `agentlabx/providers/llm/mock_provider.py`
- Create: `tests/providers/test_litellm_provider.py`
- Create: `tests/providers/test_mock_provider.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/providers/test_mock_provider.py
from __future__ import annotations
import pytest
from agentlabx.providers.llm.mock_provider import MockLLMProvider


class TestMockLLMProvider:
    async def test_scripted_responses(self):
        provider = MockLLMProvider(responses=["response 1", "response 2"])
        r1 = await provider.query(model="mock", prompt="hello")
        assert r1.content == "response 1"
        r2 = await provider.query(model="mock", prompt="hi again")
        assert r2.content == "response 2"

    async def test_token_tracking(self):
        provider = MockLLMProvider(responses=["test response"])
        r = await provider.query(model="mock", prompt="test prompt")
        assert r.tokens_in > 0
        assert r.tokens_out > 0
        assert r.cost == 0.0

    async def test_default_response_when_empty(self):
        provider = MockLLMProvider(responses=[])
        r = await provider.query(model="mock", prompt="anything")
        assert "mock" in r.content.lower()

    async def test_records_calls(self):
        provider = MockLLMProvider(responses=["a", "b"])
        await provider.query(model="mock", prompt="first")
        await provider.query(model="mock", prompt="second")
        assert len(provider.calls) == 2
        assert provider.calls[0]["prompt"] == "first"
```

```python
# tests/providers/test_litellm_provider.py
"""Tests for LiteLLMProvider.

These tests use mocking since real API calls require keys. One integration test
is marked with @pytest.mark.integration and skipped unless ANTHROPIC_API_KEY is set.
"""

from __future__ import annotations
import os
from unittest.mock import AsyncMock, MagicMock, patch
import pytest
from agentlabx.providers.llm.litellm_provider import LiteLLMProvider


class TestLiteLLMProvider:
    async def test_query_calls_acompletion(self):
        provider = LiteLLMProvider()
        mock_response = MagicMock()
        mock_response.choices = [MagicMock(message=MagicMock(content="Hello"))]
        mock_response.usage.prompt_tokens = 10
        mock_response.usage.completion_tokens = 5
        mock_response.model = "anthropic/claude-sonnet-4-6"

        with patch("agentlabx.providers.llm.litellm_provider.acompletion", new_callable=AsyncMock, return_value=mock_response):
            with patch("agentlabx.providers.llm.litellm_provider.completion_cost", return_value=0.0025):
                response = await provider.query(
                    model="anthropic/claude-sonnet-4-6",
                    prompt="Hello world",
                )
        assert response.content == "Hello"
        assert response.tokens_in == 10
        assert response.tokens_out == 5
        assert response.cost == 0.0025

    async def test_query_includes_system_prompt(self):
        provider = LiteLLMProvider()
        mock_response = MagicMock()
        mock_response.choices = [MagicMock(message=MagicMock(content="response"))]
        mock_response.usage.prompt_tokens = 1
        mock_response.usage.completion_tokens = 1
        mock_response.model = "test"

        acompletion_mock = AsyncMock(return_value=mock_response)
        with patch("agentlabx.providers.llm.litellm_provider.acompletion", acompletion_mock):
            with patch("agentlabx.providers.llm.litellm_provider.completion_cost", return_value=0.0):
                await provider.query(
                    model="test",
                    prompt="user msg",
                    system_prompt="you are a helper",
                )
        # Inspect call args
        call_kwargs = acompletion_mock.call_args.kwargs
        messages = call_kwargs["messages"]
        assert messages[0] == {"role": "system", "content": "you are a helper"}
        assert messages[1] == {"role": "user", "content": "user msg"}

    async def test_retry_on_rate_limit(self):
        from litellm import RateLimitError
        provider = LiteLLMProvider(max_retries=2)
        mock_response = MagicMock()
        mock_response.choices = [MagicMock(message=MagicMock(content="ok"))]
        mock_response.usage.prompt_tokens = 1
        mock_response.usage.completion_tokens = 1
        mock_response.model = "test"

        call_count = {"n": 0}

        async def flaky_acompletion(**kwargs):
            call_count["n"] += 1
            if call_count["n"] < 2:
                raise RateLimitError("rate limited", llm_provider="test", model="test")
            return mock_response

        with patch("agentlabx.providers.llm.litellm_provider.acompletion", flaky_acompletion):
            with patch("agentlabx.providers.llm.litellm_provider.completion_cost", return_value=0.0):
                response = await provider.query(model="test", prompt="hi")
        assert response.content == "ok"
        assert call_count["n"] == 2

    @pytest.mark.skipif(
        not os.getenv("ANTHROPIC_API_KEY"),
        reason="ANTHROPIC_API_KEY not set — skipping real API test",
    )
    async def test_real_api_call(self):
        """Integration test — only runs with real API key."""
        provider = LiteLLMProvider()
        response = await provider.query(
            model="anthropic/claude-haiku-4-5-20251001",
            prompt="Say 'hello' in one word.",
            temperature=0.0,
        )
        assert len(response.content) > 0
        assert response.tokens_in > 0
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd d:/GitHub/AgentLabX && uv run pytest tests/providers/test_litellm_provider.py tests/providers/test_mock_provider.py -v`
Expected: FAIL

- [ ] **Step 3: Implement mock_provider.py**

```python
# agentlabx/providers/llm/mock_provider.py
"""Mock LLM provider for testing — returns scripted responses."""

from __future__ import annotations

from collections import deque
from typing import Any

from agentlabx.providers.llm.base import BaseLLMProvider, LLMResponse


class MockLLMProvider(BaseLLMProvider):
    """Returns scripted responses in order. Tracks call history for assertions."""

    def __init__(self, responses: list[str] | None = None) -> None:
        self._responses: deque[str] = deque(responses or [])
        self.calls: list[dict[str, Any]] = []

    async def query(
        self,
        *,
        model: str,
        prompt: str,
        system_prompt: str = "",
        temperature: float = 0.0,
    ) -> LLMResponse:
        self.calls.append({
            "model": model,
            "prompt": prompt,
            "system_prompt": system_prompt,
            "temperature": temperature,
        })

        if self._responses:
            content = self._responses.popleft()
        else:
            content = f"[mock] response to: {prompt[:50]}"

        return LLMResponse(
            content=content,
            tokens_in=max(1, len(prompt) // 4),
            tokens_out=max(1, len(content) // 4),
            model=model,
            cost=0.0,
        )
```

- [ ] **Step 4: Implement litellm_provider.py**

```python
# agentlabx/providers/llm/litellm_provider.py
"""Production LLM provider using LiteLLM for multi-provider support."""

from __future__ import annotations

import asyncio
from typing import Any

from litellm import acompletion, completion_cost
from litellm import AuthenticationError, RateLimitError, Timeout

from agentlabx.providers.llm.base import BaseLLMProvider, LLMResponse


class LiteLLMProvider(BaseLLMProvider):
    """LLM provider backed by LiteLLM.

    Supports all LiteLLM-compatible providers via the "provider/model" format:
    - "openai/gpt-4o"
    - "anthropic/claude-sonnet-4-6"
    - "gemini/gemini-2.0-pro"
    - "deepseek/deepseek-chat"
    - "ollama/llama2"

    API keys are read from environment variables (OPENAI_API_KEY, ANTHROPIC_API_KEY, etc.)
    """

    def __init__(
        self,
        *,
        max_retries: int = 3,
        retry_delay: float = 1.0,
        timeout: float = 120.0,
    ) -> None:
        self.max_retries = max_retries
        self.retry_delay = retry_delay
        self.timeout = timeout

    async def query(
        self,
        *,
        model: str,
        prompt: str,
        system_prompt: str = "",
        temperature: float = 0.0,
    ) -> LLMResponse:
        """Send a completion request with retry on rate limits and timeouts."""
        messages: list[dict[str, str]] = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})

        last_error: Exception | None = None
        for attempt in range(self.max_retries):
            try:
                response = await acompletion(
                    model=model,
                    messages=messages,
                    temperature=temperature,
                    timeout=self.timeout,
                )

                content = response.choices[0].message.content or ""
                tokens_in = response.usage.prompt_tokens
                tokens_out = response.usage.completion_tokens

                try:
                    cost = completion_cost(completion_response=response)
                except Exception:
                    cost = 0.0

                return LLMResponse(
                    content=content,
                    tokens_in=tokens_in,
                    tokens_out=tokens_out,
                    model=getattr(response, "model", model),
                    cost=float(cost or 0.0),
                )

            except (RateLimitError, Timeout) as e:
                last_error = e
                if attempt < self.max_retries - 1:
                    await asyncio.sleep(self.retry_delay * (2**attempt))
                    continue
                raise
            except AuthenticationError:
                raise  # Don't retry auth errors

        if last_error:
            raise last_error
        msg = f"LLM query failed after {self.max_retries} retries"
        raise RuntimeError(msg)
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd d:/GitHub/AgentLabX && uv run pytest tests/providers/test_litellm_provider.py tests/providers/test_mock_provider.py -v`
Expected: All PASS

- [ ] **Step 6: Commit**

```bash
git add agentlabx/providers/llm/ tests/providers/test_litellm_provider.py tests/providers/test_mock_provider.py
git commit -m "feat(providers): add LiteLLM provider with retry logic and MockLLMProvider for testing"
```

---

### Task 3: Subprocess Execution Backend with Reproducibility

**Files:**
- Create: `agentlabx/providers/execution/subprocess_backend.py`
- Create: `tests/providers/test_subprocess_backend.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/providers/test_subprocess_backend.py
from __future__ import annotations
import asyncio
from pathlib import Path
import pytest
from agentlabx.providers.execution.subprocess_backend import SubprocessBackend
from agentlabx.core.state import ReproducibilityRecord


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
        # Normalize paths (tmp_path on Windows may have different case)
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd d:/GitHub/AgentLabX && uv run pytest tests/providers/test_subprocess_backend.py -v`
Expected: FAIL

- [ ] **Step 3: Implement subprocess_backend.py**

```python
# agentlabx/providers/execution/subprocess_backend.py
"""Subprocess execution backend — runs Python code in a subprocess with reproducibility capture."""

from __future__ import annotations

import asyncio
import hashlib
import subprocess
import sys
import time
from datetime import datetime, timezone
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

        # Write code to a temp file in workspace
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
            except asyncio.TimeoutError:
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
                sys.executable, "-m", "pip", "freeze",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.DEVNULL,
            )
            stdout_bytes, _ = await asyncio.wait_for(proc.communicate(), timeout=15)
            for line in stdout_bytes.decode("utf-8", errors="replace").splitlines():
                if "==" in line:
                    name, version = line.split("==", 1)
                    deps_snapshot[name.strip()] = version.strip()
        except (asyncio.TimeoutError, OSError):
            pass

        return ReproducibilityRecord(
            random_seed=seed,
            environment_hash=env_hash,
            run_command=run_command,
            container_image=None,
            git_ref=None,
            dependencies_snapshot=deps_snapshot,
            timestamp=datetime.now(timezone.utc),
        )

    def _hash_environment(self) -> str:
        """Hash of Python version + platform + key env vars."""
        import platform
        components = [
            sys.version,
            platform.platform(),
            platform.python_implementation(),
        ]
        h = hashlib.sha256("|".join(components).encode()).hexdigest()
        return h[:16]
```

- [ ] **Step 4: Run tests, commit**

Run: `cd d:/GitHub/AgentLabX && uv run pytest tests/providers/test_subprocess_backend.py -v`

```bash
git add agentlabx/providers/execution/subprocess_backend.py tests/providers/test_subprocess_backend.py
git commit -m "feat(providers): add subprocess execution backend with reproducibility capture"
```

---

### Task 4: SQLite Storage Backend

**Files:**
- Create: `agentlabx/providers/storage/models.py`
- Create: `agentlabx/providers/storage/sqlite_backend.py`
- Create: `tests/providers/test_sqlite_backend.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/providers/test_sqlite_backend.py
from __future__ import annotations
from pathlib import Path
import pytest
from agentlabx.providers.storage.sqlite_backend import SQLiteBackend


@pytest.fixture()
async def backend(tmp_path: Path) -> SQLiteBackend:
    db_path = tmp_path / "test.db"
    b = SQLiteBackend(database_url=f"sqlite+aiosqlite:///{db_path}", artifacts_path=tmp_path / "artifacts")
    await b.initialize()
    yield b
    await b.close()


class TestSQLiteBackend:
    async def test_save_and_load_state(self, backend: SQLiteBackend):
        await backend.save_state("sess-1", "lit_review", {"papers": 5, "summary": "test"})
        state = await backend.load_state("sess-1", "lit_review")
        assert state == {"papers": 5, "summary": "test"}

    async def test_load_missing_returns_none(self, backend: SQLiteBackend):
        state = await backend.load_state("nonexistent", "stage")
        assert state is None

    async def test_save_overwrites(self, backend: SQLiteBackend):
        await backend.save_state("sess-1", "lit_review", {"v": 1})
        await backend.save_state("sess-1", "lit_review", {"v": 2})
        state = await backend.load_state("sess-1", "lit_review")
        assert state == {"v": 2}

    async def test_state_is_session_scoped(self, backend: SQLiteBackend):
        await backend.save_state("sess-a", "lit_review", {"owner": "a"})
        await backend.save_state("sess-b", "lit_review", {"owner": "b"})
        a = await backend.load_state("sess-a", "lit_review")
        b = await backend.load_state("sess-b", "lit_review")
        assert a["owner"] == "a"
        assert b["owner"] == "b"

    async def test_save_and_load_artifact(self, backend: SQLiteBackend):
        path = await backend.save_artifact("sess-1", "code", "train.py", b"print('hi')")
        data = await backend.load_artifact(path)
        assert data == b"print('hi')"

    async def test_artifact_missing_returns_none(self, backend: SQLiteBackend):
        data = await backend.load_artifact("nonexistent/path")
        assert data is None

    async def test_artifact_namespacing(self, backend: SQLiteBackend):
        """Artifacts for different sessions shouldn't collide."""
        p1 = await backend.save_artifact("sess-a", "code", "file.py", b"a")
        p2 = await backend.save_artifact("sess-b", "code", "file.py", b"b")
        assert p1 != p2
        assert await backend.load_artifact(p1) == b"a"
        assert await backend.load_artifact(p2) == b"b"
```

- [ ] **Step 2: Implement models.py**

```python
# agentlabx/providers/storage/models.py
"""SQLAlchemy ORM models for SQLite storage."""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import JSON, DateTime, Integer, String, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class SessionRecord(Base):
    __tablename__ = "sessions"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    user_id: Mapped[str] = mapped_column(String, index=True)
    topic: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String)
    pipeline_config: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(timezone.utc)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(timezone.utc)
    )


class CheckpointRecord(Base):
    __tablename__ = "checkpoints"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    session_id: Mapped[str] = mapped_column(String, index=True)
    stage: Mapped[str] = mapped_column(String)
    state_blob: Mapped[dict] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(timezone.utc)
    )


class ArtifactRecord(Base):
    __tablename__ = "artifacts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    session_id: Mapped[str] = mapped_column(String, index=True)
    artifact_type: Mapped[str] = mapped_column(String)
    name: Mapped[str] = mapped_column(String)
    path: Mapped[str] = mapped_column(String, unique=True)
    size_bytes: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(timezone.utc)
    )
```

- [ ] **Step 3: Implement sqlite_backend.py**

```python
# agentlabx/providers/storage/sqlite_backend.py
"""SQLite storage backend using SQLAlchemy async."""

from __future__ import annotations

import uuid
from pathlib import Path
from typing import Any

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from agentlabx.providers.storage.base import BaseStorageBackend
from agentlabx.providers.storage.models import (
    ArtifactRecord,
    Base,
    CheckpointRecord,
)


class SQLiteBackend(BaseStorageBackend):
    """Async SQLite backend.

    Stores pipeline state as JSON blobs in the checkpoints table.
    Stores artifacts as files on disk with metadata in the artifacts table.
    Paths are namespaced by session_id.
    """

    def __init__(self, *, database_url: str, artifacts_path: Path) -> None:
        self.database_url = database_url
        self.artifacts_path = Path(artifacts_path)
        self._engine = None
        self._session_factory: async_sessionmaker[AsyncSession] | None = None

    async def initialize(self) -> None:
        """Create database tables and artifacts directory."""
        self._engine = create_async_engine(self.database_url, echo=False)
        self._session_factory = async_sessionmaker(self._engine, expire_on_commit=False)
        self.artifacts_path.mkdir(parents=True, exist_ok=True)

        async with self._engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

    async def close(self) -> None:
        if self._engine:
            await self._engine.dispose()

    async def save_state(
        self, session_id: str, stage: str, state: dict[str, Any]
    ) -> None:
        if self._session_factory is None:
            msg = "Backend not initialized — call initialize() first"
            raise RuntimeError(msg)
        async with self._session_factory() as sess:
            # Delete existing checkpoint for this session+stage (overwrite semantics)
            await sess.execute(
                delete(CheckpointRecord).where(
                    CheckpointRecord.session_id == session_id,
                    CheckpointRecord.stage == stage,
                )
            )
            sess.add(CheckpointRecord(session_id=session_id, stage=stage, state_blob=state))
            await sess.commit()

    async def load_state(
        self, session_id: str, stage: str
    ) -> dict[str, Any] | None:
        if self._session_factory is None:
            return None
        async with self._session_factory() as sess:
            result = await sess.execute(
                select(CheckpointRecord)
                .where(
                    CheckpointRecord.session_id == session_id,
                    CheckpointRecord.stage == stage,
                )
                .order_by(CheckpointRecord.created_at.desc())
                .limit(1)
            )
            record = result.scalar_one_or_none()
            return record.state_blob if record else None

    async def save_artifact(
        self,
        session_id: str,
        artifact_type: str,
        name: str,
        data: bytes,
    ) -> str:
        if self._session_factory is None:
            msg = "Backend not initialized — call initialize() first"
            raise RuntimeError(msg)

        # Namespaced path: artifacts_path/session_id/artifact_type/uuid_name
        session_dir = self.artifacts_path / session_id / artifact_type
        session_dir.mkdir(parents=True, exist_ok=True)
        unique_name = f"{uuid.uuid4().hex[:8]}_{name}"
        file_path = session_dir / unique_name
        file_path.write_bytes(data)

        path_str = str(file_path)

        async with self._session_factory() as sess:
            sess.add(ArtifactRecord(
                session_id=session_id,
                artifact_type=artifact_type,
                name=name,
                path=path_str,
                size_bytes=len(data),
            ))
            await sess.commit()

        return path_str

    async def load_artifact(self, path: str) -> bytes | None:
        file_path = Path(path)
        if not file_path.exists():
            return None
        return file_path.read_bytes()
```

- [ ] **Step 4: Run tests, commit**

```bash
uv run pytest tests/providers/test_sqlite_backend.py -v
git add agentlabx/providers/storage/ tests/providers/test_sqlite_backend.py
git commit -m "feat(providers): add SQLite storage backend with session-scoped namespacing"
```

---

### Task 5: ArXiv Search Tool

**Files:**
- Create: `agentlabx/tools/arxiv_search.py`
- Create: `tests/tools/test_arxiv_search.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/tools/test_arxiv_search.py
from __future__ import annotations
from unittest.mock import MagicMock, patch
import pytest
from agentlabx.tools.arxiv_search import ArxivSearch


class TestArxivSearch:
    async def test_search_returns_results(self):
        tool = ArxivSearch()
        mock_result = MagicMock()
        mock_result.title = "Chain of Thought Prompting"
        mock_result.summary = "A paper about CoT prompting."
        mock_result.entry_id = "http://arxiv.org/abs/2201.11903v1"
        mock_result.get_short_id.return_value = "2201.11903"
        mock_result.authors = [MagicMock(name="Wei et al.")]
        mock_result.published = MagicMock()
        mock_result.published.isoformat.return_value = "2022-01-28"

        with patch("agentlabx.tools.arxiv_search.arxiv.Client") as MockClient:
            MockClient.return_value.results.return_value = iter([mock_result])
            result = await tool.execute(query="chain of thought", max_results=1)

        assert result.success is True
        assert len(result.data["papers"]) == 1
        assert result.data["papers"][0]["arxiv_id"] == "2201.11903"

    async def test_empty_results(self):
        tool = ArxivSearch()
        with patch("agentlabx.tools.arxiv_search.arxiv.Client") as MockClient:
            MockClient.return_value.results.return_value = iter([])
            result = await tool.execute(query="nonexistent", max_results=5)
        assert result.success is True
        assert result.data["papers"] == []

    def test_schema(self):
        tool = ArxivSearch()
        schema = tool.get_schema()
        assert schema["name"] == "arxiv_search"
        assert "query" in schema["parameters"]["properties"]
```

- [ ] **Step 2: Implement arxiv_search.py**

```python
# agentlabx/tools/arxiv_search.py
"""ArXiv paper search tool."""

from __future__ import annotations

import asyncio
from typing import Any

import arxiv
from pydantic import BaseModel

from agentlabx.tools.base import BaseTool, ToolResult


class ArxivSearchConfig(BaseModel):
    query: str
    max_results: int = 5


class ArxivSearch(BaseTool):
    """Search arXiv for papers matching a query."""

    name = "arxiv_search"
    description = "Search arXiv for academic papers by keyword. Returns titles, abstracts, authors, and arxiv IDs."
    config_schema = ArxivSearchConfig

    async def execute(self, **kwargs: Any) -> ToolResult:
        query = kwargs.get("query", "")
        max_results = kwargs.get("max_results", 5)

        if not query:
            return ToolResult(success=False, error="query is required")

        try:
            papers = await asyncio.to_thread(self._search_sync, query, max_results)
            return ToolResult(success=True, data={"papers": papers, "count": len(papers)})
        except Exception as e:
            return ToolResult(success=False, error=f"arXiv search failed: {e}")

    def _search_sync(self, query: str, max_results: int) -> list[dict[str, Any]]:
        client = arxiv.Client()
        search = arxiv.Search(
            query=query,
            max_results=max_results,
            sort_by=arxiv.SortCriterion.Relevance,
        )
        papers: list[dict[str, Any]] = []
        for result in client.results(search):
            papers.append({
                "arxiv_id": result.get_short_id(),
                "title": result.title,
                "abstract": result.summary,
                "authors": [str(a) for a in result.authors],
                "published": result.published.isoformat() if result.published else None,
                "url": result.entry_id,
            })
        return papers
```

- [ ] **Step 3: Run tests, commit**

```bash
uv run pytest tests/tools/test_arxiv_search.py -v
git add agentlabx/tools/arxiv_search.py tests/tools/test_arxiv_search.py
git commit -m "feat(tools): add ArXiv paper search tool"
```

---

### Task 6: HuggingFace Dataset Search Tool

**Files:**
- Create: `agentlabx/tools/hf_dataset_search.py`
- Create: `tests/tools/test_hf_dataset_search.py`

- [ ] **Step 1: Write tests** with mock (same pattern as ArxivSearch — mock `huggingface_hub.list_datasets`).

- [ ] **Step 2: Implement tool**

```python
# agentlabx/tools/hf_dataset_search.py
"""HuggingFace dataset search tool."""

from __future__ import annotations

import asyncio
from typing import Any

from huggingface_hub import list_datasets
from pydantic import BaseModel

from agentlabx.tools.base import BaseTool, ToolResult


class HFDatasetSearchConfig(BaseModel):
    query: str
    max_results: int = 5


class HFDatasetSearch(BaseTool):
    name = "hf_dataset_search"
    description = "Search HuggingFace datasets by name or description. Returns dataset IDs, descriptions, and download counts."
    config_schema = HFDatasetSearchConfig

    async def execute(self, **kwargs: Any) -> ToolResult:
        query = kwargs.get("query", "")
        max_results = kwargs.get("max_results", 5)
        if not query:
            return ToolResult(success=False, error="query is required")

        try:
            datasets = await asyncio.to_thread(self._search_sync, query, max_results)
            return ToolResult(success=True, data={"datasets": datasets, "count": len(datasets)})
        except Exception as e:
            return ToolResult(success=False, error=f"HuggingFace search failed: {e}")

    def _search_sync(self, query: str, max_results: int) -> list[dict[str, Any]]:
        results = []
        for ds in list_datasets(search=query, limit=max_results):
            results.append({
                "id": ds.id,
                "description": getattr(ds, "description", "") or "",
                "downloads": getattr(ds, "downloads", 0),
                "likes": getattr(ds, "likes", 0),
                "tags": list(getattr(ds, "tags", []) or []),
            })
        return results
```

Commit: `feat(tools): add HuggingFace dataset search tool`

---

### Task 7: Semantic Scholar, GitHub, Session Artifact Search Tools

**Files:**
- Create: `agentlabx/tools/semantic_scholar.py` + tests
- Create: `agentlabx/tools/github_search.py` + tests
- Create: `agentlabx/tools/session_artifact_search.py` + tests

Each follows the same pattern: `BaseTool` subclass with `execute()` async method, mock-tested.

**semantic_scholar.py** — uses `semanticscholar` package to search papers by query. Returns papers with title, abstract, citations count, authors.

**github_search.py** — uses `PyGithub` library for code search. Has two methods: `search_repos(query, max_results)` and `clone_repo(repo_name, dest_path)`. Requires `GITHUB_TOKEN` env var.

**session_artifact_search.py** — takes a storage backend, lists artifacts across sessions for the current user, filters by name/type match. Used for "elder student's code" cross-session reuse.

Each tool:
- Defines a Pydantic `{Tool}Config` schema
- Has name, description, config_schema class attrs
- Implements `async def execute(**kwargs) -> ToolResult`
- Uses `asyncio.to_thread` for synchronous library calls

Tests mock the underlying library calls and verify ToolResult shape.

Commits:
- `feat(tools): add Semantic Scholar citation search tool`
- `feat(tools): add GitHub search and clone tool`
- `feat(tools): add session artifact search for cross-session code reuse`

---

### Task 8: Code Executor and LaTeX Compiler Tools

**Files:**
- Create: `agentlabx/tools/code_executor.py` + tests
- Create: `agentlabx/tools/latex_compiler.py` + tests

**code_executor.py** — A tool wrapper around `BaseExecutionBackend`. The tool receives an execution backend via dependency injection and exposes it as a tool agents can invoke. Captures reproducibility metadata on each call.

```python
# agentlabx/tools/code_executor.py
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
    description = "Execute Python code in an isolated workspace. Returns stdout, stderr, exit_code, and reproducibility metadata."
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
                    code=code, workspace=workspace, seed=seed,
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
```

**latex_compiler.py** — Compiles LaTeX source to PDF using `pdflatex` subprocess. Returns PDF bytes on success.

```python
# agentlabx/tools/latex_compiler.py
from __future__ import annotations
import asyncio
import shutil
from pathlib import Path
from typing import Any
from pydantic import BaseModel
from agentlabx.tools.base import BaseTool, ToolResult


class LaTeXCompilerConfig(BaseModel):
    latex_source: str
    output_name: str = "output"


class LaTeXCompiler(BaseTool):
    name = "latex_compiler"
    description = "Compile LaTeX source code to a PDF file."
    config_schema = LaTeXCompilerConfig

    async def execute(self, **kwargs: Any) -> ToolResult:
        latex = kwargs.get("latex_source", "")
        output_name = kwargs.get("output_name", "output")

        if not shutil.which("pdflatex"):
            return ToolResult(success=False, error="pdflatex not installed on system")

        import tempfile
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir)
            tex_file = tmp_path / f"{output_name}.tex"
            tex_file.write_text(latex)

            proc = await asyncio.create_subprocess_exec(
                "pdflatex", "-interaction=nonstopmode", "-output-directory", str(tmp_path),
                str(tex_file),
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            try:
                stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=60)
            except asyncio.TimeoutError:
                proc.kill()
                return ToolResult(success=False, error="pdflatex timeout")

            pdf_file = tmp_path / f"{output_name}.pdf"
            if proc.returncode != 0 or not pdf_file.exists():
                return ToolResult(
                    success=False,
                    error=f"pdflatex failed: {stderr.decode('utf-8', errors='replace')[:500]}",
                )

            pdf_bytes = pdf_file.read_bytes()
            return ToolResult(
                success=True,
                data={"pdf_bytes": pdf_bytes, "size": len(pdf_bytes)},
            )
```

Tests mock subprocess calls for LaTeX, use real SubprocessBackend for code executor.

Commits:
- `feat(tools): add code executor tool using execution backend with reproducibility`
- `feat(tools): add LaTeX compiler tool for report generation`

---

### Task 9: Code Agent Adapters (Claude Code + Builtin Fallback)

**Files:**
- Create: `agentlabx/providers/code_agent/builtin_agent.py` + tests
- Create: `agentlabx/providers/code_agent/claude_code_agent.py` + tests

**builtin_agent.py** — Simple fallback that uses `BaseLLMProvider` to generate code directly. Prompts the LLM to generate/edit/debug code and writes files.

```python
# agentlabx/providers/code_agent/builtin_agent.py
from __future__ import annotations
from pathlib import Path
from agentlabx.providers.code_agent.base import BaseCodeAgent, CodeContext, CodeResult
from agentlabx.providers.llm.base import BaseLLMProvider


class BuiltinCodeAgent(BaseCodeAgent):
    """Fallback code agent using direct LLM calls. No external tool required."""

    name = "builtin"
    supports_streaming = False

    def __init__(self, llm_provider: BaseLLMProvider, model: str = "claude-sonnet-4-6") -> None:
        self.llm_provider = llm_provider
        self.model = model

    async def generate(self, task: str, context: CodeContext, workspace: Path) -> CodeResult:
        prompt = self._build_prompt("generate", task, context)
        response = await self.llm_provider.query(
            model=self.model, prompt=prompt,
            system_prompt="You are a code generation assistant. Output only Python code inside ```python blocks.",
        )
        code = self._extract_code(response.content)
        filename = "generated.py"
        file_path = workspace / filename
        workspace.mkdir(parents=True, exist_ok=True)
        file_path.write_text(code)
        return CodeResult(
            success=True, files=[str(file_path)],
            explanation=response.content,
        )

    async def edit(self, instruction: str, files: list[Path], context: CodeContext) -> CodeResult:
        file_contents = {str(f): f.read_text() for f in files if f.exists()}
        prompt = self._build_edit_prompt(instruction, file_contents, context)
        response = await self.llm_provider.query(
            model=self.model, prompt=prompt,
            system_prompt="You edit Python files. Output each edited file in ```python:filename.py blocks.",
        )
        edited = self._parse_multi_file(response.content)
        for filename, content in edited.items():
            Path(filename).write_text(content)
        return CodeResult(
            success=True, files=list(edited.keys()),
            explanation=response.content,
        )

    async def debug(self, error: str, files: list[Path], execution_log: str) -> CodeResult:
        file_contents = {str(f): f.read_text() for f in files if f.exists()}
        prompt = f"The following code produced an error:\n\nError: {error}\n\nExecution log:\n{execution_log}\n\nFiles:\n"
        for f, c in file_contents.items():
            prompt += f"\n```python:{f}\n{c}\n```\n"
        prompt += "\nFix the code. Output each file in ```python:filename.py blocks."
        response = await self.llm_provider.query(
            model=self.model, prompt=prompt,
            system_prompt="You debug Python code.",
        )
        edited = self._parse_multi_file(response.content)
        for filename, content in edited.items():
            Path(filename).write_text(content)
        return CodeResult(
            success=True, files=list(edited.keys()),
            explanation=response.content,
        )

    def _build_prompt(self, action: str, task: str, context: CodeContext) -> str:
        parts = [f"Task: {task}", f"\nDescription: {context.task_description}"]
        if context.references:
            parts.append(f"\nReferences:\n" + "\n".join(f"- {r}" for r in context.references))
        if context.imports:
            parts.append(f"\nImports needed:\n" + "\n".join(f"- {i}" for i in context.imports))
        return "\n".join(parts)

    def _build_edit_prompt(self, instruction: str, files: dict[str, str], context: CodeContext) -> str:
        parts = [f"Edit instruction: {instruction}\n\nFiles:"]
        for f, c in files.items():
            parts.append(f"\n```python:{f}\n{c}\n```")
        return "\n".join(parts)

    def _extract_code(self, text: str) -> str:
        import re
        match = re.search(r"```(?:python)?\n(.*?)```", text, re.DOTALL)
        return match.group(1) if match else text

    def _parse_multi_file(self, text: str) -> dict[str, str]:
        import re
        result = {}
        for match in re.finditer(r"```python:([^\n]+)\n(.*?)```", text, re.DOTALL):
            filename = match.group(1).strip()
            content = match.group(2)
            result[filename] = content
        return result
```

**claude_code_agent.py** — Placeholder adapter that checks for Claude Code SDK availability and delegates. For MVP, falls back to BuiltinCodeAgent if the SDK isn't available.

```python
# agentlabx/providers/code_agent/claude_code_agent.py
from __future__ import annotations
from pathlib import Path
from agentlabx.providers.code_agent.base import BaseCodeAgent, CodeContext, CodeResult
from agentlabx.providers.code_agent.builtin_agent import BuiltinCodeAgent
from agentlabx.providers.llm.base import BaseLLMProvider


class ClaudeCodeAgent(BaseCodeAgent):
    """Adapter for Claude Code SDK.

    Falls back to BuiltinCodeAgent if claude_agent_sdk is not installed.
    Plan 4+ will wire up the real SDK once the project validates the approach.
    """

    name = "claude_code"
    supports_streaming = True

    def __init__(self, llm_provider: BaseLLMProvider, model: str = "claude-sonnet-4-6") -> None:
        self._fallback = BuiltinCodeAgent(llm_provider=llm_provider, model=model)
        self._sdk_available = self._check_sdk()

    def _check_sdk(self) -> bool:
        try:
            import claude_agent_sdk  # noqa: F401
            return True
        except ImportError:
            return False

    async def generate(self, task: str, context: CodeContext, workspace: Path) -> CodeResult:
        if self._sdk_available:
            return await self._sdk_generate(task, context, workspace)
        return await self._fallback.generate(task, context, workspace)

    async def edit(self, instruction: str, files: list[Path], context: CodeContext) -> CodeResult:
        if self._sdk_available:
            return await self._sdk_edit(instruction, files, context)
        return await self._fallback.edit(instruction, files, context)

    async def debug(self, error: str, files: list[Path], execution_log: str) -> CodeResult:
        if self._sdk_available:
            return await self._sdk_debug(error, files, execution_log)
        return await self._fallback.debug(error, files, execution_log)

    async def _sdk_generate(self, task: str, context: CodeContext, workspace: Path) -> CodeResult:
        # TODO: Real Claude Code SDK integration (Plan 4+)
        return await self._fallback.generate(task, context, workspace)

    async def _sdk_edit(self, instruction: str, files: list[Path], context: CodeContext) -> CodeResult:
        return await self._fallback.edit(instruction, files, context)

    async def _sdk_debug(self, error: str, files: list[Path], execution_log: str) -> CodeResult:
        return await self._fallback.debug(error, files, execution_log)
```

Tests use MockLLMProvider to verify correct prompts are sent and files are written.

Commits:
- `feat(providers): add BuiltinCodeAgent fallback using LLM provider directly`
- `feat(providers): add ClaudeCodeAgent adapter with fallback to builtin`

---

### Task 10: Wire LLM into ConfigAgent

**Files:**
- Modify: `agentlabx/agents/config_agent.py`
- Create: `tests/agents/test_config_agent_real_llm.py`

- [ ] **Step 1: Add `llm_provider` parameter to ConfigAgent**

The current `ConfigAgent.inference()` uses mock_responses. Upgrade to use real LLM via injected provider, with mock_responses still supported as a testing override.

```python
# agentlabx/agents/config_agent.py (updated)
class ConfigAgent(BaseAgent):
    def __init__(
        self,
        *,
        name: str,
        role: str,
        system_prompt: str,
        tools: list[Any],
        memory_scope: MemoryScope,
        max_history_length: int = 15,
        mock_responses: list[str] | None = None,
        llm_provider: BaseLLMProvider | None = None,
        model: str = "claude-sonnet-4-6",
    ) -> None:
        super().__init__(name=name, role=role, system_prompt=system_prompt, tools=tools, memory_scope=memory_scope)
        self.max_history_length = max_history_length
        self._mock_responses: deque[str] = deque(mock_responses or [])
        self.llm_provider = llm_provider
        self.model = model

    async def inference(self, prompt: str, context: AgentContext) -> str:
        self.conversation_history.append({"role": "user", "content": prompt})

        if self._mock_responses:
            response_text = self._mock_responses.popleft()
        elif self.llm_provider is not None:
            response = await self.llm_provider.query(
                model=self.model,
                prompt=prompt,
                system_prompt=self.system_prompt,
                temperature=0.0,
            )
            response_text = response.content
        else:
            response_text = f"[{self.name}] Stub (no LLM provider and no mock): {prompt[:50]}"

        self.conversation_history.append({"role": "assistant", "content": response_text})
        self._truncate_history()
        return response_text
```

- [ ] **Step 2: Write tests** that verify:
  - When `llm_provider` is passed and no mocks, LLM provider is called
  - System prompt from config is passed to provider
  - Mock responses still take priority when provided

- [ ] **Step 3: Update existing ConfigAgent tests** to ensure they still pass (no regressions)

Commit: `feat(agents): wire LLM provider into ConfigAgent — real inference alongside mock support`

---

### Task 11: Wire LLM into PIAgent

**Files:**
- Modify: `agentlabx/agents/pi_agent.py`
- Create: `tests/agents/test_pi_agent_real_llm.py`

- [ ] **Step 1: Upgrade PIAgent to use LLM for confidence + judgment**

```python
# agentlabx/agents/pi_agent.py (updated)
from __future__ import annotations
import json
import re
from typing import Any
from pydantic import BaseModel
from agentlabx.agents.context import ContextAssembler
from agentlabx.agents.base import MemoryScope
from agentlabx.core.session import SessionPreferences
from agentlabx.core.state import PipelineState
from agentlabx.providers.llm.base import BaseLLMProvider
from agentlabx.stages.transition import TransitionHandler


class PIDecision(BaseModel):
    next_stage: str | None
    action: str
    reason: str
    confidence: float
    budget_note: str | None = None
    used_fallback: bool = False


PI_DECISION_PROMPT = """You are the Principal Investigator directing this research project. Your job is to decide what the lab should do next.

Current research state:
{context}

The rule-based handler suggests: transition to '{rule_next_stage}' (action: {rule_action}, reason: {rule_reason}).

Evaluate this decision. Consider:
1. Are the research goals being met?
2. Is the rule-based suggestion appropriate given what we've accomplished?
3. What is the confidence in this decision (0.0-1.0)?

{budget_note}

Respond with JSON (no markdown):
{{"agree_with_rule": true/false, "next_stage": "stage_name" or null, "confidence": 0.0-1.0, "reasoning": "your analysis"}}
"""


class PIAgent:
    def __init__(
        self,
        transition_handler: TransitionHandler,
        confidence_threshold: float = 0.6,
        llm_provider: BaseLLMProvider | None = None,
        model: str = "claude-sonnet-4-6",
    ) -> None:
        self.transition_handler = transition_handler
        self.confidence_threshold = confidence_threshold
        self.llm_provider = llm_provider
        self.model = model
        self.decision_history: list[PIDecision] = []
        self._context_assembler = ContextAssembler()
        self._memory_scope = MemoryScope(
            read=["hypotheses.*", "transition_log.*", "review_feedback.*", "cost_tracker.*", "stage_iterations.*", "errors.*"],
            summarize={
                "literature_review": "abstract",
                "plan": "goals and methodology summary",
                "experiment_results": "metrics and outcomes",
                "interpretation": "key findings",
                "report": "abstract and conclusion",
            },
        )

    async def decide(
        self,
        state: PipelineState,
        preferences: SessionPreferences,
        budget_warning: bool = False,
    ) -> PIDecision:
        rule_decision = self.transition_handler.decide(state)

        # No LLM → mock/fallback path (same as Plan 2)
        if self.llm_provider is None:
            decision = PIDecision(
                next_stage=rule_decision.next_stage,
                action=rule_decision.action,
                reason=rule_decision.reason,
                confidence=0.85,
                budget_note="Budget warning active" if budget_warning else None,
                used_fallback=False,
            )
            self.decision_history.append(decision)
            return decision

        # Real LLM path
        context = self._context_assembler.assemble(state, self._memory_scope)
        context_text = self._context_assembler.format_for_prompt(context)

        budget_note_prompt = (
            "Budget is tight (>70% spent). Bias toward completing rather than iterating."
            if budget_warning else ""
        )
        prompt = PI_DECISION_PROMPT.format(
            context=context_text,
            rule_next_stage=rule_decision.next_stage or "END",
            rule_action=rule_decision.action,
            rule_reason=rule_decision.reason,
            budget_note=budget_note_prompt,
        )

        try:
            response = await self.llm_provider.query(
                model=self.model, prompt=prompt,
                system_prompt="You are a research director. Respond with valid JSON only.",
                temperature=0.1,
            )
            parsed = self._parse_decision(response.content)
            confidence = float(parsed.get("confidence", 0.5))

            used_fallback = confidence < self.confidence_threshold
            if used_fallback or parsed.get("agree_with_rule", True):
                next_stage = rule_decision.next_stage
                action = rule_decision.action
                reason = rule_decision.reason
            else:
                next_stage = parsed.get("next_stage")
                action = "pi_override"
                reason = parsed.get("reasoning", "PI disagreed with rule-based suggestion")
        except Exception as e:
            # Any LLM error → fall back to rule decision
            next_stage = rule_decision.next_stage
            action = rule_decision.action
            reason = f"Rule fallback (LLM error: {e})"
            confidence = 0.0
            used_fallback = True

        decision = PIDecision(
            next_stage=next_stage,
            action=action,
            reason=reason,
            confidence=confidence,
            budget_note="Budget warning active" if budget_warning else None,
            used_fallback=used_fallback,
        )
        self.decision_history.append(decision)
        return decision

    def _parse_decision(self, text: str) -> dict[str, Any]:
        # Extract JSON from response (handle markdown wrapping)
        match = re.search(r"\{.*\}", text, re.DOTALL)
        if match:
            return json.loads(match.group(0))
        return {}
```

- [ ] **Step 2: Write tests** using MockLLMProvider:
  - Test high-confidence LLM agrees with rule → returns rule decision
  - Test LLM disagrees with high confidence → returns PI override
  - Test low-confidence LLM → falls back to rule with `used_fallback=True`
  - Test LLM error → falls back to rule
  - Test budget warning includes note in prompt
  - Test existing Plan 2 tests (no LLM) still pass

Commit: `feat(agents): wire LLM into PIAgent — real confidence judgment with rule-based fallback`

---

### Task 12: Real Literature Review Stage

**Files:**
- Replace: `agentlabx/stages/literature_review.py` (moves from skeleton to real implementation)
- Create: `tests/stages/test_literature_review_real.py`

- [ ] **Step 1: Design the real lit review loop**

Real literature review involves:
1. PhD student generates search queries based on research topic
2. PhD student calls `arxiv_search` + `semantic_scholar` tools
3. PhD student reads results, selects relevant papers
4. Loops: refine queries based on what's found (max 3 iterations)
5. Produces `LitReviewResult` with papers + synthesized summary

- [ ] **Step 2: Implement**

```python
# agentlabx/stages/literature_review.py
from __future__ import annotations
from agentlabx.agents.context import ContextAssembler
from agentlabx.core.state import LitReviewResult, PipelineState
from agentlabx.stages.base import BaseStage, StageContext, StageResult


class LiteratureReviewStage(BaseStage):
    name = "literature_review"
    description = "Search and review academic literature. PhD student iteratively searches and synthesizes."
    required_agents = ["phd_student"]
    required_tools = ["arxiv_search", "semantic_scholar"]

    async def run(self, state: PipelineState, context: StageContext) -> StageResult:
        registry = context.registry
        if registry is None:
            return StageResult(output={}, status="backtrack", reason="No registry in context", next_hint=None)

        phd_agent = self._resolve_agent(registry, "phd_student")
        arxiv_tool = self._resolve_tool(registry, "arxiv_search")
        scholar_tool = self._resolve_tool(registry, "semantic_scholar")

        topic = state["research_topic"]
        papers: list[dict] = []
        max_iterations = 3

        for iteration in range(max_iterations):
            # PhD generates search query
            query_prompt = self._build_query_prompt(topic, papers, iteration)
            ctx = self._agent_context(state, phd_agent)
            query_response = await phd_agent.inference(query_prompt, ctx)
            search_query = self._extract_query(query_response)

            # Execute searches
            arxiv_result = await arxiv_tool.execute(query=search_query, max_results=5)
            if arxiv_result.success:
                papers.extend(arxiv_result.data["papers"])

            # Check if enough papers found
            if len(papers) >= 5:
                break

        # Synthesize summary
        summary_prompt = self._build_summary_prompt(topic, papers)
        summary_ctx = self._agent_context(state, phd_agent)
        summary = await phd_agent.inference(summary_prompt, summary_ctx)

        result = LitReviewResult(papers=papers[:10], summary=summary)
        return StageResult(
            output={"literature_review": [result]},
            status="done",
            reason=f"Reviewed {len(papers)} papers over {iteration + 1} iterations",
        )

    def _resolve_agent(self, registry, name):
        from agentlabx.core.registry import PluginType
        from agentlabx.agents.config_agent import ConfigAgent
        from agentlabx.agents.config_loader import AgentConfig
        entry = registry.resolve(PluginType.AGENT, name)
        if isinstance(entry, AgentConfig):
            return ConfigAgent.from_config(entry)
        return entry()  # class → instance

    def _resolve_tool(self, registry, name):
        from agentlabx.core.registry import PluginType
        entry = registry.resolve(PluginType.TOOL, name)
        return entry() if isinstance(entry, type) else entry

    def _agent_context(self, state, agent):
        from agentlabx.agents.base import AgentContext
        assembler = ContextAssembler()
        filtered = assembler.assemble(state, agent.memory_scope)
        return AgentContext(phase="literature_review", state=filtered, working_memory=agent.working_memory)

    def _build_query_prompt(self, topic: str, existing_papers: list, iteration: int) -> str:
        existing_summary = "\n".join(f"- {p['title']}" for p in existing_papers[:5])
        return (
            f"Research topic: {topic}\n\n"
            f"Papers found so far (iteration {iteration + 1}):\n{existing_summary or 'None'}\n\n"
            f"Generate a concise search query (3-8 words) to find more relevant papers. "
            f"Output only the query, no explanation."
        )

    def _build_summary_prompt(self, topic: str, papers: list) -> str:
        papers_text = "\n\n".join(
            f"Title: {p['title']}\nAbstract: {p.get('abstract', '')[:300]}"
            for p in papers[:10]
        )
        return (
            f"Topic: {topic}\n\n"
            f"Papers:\n{papers_text}\n\n"
            f"Write a 200-word literature review synthesizing these papers, "
            f"identifying key themes, gaps, and relevance to the research topic."
        )

    def _extract_query(self, response: str) -> str:
        return response.strip().split("\n")[0].strip()
```

- [ ] **Step 3: Update stages/skeleton.py `register_default_stages()`**

Remove `LiteratureReviewStage` from skeleton.py and import it from `literature_review.py`. Register both real and skeleton names (real takes precedence if both available).

- [ ] **Step 4: Write tests** using MockLLMProvider + mock tools:
  - test_runs_with_mock_providers — full flow with scripted LLM responses
  - test_generates_search_queries — verifies PhD is prompted for queries
  - test_synthesizes_summary — final LitReviewResult has non-empty summary

Commit: `feat(stages): add real literature review stage with iterative search and synthesis`

---

### Task 13: Real Plan Formulation Stage

**Files:**
- Create: `agentlabx/stages/plan_formulation.py` (real implementation)
- Create: `tests/stages/test_plan_formulation_real.py`

- [ ] **Step 1: Implement postdoc+phd dialogue**

```python
# agentlabx/stages/plan_formulation.py
from __future__ import annotations
from agentlabx.agents.context import ContextAssembler
from agentlabx.agents.base import AgentContext
from agentlabx.core.state import Hypothesis, PipelineState, ResearchPlan
from agentlabx.stages.base import BaseStage, StageContext, StageResult


class PlanFormulationStage(BaseStage):
    name = "plan_formulation"
    description = "Postdoc and PhD student collaborate to design the research plan."
    required_agents = ["postdoc", "phd_student"]
    required_tools = []

    async def run(self, state: PipelineState, context: StageContext) -> StageResult:
        from agentlabx.stages.literature_review import LiteratureReviewStage  # reuse helpers
        helper = LiteratureReviewStage()
        registry = context.registry

        postdoc = helper._resolve_agent(registry, "postdoc")
        phd = helper._resolve_agent(registry, "phd_student")

        topic = state["research_topic"]
        lit_review = state.get("literature_review", [])
        lit_summary = lit_review[-1].summary if lit_review else "No literature review available."

        # Postdoc proposes initial plan
        postdoc_prompt = (
            f"Research topic: {topic}\n\n"
            f"Literature review summary:\n{lit_summary}\n\n"
            f"Propose an initial research plan with:\n"
            f"1. Three goals\n"
            f"2. Methodology (2-3 sentences)\n"
            f"3. 1-2 testable hypotheses\n\n"
            f"Format:\nGOALS: ...\nMETHODOLOGY: ...\nHYPOTHESES: ..."
        )
        postdoc_ctx = helper._agent_context(state, postdoc)
        initial_plan = await postdoc.inference(postdoc_prompt, postdoc_ctx)

        # PhD reviews and provides feedback
        phd_prompt = (
            f"Topic: {topic}\n\nPostdoc's proposed plan:\n{initial_plan}\n\n"
            f"As the PhD student, provide 1-2 constructive suggestions "
            f"to improve the plan. Be concise."
        )
        phd_ctx = helper._agent_context(state, phd)
        phd_feedback = await phd.inference(phd_prompt, phd_ctx)

        # Postdoc finalizes
        finalize_prompt = (
            f"Initial plan:\n{initial_plan}\n\n"
            f"PhD feedback:\n{phd_feedback}\n\n"
            f"Incorporate the feedback and output the final plan in the same format: GOALS / METHODOLOGY / HYPOTHESES."
        )
        final_plan_text = await postdoc.inference(finalize_prompt, postdoc_ctx)

        # Parse
        goals, methodology, hypotheses = self._parse_plan(final_plan_text)
        plan = ResearchPlan(
            goals=goals, methodology=methodology, hypotheses=hypotheses,
            full_text=final_plan_text,
        )

        # Convert hypothesis statements to Hypothesis objects
        hypothesis_objects = [
            Hypothesis(
                id=f"H{i + 1}",
                statement=h,
                status="active",
                created_at_stage="plan_formulation",
            )
            for i, h in enumerate(hypotheses)
        ]

        return StageResult(
            output={"plan": [plan], "hypotheses": hypothesis_objects},
            status="done",
            reason="Plan formulated with postdoc-PhD collaboration",
        )

    def _parse_plan(self, text: str) -> tuple[list[str], str, list[str]]:
        import re
        goals_m = re.search(r"GOALS:?\s*(.+?)(?=METHODOLOGY:|$)", text, re.DOTALL | re.IGNORECASE)
        method_m = re.search(r"METHODOLOGY:?\s*(.+?)(?=HYPOTHESES:|$)", text, re.DOTALL | re.IGNORECASE)
        hyp_m = re.search(r"HYPOTHESES:?\s*(.+?)$", text, re.DOTALL | re.IGNORECASE)

        goals_text = goals_m.group(1).strip() if goals_m else ""
        goals = [g.strip("- ").strip() for g in goals_text.split("\n") if g.strip() and g.strip().startswith("-")]
        if not goals and goals_text:
            goals = [goals_text.split(".")[0].strip()]

        methodology = method_m.group(1).strip() if method_m else ""
        hyp_text = hyp_m.group(1).strip() if hyp_m else ""
        hypotheses = [h.strip("- ").strip() for h in hyp_text.split("\n") if h.strip() and h.strip().startswith("-")]
        if not hypotheses and hyp_text:
            hypotheses = [hyp_text.split(".")[0].strip()]

        return goals or ["Goal from plan"], methodology or "Methodology from plan", hypotheses or ["Hypothesis from plan"]
```

- [ ] **Step 2: Update registry** to use real `PlanFormulationStage` instead of skeleton

- [ ] **Step 3: Write tests** with scripted LLM responses for postdoc and PhD

Commit: `feat(stages): add real plan formulation stage with postdoc-PhD dialogue and hypothesis extraction`

---

### Task 14: Real Peer Review Stage (Blind Review)

**Files:**
- Create: `agentlabx/stages/peer_review.py` (real blind review)
- Create: `tests/stages/test_peer_review_real.py`

- [ ] **Step 1: Implement blind review**

The key feature: reviewer sees ONLY the final report, not internal state. Uses `MemoryScope(read=["report"])`. Optionally uses a different LLM model for bias reduction.

```python
# agentlabx/stages/peer_review.py
from __future__ import annotations
from agentlabx.agents.base import AgentContext, MemoryScope
from agentlabx.agents.config_agent import ConfigAgent
from agentlabx.agents.context import ContextAssembler
from agentlabx.core.state import PipelineState, ReviewResult
from agentlabx.stages.base import BaseStage, StageContext, StageResult


class PeerReviewStage(BaseStage):
    name = "peer_review"
    description = "Blind peer review — reviewers see only the final report."
    required_agents = ["reviewers"]
    required_tools = []

    NUM_REVIEWERS = 3

    async def run(self, state: PipelineState, context: StageContext) -> StageResult:
        from agentlabx.stages.literature_review import LiteratureReviewStage
        helper = LiteratureReviewStage()
        registry = context.registry

        reviewer_template = helper._resolve_agent(registry, "reviewers")

        report = state.get("report", [])
        if not report:
            return StageResult(
                output={}, status="backtrack", next_hint="report_writing",
                reason="No report to review",
            )
        latest_report = report[-1]

        # Strict blind scope
        blind_scope = MemoryScope(read=["report"])
        assembler = ContextAssembler()

        reviews: list[ReviewResult] = []
        for i in range(self.NUM_REVIEWERS):
            # Create a fresh reviewer instance (no shared history)
            if isinstance(reviewer_template, ConfigAgent):
                # Create fresh instance, using the template's LLM provider
                reviewer = ConfigAgent(
                    name=f"reviewer_{i + 1}",
                    role=reviewer_template.role,
                    system_prompt=reviewer_template.system_prompt,
                    tools=[],
                    memory_scope=blind_scope,  # Enforce blind review
                    max_history_length=reviewer_template.max_history_length,
                    llm_provider=reviewer_template.llm_provider,
                    model=reviewer_template.model,
                )
            else:
                reviewer = reviewer_template

            # Assemble context with blind scope (only report visible)
            blind_context = assembler.assemble(state, blind_scope)
            ctx = AgentContext(
                phase="peer_review",
                state=blind_context,
                working_memory={},
            )

            review_prompt = self._build_review_prompt(latest_report, i)
            review_text = await reviewer.inference(review_prompt, ctx)

            review = self._parse_review(review_text, f"reviewer_{i + 1}")
            reviews.append(review)

        # Overall decision: majority vote
        decisions = [r.decision for r in reviews]
        if decisions.count("accept") >= 2:
            overall = "accept"
        elif decisions.count("reject") >= 2:
            overall = "reject"
        else:
            overall = "revise"

        return StageResult(
            output={"review": reviews, "review_feedback": reviews},
            status="done" if overall == "accept" else "backtrack",
            next_hint=None if overall == "accept" else "report_writing",
            reason=f"Peer review complete: {overall} ({decisions})",
            feedback=None if overall == "accept" else "\n\n".join(r.feedback for r in reviews),
        )

    def _build_review_prompt(self, report, reviewer_idx: int) -> str:
        focus = ["experimental rigor", "impact and significance", "novelty and originality"][reviewer_idx]
        return (
            f"You are an anonymous reviewer focused on {focus}.\n\n"
            f"Paper to review:\n{report.latex_source[:5000]}\n\n"
            f"Provide:\n"
            f"- DECISION: accept / revise / reject\n"
            f"- SCORES (1-4): originality, quality, clarity, significance\n"
            f"- OVERALL (1-10)\n"
            f"- FEEDBACK: 2-3 sentences\n\n"
            f"Format:\nDECISION: ...\nSCORES: originality=X quality=X clarity=X significance=X\nOVERALL: X\nFEEDBACK: ..."
        )

    def _parse_review(self, text: str, reviewer_id: str) -> ReviewResult:
        import re
        decision_m = re.search(r"DECISION:\s*(\w+)", text, re.IGNORECASE)
        decision = (decision_m.group(1).lower() if decision_m else "revise")
        if decision not in ("accept", "revise", "reject"):
            decision = "revise"

        scores = {}
        for metric in ["originality", "quality", "clarity", "significance"]:
            m = re.search(rf"{metric}\s*=\s*(\d+)", text, re.IGNORECASE)
            scores[metric] = float(m.group(1)) if m else 2.0

        overall_m = re.search(r"OVERALL:\s*(\d+)", text, re.IGNORECASE)
        scores["overall"] = float(overall_m.group(1)) if overall_m else 5.0

        feedback_m = re.search(r"FEEDBACK:\s*(.+)", text, re.DOTALL | re.IGNORECASE)
        feedback = feedback_m.group(1).strip() if feedback_m else text

        return ReviewResult(
            decision=decision,
            scores=scores,
            feedback=feedback,
            reviewer_id=reviewer_id,
        )
```

- [ ] **Step 2: Write tests** with scripted LLM responses:
  - test_three_reviewers_run — verifies 3 reviews produced
  - test_majority_accept — all accept → status=done
  - test_majority_reject → status=backtrack, next_hint=report_writing
  - test_reviewer_only_sees_report — verify blind scope enforced

Commit: `feat(stages): add real blind peer review with 3 reviewers and majority decision`

---

### Task 15: Final Integration + Lint + Test

- [ ] **Step 1: Update `stages/skeleton.py` `register_default_stages()`**

Make it smart — register real stages when available, fall back to skeletons otherwise. Or create a separate `register_all_stages()` that registers real where available.

- [ ] **Step 2: Run full suite + lint**

```bash
cd d:/GitHub/AgentLabX
uv run ruff check agentlabx/ tests/
uv run ruff format agentlabx/ tests/
uv run pytest tests/ -v --tb=short
```

Expected: All tests pass, lint clean.

- [ ] **Step 3: Commit final cleanup**

```bash
git add -A
git commit -m "feat(core): Plan 3 complete — all providers, tools, real stages integrated"
```

---

## Summary

After completing all 15 tasks, you will have:

**Providers:**
- **LiteLLMProvider** — real multi-provider LLM inference with retry logic
- **MockLLMProvider** — scripted responses for testing
- **SubprocessBackend** — real code execution with reproducibility capture
- **SQLiteBackend** — async SQLite storage with session-scoped namespacing
- **BuiltinCodeAgent** + **ClaudeCodeAgent** — code generation/editing/debugging

**Tools:**
- ArXiv search
- HuggingFace dataset search
- Semantic Scholar citation search
- GitHub search + clone
- Session artifact search (cross-session reuse)
- Code executor (wraps execution backend)
- LaTeX compiler

**Upgraded agents:**
- **ConfigAgent** — now uses real LLM via injected provider
- **PIAgent** — LLM-powered confidence judgment with rule-based fallback

**Real stage implementations (3 of 8):**
- Literature review (iterative search + synthesis)
- Plan formulation (postdoc-PhD dialogue + hypothesis extraction)
- Peer review (blind, 3 reviewers, majority decision)

**What's deferred to Plan 4 (Server):**
- FastAPI + WebSocket server
- REST endpoints for sessions/pipelines/artifacts
- Real-time event streaming via WebSocket
- Remaining 5 real stage implementations (data_exploration, data_preparation, experimentation, results_interpretation, report_writing) — upgrading these requires the server for live progress monitoring and the code agent for experimentation

**What's deferred to Plan 5 (Frontend):**
- React + Ant Design + Vite UI
- Session management dashboard
- Live pipeline visualization
