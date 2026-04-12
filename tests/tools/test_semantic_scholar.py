"""Tests for Semantic Scholar search tool."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from agentlabx.tools.semantic_scholar import SemanticScholarSearch


def _make_mock_paper(
    paper_id: str = "abc123",
    title: str = "Attention Is All You Need",
    abstract: str = "We propose the Transformer.",
    year: int = 2017,
    citation_count: int = 50000,
    author_names: list[str] | None = None,
    url: str = "https://www.semanticscholar.org/paper/abc123",
) -> MagicMock:
    paper = MagicMock()
    paper.paperId = paper_id
    paper.title = title
    paper.abstract = abstract
    paper.year = year
    paper.citationCount = citation_count
    paper.url = url
    authors = []
    for name in author_names or ["Vaswani", "Shazeer"]:
        a = MagicMock()
        a.name = name
        authors.append(a)
    paper.authors = authors
    return paper


class TestSemanticScholarSearch:
    @pytest.mark.asyncio
    async def test_search_returns_papers(self):
        mock_paper = _make_mock_paper()
        with patch("agentlabx.tools.semantic_scholar.SemanticScholar") as mock_ss_cls:
            mock_sch = MagicMock()
            mock_sch.search_paper.return_value = [mock_paper]
            mock_ss_cls.return_value = mock_sch

            tool = SemanticScholarSearch()
            result = await tool.execute(query="attention transformer", max_results=5)

        assert result.success is True
        assert result.data["count"] == 1
        papers = result.data["papers"]
        assert len(papers) == 1
        assert papers[0]["paper_id"] == "abc123"
        assert papers[0]["title"] == "Attention Is All You Need"
        assert papers[0]["citation_count"] == 50000
        assert papers[0]["year"] == 2017
        assert "Vaswani" in papers[0]["authors"]
        assert papers[0]["url"] == "https://www.semanticscholar.org/paper/abc123"

    @pytest.mark.asyncio
    async def test_empty_query_returns_error(self):
        tool = SemanticScholarSearch()
        result = await tool.execute()
        assert result.success is False
        assert "query is required" in result.error

    def test_schema(self):
        tool = SemanticScholarSearch()
        schema = tool.get_schema()
        assert schema["name"] == "semantic_scholar"
        assert "parameters" in schema
        props = schema["parameters"]["properties"]
        assert "query" in props
        assert "max_results" in props
