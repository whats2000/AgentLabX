"""Fallback code agent — generates code via direct LLM calls (no external SDK)."""

from __future__ import annotations

import re
from pathlib import Path

from agentlabx.providers.code_agent.base import BaseCodeAgent, CodeContext, CodeResult
from agentlabx.providers.llm.base import BaseLLMProvider


class BuiltinCodeAgent(BaseCodeAgent):
    """Fallback code agent using direct LLM calls. No external tool required."""

    name = "builtin"
    supports_streaming = False

    def __init__(
        self,
        llm_provider: BaseLLMProvider,
        model: str = "claude-sonnet-4-6",
    ) -> None:
        self.llm_provider = llm_provider
        self.model = model

    async def generate(self, task: str, context: CodeContext, workspace: Path) -> CodeResult:
        prompt = self._build_generate_prompt(task, context)
        response = await self.llm_provider.query(
            model=self.model,
            prompt=prompt,
            system_prompt=(
                "You are a code generation assistant. "
                "Output only Python code inside ```python blocks. "
                "Do not include explanation outside the code block."
            ),
        )
        code = self._extract_code(response.content)
        workspace.mkdir(parents=True, exist_ok=True)
        file_path = workspace / "generated.py"
        file_path.write_text(code)
        return CodeResult(
            success=True,
            files=[str(file_path)],
            explanation=response.content,
        )

    async def edit(self, instruction: str, files: list[Path], context: CodeContext) -> CodeResult:
        file_contents = {str(f): f.read_text() for f in files if f.exists()}
        prompt = self._build_edit_prompt(instruction, file_contents, context)
        response = await self.llm_provider.query(
            model=self.model,
            prompt=prompt,
            system_prompt=(
                "You edit Python files. "
                "Output each edited file in ```python:filename.py blocks. "
                "Do not add prose outside the code blocks."
            ),
        )
        edited = self._parse_multi_file(response.content)
        edited_files: list[str] = []
        for filename, content in edited.items():
            file_path = Path(filename)
            file_path.write_text(content)
            edited_files.append(str(file_path))
        return CodeResult(
            success=True,
            files=edited_files or [str(f) for f in files],
            explanation=response.content,
        )

    async def debug(self, error: str, files: list[Path], execution_log: str) -> CodeResult:
        file_contents = {str(f): f.read_text() for f in files if f.exists()}
        prompt_parts = [
            "The following code produced an error:",
            f"\nError: {error}",
            f"\nExecution log:\n{execution_log}",
            "\nFiles:",
        ]
        for f, c in file_contents.items():
            prompt_parts.append(f"\n```python:{f}\n{c}\n```")
        prompt_parts.append(
            "\nFix the code. Output each corrected file in ```python:filename.py blocks."
        )
        prompt = "\n".join(prompt_parts)
        response = await self.llm_provider.query(
            model=self.model,
            prompt=prompt,
            system_prompt="You debug Python code. Output corrected files only.",
        )
        edited = self._parse_multi_file(response.content)
        fixed_files: list[str] = []
        for filename, content in edited.items():
            file_path = Path(filename)
            file_path.write_text(content)
            fixed_files.append(str(file_path))
        return CodeResult(
            success=True,
            files=fixed_files or [str(f) for f in files],
            explanation=response.content,
        )

    def _build_generate_prompt(self, task: str, context: CodeContext) -> str:
        parts = [f"Task: {task}", f"\nDescription: {context.task_description}"]
        if context.references:
            refs = "\n".join(f"- {r}" for r in context.references)
            parts.append(f"\nReferences:\n{refs}")
        if context.imports:
            imps = "\n".join(f"- {i}" for i in context.imports)
            parts.append(f"\nImports needed:\n{imps}")
        return "\n".join(parts)

    def _build_edit_prompt(
        self, instruction: str, files: dict[str, str], context: CodeContext
    ) -> str:
        parts = [f"Edit instruction: {instruction}", "\nFiles:"]
        for f, c in files.items():
            parts.append(f"\n```python:{f}\n{c}\n```")
        return "\n".join(parts)

    def _extract_code(self, text: str) -> str:
        match = re.search(r"```(?:python)?\n(.*?)```", text, re.DOTALL)
        return match.group(1) if match else text

    def _parse_multi_file(self, text: str) -> dict[str, str]:
        result: dict[str, str] = {}
        for match in re.finditer(r"```python:([^\n]+)\n(.*?)```", text, re.DOTALL):
            filename = match.group(1).strip()
            content = match.group(2)
            result[filename] = content
        return result
