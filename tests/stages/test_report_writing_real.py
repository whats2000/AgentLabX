"""Tests for real report writing stage."""

from __future__ import annotations

from pathlib import Path

import pytest

from agentlabx.agents.config_loader import AgentConfigLoader
from agentlabx.core.registry import PluginRegistry
from agentlabx.core.state import create_initial_state
from agentlabx.providers.llm.mock_provider import MockLLMProvider
from agentlabx.stages.base import StageContext
from agentlabx.stages.report_writing import ReportWritingStage

CONFIGS_DIR = Path(__file__).parent.parent.parent / "agentlabx" / "agents" / "configs"


@pytest.fixture()
def registry() -> PluginRegistry:
    reg = PluginRegistry()
    loader = AgentConfigLoader()
    configs = loader.load_all(CONFIGS_DIR)
    loader.register_all(configs, reg)
    return reg


class TestReportWritingStage:
    async def test_runs_end_to_end(self, registry):
        provider = MockLLMProvider(
            responses=[
                r"Outline: \section{Introduction}, \section{Methods}, \section{Results}",
                # Draft — a complete LaTeX doc with sections
                (
                    r"\documentclass{article}\begin{document}"
                    r"\begin{abstract}Test abstract.\end{abstract}"
                    r"\section{Introduction}Intro text."
                    r"\section{Methods}Methodology."
                    r"\section{Results}Findings."
                    r"\end{document}"
                ),
                # Polished version
                (
                    r"\documentclass{article}\begin{document}"
                    r"\begin{abstract}Polished abstract.\end{abstract}"
                    r"\section{Introduction}Polished intro."
                    r"\section{Methods}Polished methods."
                    r"\section{Results}Polished results."
                    r"\end{document}"
                ),
            ]
        )
        context = StageContext(
            settings={},
            event_bus=None,
            registry=registry,
            llm_provider=provider,
        )
        state = create_initial_state(
            session_id="s1",
            user_id="u1",
            research_topic="Test topic",
        )

        stage = ReportWritingStage()
        result = await stage.run(state, context)

        assert result.status == "done"
        assert "report" in result.output
        report = result.output["report"][0]
        assert "Polished abstract" in report.latex_source
        assert "Introduction" in report.sections
        assert "Polished intro" in report.sections["Introduction"]

    async def test_no_registry_returns_backtrack(self):
        context = StageContext(settings={}, event_bus=None, registry=None)
        state = create_initial_state(session_id="s1", user_id="u1", research_topic="test")
        stage = ReportWritingStage()
        result = await stage.run(state, context)
        assert result.status == "backtrack"

    async def test_extracts_multiple_sections(self):
        stage = ReportWritingStage()
        latex = (
            r"\documentclass{article}\begin{document}"
            r"\section{A}alpha content"
            r"\section{B}beta content"
            r"\end{document}"
        )
        sections = stage._extract_sections(latex)
        assert "A" in sections
        assert "B" in sections
        assert "alpha" in sections["A"]
