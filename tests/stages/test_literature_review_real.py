"""Tests for real literature review stage."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from agentlabx.agents.config_loader import AgentConfigLoader
from agentlabx.core.registry import PluginRegistry, PluginType
from agentlabx.core.state import create_initial_state
from agentlabx.providers.llm.mock_provider import MockLLMProvider
from agentlabx.stages.base import StageContext
from agentlabx.stages.literature_review import LiteratureReviewStage
from agentlabx.tools.arxiv_search import ArxivSearch

CONFIGS_DIR = Path(__file__).parent.parent.parent / "agentlabx" / "agents" / "configs"


@pytest.fixture()
def registry() -> PluginRegistry:
    reg = PluginRegistry()
    loader = AgentConfigLoader()
    configs = loader.load_all(CONFIGS_DIR)
    loader.register_all(configs, reg)
    reg.register(PluginType.TOOL, "arxiv_search", ArxivSearch)
    return reg


@pytest.fixture()
def mock_arxiv_result():
    """Patches arxiv.Client to return 3 canned papers."""
    result = MagicMock()
    result.get_short_id.return_value = "2201.11903"
    result.title = "Chain of Thought Prompting"
    result.summary = "Abstract about CoT."
    result.entry_id = "http://arxiv.org/abs/2201.11903"
    result.authors = [MagicMock(__str__=lambda self: "Wei et al.")]
    result.published = MagicMock()
    result.published.isoformat.return_value = "2022-01-28"
    return result


class TestLiteratureReviewStage:
    async def test_runs_end_to_end(self, registry, mock_arxiv_result):
        provider = MockLLMProvider(
            responses=[
                "chain of thought prompting LLM",  # query 1
                "Literature review summary: CoT prompting improves reasoning.",
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
            research_topic="MATH with CoT",
        )

        with patch("agentlabx.tools.arxiv_search.arxiv.Client") as mock_client:
            mock_client.return_value.results.return_value = iter(
                [
                    mock_arxiv_result,
                    mock_arxiv_result,
                    mock_arxiv_result,
                    mock_arxiv_result,
                    mock_arxiv_result,
                ]
            )
            stage = LiteratureReviewStage()
            result = await stage.run(state, context)

        assert result.status == "done"
        assert "literature_review" in result.output
        assert len(result.output["literature_review"]) == 1
        review = result.output["literature_review"][0]
        assert len(review.papers) >= 5
        assert "CoT" in review.summary or "summary" in review.summary.lower()

    async def test_no_registry_returns_backtrack(self):
        context = StageContext(settings={}, event_bus=None, registry=None)
        state = create_initial_state(session_id="s1", user_id="u1", research_topic="test")
        stage = LiteratureReviewStage()
        result = await stage.run(state, context)
        assert result.status == "backtrack"

    async def test_query_extraction_handles_quoted_response(self):
        stage = LiteratureReviewStage()
        assert stage._extract_query('"chain of thought"') == "chain of thought"
        assert stage._extract_query("line one\nline two") == "line one"

    async def test_empty_papers_still_synthesizes(self, registry):
        """Even with 0 papers, the summary should still be produced."""
        provider = MockLLMProvider(
            responses=[
                "query 1",
                "query 2",
                "query 3",  # 3 queries
                "Summary with no papers: area is underexplored.",  # synthesis
            ]
        )
        context = StageContext(
            settings={},
            event_bus=None,
            registry=registry,
            llm_provider=provider,
        )
        state = create_initial_state(session_id="s1", user_id="u1", research_topic="test")

        with patch("agentlabx.tools.arxiv_search.arxiv.Client") as mock_client:
            mock_client.return_value.results.return_value = iter([])
            stage = LiteratureReviewStage()
            result = await stage.run(state, context)

        assert result.status == "done"
        review = result.output["literature_review"][0]
        assert len(review.papers) == 0
        assert "underexplored" in review.summary
