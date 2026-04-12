"""Tests for LaTeX compiler tool."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from agentlabx.tools.latex_compiler import LaTeXCompiler

MINIMAL_LATEX = r"""
\documentclass{article}
\begin{document}
Hello world.
\end{document}
"""


class TestLaTeXCompiler:
    @pytest.mark.asyncio
    async def test_missing_pdflatex_returns_error(self):
        with patch("shutil.which", return_value=None):
            tool = LaTeXCompiler()
            result = await tool.execute(latex_source=MINIMAL_LATEX)

        assert result.success is False
        assert "pdflatex not installed" in result.error

    @pytest.mark.asyncio
    async def test_empty_source_returns_error(self):
        tool = LaTeXCompiler()
        result = await tool.execute(latex_source="")
        assert result.success is False
        assert "latex_source is required" in result.error

    def test_schema(self):
        tool = LaTeXCompiler()
        schema = tool.get_schema()
        assert schema["name"] == "latex_compiler"
        assert "parameters" in schema
        props = schema["parameters"]["properties"]
        assert "latex_source" in props
        assert "output_name" in props

    @pytest.mark.asyncio
    async def test_pdflatex_failure_returns_error(self):
        """Mock a pdflatex run that returns non-zero exit code."""
        mock_proc = MagicMock()
        mock_proc.returncode = 1
        mock_proc.communicate = AsyncMock(return_value=(b"", b"! LaTeX Error: something"))
        mock_proc.kill = MagicMock()

        with patch("shutil.which", return_value="/usr/bin/pdflatex"):
            with patch("asyncio.create_subprocess_exec", new_callable=AsyncMock) as mock_exec:
                mock_exec.return_value = mock_proc

                tool = LaTeXCompiler()
                result = await tool.execute(latex_source=MINIMAL_LATEX)

        assert result.success is False
        assert "pdflatex failed" in result.error
