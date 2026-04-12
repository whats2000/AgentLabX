"""LaTeX compiler tool for report generation."""

from __future__ import annotations

import asyncio
import shutil
import tempfile
from pathlib import Path
from typing import Any

from pydantic import BaseModel

from agentlabx.tools.base import BaseTool, ToolResult


class LaTeXCompilerConfig(BaseModel):
    latex_source: str
    output_name: str = "output"


class LaTeXCompiler(BaseTool):
    name = "latex_compiler"
    description = "Compile LaTeX source code to a PDF file. Requires pdflatex on the system."
    config_schema = LaTeXCompilerConfig

    async def execute(self, **kwargs: Any) -> ToolResult:
        latex = kwargs.get("latex_source", "")
        output_name = kwargs.get("output_name", "output")
        if not latex:
            return ToolResult(success=False, error="latex_source is required")
        if not shutil.which("pdflatex"):
            return ToolResult(success=False, error="pdflatex not installed on system")

        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir)
            tex_file = tmp_path / f"{output_name}.tex"
            tex_file.write_text(latex)
            proc = await asyncio.create_subprocess_exec(
                "pdflatex",
                "-interaction=nonstopmode",
                "-output-directory",
                str(tmp_path),
                str(tex_file),
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            try:
                stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=60)
            except TimeoutError:
                proc.kill()
                return ToolResult(success=False, error="pdflatex timeout")
            pdf_file = tmp_path / f"{output_name}.pdf"
            if proc.returncode != 0 or not pdf_file.exists():
                return ToolResult(
                    success=False,
                    error=f"pdflatex failed: {stderr.decode('utf-8', errors='replace')[:500]}",
                )
            pdf_bytes = pdf_file.read_bytes()
            return ToolResult(success=True, data={"pdf_bytes": pdf_bytes, "size": len(pdf_bytes)})
