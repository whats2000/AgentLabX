"""Tests for BuiltinCodeAgent — LLM-based fallback code generation."""

from __future__ import annotations

from pathlib import Path

import pytest

from agentlabx.providers.code_agent.base import CodeContext
from agentlabx.providers.code_agent.builtin_agent import BuiltinCodeAgent
from agentlabx.providers.llm.mock_provider import MockLLMProvider


@pytest.fixture
def workspace(tmp_path: Path) -> Path:
    return tmp_path / "workspace"


@pytest.fixture
def code_context() -> CodeContext:
    return CodeContext(
        task_description="Write a hello world function",
        references=["https://docs.python.org"],
        imports=["os", "sys"],
    )


class TestBuiltinCodeAgentGenerate:
    @pytest.mark.asyncio
    async def test_generate_creates_file(self, workspace: Path, code_context: CodeContext):
        mock = MockLLMProvider(responses=['```python\nprint("x")\n```'])
        agent = BuiltinCodeAgent(llm_provider=mock, model="claude-sonnet-4-6")

        result = await agent.generate("write hello world", code_context, workspace)

        assert result.success is True
        assert len(result.files) == 1
        file_path = Path(result.files[0])
        assert file_path.exists()
        assert 'print("x")' in file_path.read_text()

    @pytest.mark.asyncio
    async def test_generate_uses_correct_system_prompt(
        self, workspace: Path, code_context: CodeContext
    ):
        mock = MockLLMProvider(responses=["```python\npass\n```"])
        agent = BuiltinCodeAgent(llm_provider=mock)

        await agent.generate("write a function", code_context, workspace)

        assert len(mock.calls) == 1
        call = mock.calls[0]
        assert "code generation" in call["system_prompt"].lower()
        assert "```python" in call["system_prompt"]

    @pytest.mark.asyncio
    async def test_generate_without_code_block_returns_raw_text(
        self, workspace: Path, code_context: CodeContext
    ):
        raw = "print('hello')"
        mock = MockLLMProvider(responses=[raw])
        agent = BuiltinCodeAgent(llm_provider=mock)

        result = await agent.generate("write hello", code_context, workspace)

        assert result.success is True
        file_path = Path(result.files[0])
        assert file_path.read_text() == raw

    @pytest.mark.asyncio
    async def test_generate_workspace_created(self, workspace: Path, code_context: CodeContext):
        mock = MockLLMProvider(responses=["```python\nx = 1\n```"])
        agent = BuiltinCodeAgent(llm_provider=mock)

        assert not workspace.exists()
        await agent.generate("task", code_context, workspace)
        assert workspace.exists()

    @pytest.mark.asyncio
    async def test_generate_prompt_includes_task_and_description(
        self, workspace: Path, code_context: CodeContext
    ):
        mock = MockLLMProvider(responses=["```python\npass\n```"])
        agent = BuiltinCodeAgent(llm_provider=mock)

        await agent.generate("my specific task", code_context, workspace)

        prompt = mock.calls[0]["prompt"]
        assert "my specific task" in prompt
        assert "Write a hello world function" in prompt


class TestBuiltinCodeAgentEdit:
    @pytest.mark.asyncio
    async def test_edit_parses_multi_file_output(self, tmp_path: Path):
        foo = tmp_path / "foo.py"
        bar = tmp_path / "bar.py"
        foo.write_text("x = 1")
        bar.write_text("y = 2")

        response = f"```python:{foo}\nx = 10\n```\n```python:{bar}\ny = 20\n```"
        mock = MockLLMProvider(responses=[response])
        agent = BuiltinCodeAgent(llm_provider=mock)
        ctx = CodeContext(task_description="edit files", references=[], imports=[])

        result = await agent.edit("multiply by 10", [foo, bar], ctx)

        assert result.success is True
        assert foo.read_text() == "x = 10\n"
        assert bar.read_text() == "y = 20\n"
        assert len(result.files) == 2

    @pytest.mark.asyncio
    async def test_edit_falls_back_to_original_files_when_no_blocks(self, tmp_path: Path):
        foo = tmp_path / "foo.py"
        foo.write_text("pass")

        mock = MockLLMProvider(responses=["No changes needed."])
        agent = BuiltinCodeAgent(llm_provider=mock)
        ctx = CodeContext(task_description="edit", references=[], imports=[])

        result = await agent.edit("no-op", [foo], ctx)

        assert result.success is True
        assert str(foo) in result.files


class TestBuiltinCodeAgentDebug:
    @pytest.mark.asyncio
    async def test_debug_captures_error_in_prompt(self, tmp_path: Path):
        code_file = tmp_path / "buggy.py"
        code_file.write_text("raise ValueError('oops')")

        mock = MockLLMProvider(responses=[f"```python:{code_file}\npass\n```"])
        agent = BuiltinCodeAgent(llm_provider=mock)

        await agent.debug("NameError: x is not defined", [code_file], "Traceback: line 1")

        prompt = mock.calls[0]["prompt"]
        assert "NameError: x is not defined" in prompt

    @pytest.mark.asyncio
    async def test_debug_captures_execution_log_in_prompt(self, tmp_path: Path):
        code_file = tmp_path / "buggy.py"
        code_file.write_text("x = 1")

        mock = MockLLMProvider(responses=[f"```python:{code_file}\nx = 2\n```"])
        agent = BuiltinCodeAgent(llm_provider=mock)

        await agent.debug("SomeError", [code_file], "execution log line A")

        prompt = mock.calls[0]["prompt"]
        assert "execution log line A" in prompt

    @pytest.mark.asyncio
    async def test_debug_writes_fixed_files(self, tmp_path: Path):
        code_file = tmp_path / "buggy.py"
        code_file.write_text("raise ValueError")

        mock = MockLLMProvider(responses=[f"```python:{code_file}\nprint('fixed')\n```"])
        agent = BuiltinCodeAgent(llm_provider=mock)

        result = await agent.debug("ValueError", [code_file], "log")

        assert result.success is True
        assert "print('fixed')" in code_file.read_text()

    @pytest.mark.asyncio
    async def test_debug_falls_back_to_original_files_when_no_blocks(self, tmp_path: Path):
        code_file = tmp_path / "buggy.py"
        code_file.write_text("x = 1")

        mock = MockLLMProvider(responses=["I cannot fix this."])
        agent = BuiltinCodeAgent(llm_provider=mock)

        result = await agent.debug("error", [code_file], "log")

        assert result.success is True
        assert str(code_file) in result.files
