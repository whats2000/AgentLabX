from __future__ import annotations

from pathlib import Path
from typing import Any

from agentlabx.providers.code_agent.base import BaseCodeAgent, CodeContext, CodeResult
from agentlabx.providers.execution.base import BaseExecutionBackend, ExecutionResult
from agentlabx.providers.llm.base import BaseLLMProvider, LLMResponse
from agentlabx.providers.storage.base import AgentTurnRecord, BaseStorageBackend


class DummyLLMProvider(BaseLLMProvider):
    async def query(
        self, *, model: str, prompt: str, system_prompt: str = "", temperature: float = 0.0
    ) -> LLMResponse:
        return LLMResponse(
            content="dummy response", tokens_in=10, tokens_out=5, model=model, cost=0.001
        )


class TestBaseLLMProvider:
    async def test_query_returns_response(self):
        provider = DummyLLMProvider()
        resp = await provider.query(model="test", prompt="hello")
        assert resp.content == "dummy response"
        assert resp.tokens_in == 10
        assert resp.cost == 0.001


class DummyExecutionBackend(BaseExecutionBackend):
    async def execute(self, *, code: str, workspace: Path, timeout: int = 120) -> ExecutionResult:
        return ExecutionResult(
            success=True, stdout="output", stderr="", exit_code=0, execution_time=1.5
        )

    async def cleanup(self, workspace: Path) -> None:
        pass


class TestBaseExecutionBackend:
    async def test_execute_returns_result(self):
        backend = DummyExecutionBackend()
        result = await backend.execute(code="print(1)", workspace=Path("/tmp"))
        assert result.success is True
        assert result.stdout == "output"
        assert result.exit_code == 0

    async def test_cleanup_does_not_raise(self):
        backend = DummyExecutionBackend()
        await backend.cleanup(Path("/tmp"))


class DummyStorageBackend(BaseStorageBackend):
    def __init__(self) -> None:
        self._store: dict[str, Any] = {}

    async def save_state(self, session_id: str, stage: str, state: dict[str, Any]) -> None:
        self._store[f"{session_id}/{stage}"] = state

    async def load_state(self, session_id: str, stage: str) -> dict[str, Any] | None:
        return self._store.get(f"{session_id}/{stage}")

    async def save_artifact(
        self, session_id: str, artifact_type: str, name: str, data: bytes
    ) -> str:
        key = f"{session_id}/{artifact_type}/{name}"
        self._store[key] = data
        return key

    async def load_artifact(self, path: str) -> bytes | None:
        return self._store.get(path)

    async def delete_session(self, session_id: str) -> None:
        prefix = f"{session_id}/"
        for key in [k for k in self._store if k.startswith(prefix)]:
            del self._store[key]

    async def append_agent_turn(self, record: AgentTurnRecord) -> int:
        raise NotImplementedError("Implemented in Task A4")

    async def list_agent_turns(self, session_id, *, agent=None, stage=None, after_ts=None, limit=200):
        raise NotImplementedError("Implemented in Task A4")


class TestBaseStorageBackend:
    async def test_save_and_load_state(self):
        backend = DummyStorageBackend()
        await backend.save_state("s1", "lit_review", {"papers": 5})
        state = await backend.load_state("s1", "lit_review")
        assert state == {"papers": 5}

    async def test_load_missing_state(self):
        backend = DummyStorageBackend()
        state = await backend.load_state("nonexistent", "stage")
        assert state is None

    async def test_save_and_load_artifact(self):
        backend = DummyStorageBackend()
        path = await backend.save_artifact("s1", "code", "train.py", b"print(1)")
        data = await backend.load_artifact(path)
        assert data == b"print(1)"


class DummyCodeAgent(BaseCodeAgent):
    name = "dummy"
    supports_streaming = False

    async def generate(self, task: str, context: CodeContext, workspace: Path) -> CodeResult:
        return CodeResult(success=True, files=["train.py"], explanation="Generated training script")

    async def edit(self, instruction: str, files: list[Path], context: CodeContext) -> CodeResult:
        return CodeResult(success=True, files=[str(f) for f in files], explanation="Edited files")

    async def debug(self, error: str, files: list[Path], execution_log: str) -> CodeResult:
        return CodeResult(success=True, files=[str(f) for f in files], explanation="Fixed the bug")


class TestBaseCodeAgent:
    async def test_generate(self):
        agent = DummyCodeAgent()
        ctx = CodeContext(task_description="train a model", references=[], imports=[])
        result = await agent.generate("implement CoT", ctx, Path("/tmp"))
        assert result.success is True
        assert "train.py" in result.files

    async def test_edit(self):
        agent = DummyCodeAgent()
        ctx = CodeContext(task_description="modify", references=[], imports=[])
        result = await agent.edit("add logging", [Path("train.py")], ctx)
        assert result.success is True

    async def test_debug(self):
        agent = DummyCodeAgent()
        result = await agent.debug("IndexError", [Path("train.py")], "traceback...")
        assert result.success is True
