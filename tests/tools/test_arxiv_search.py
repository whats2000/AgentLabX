"""Tests for ArXiv search tool."""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import MagicMock, patch

import pytest

from agentlabx.tools.arxiv_search import ArxivSearch


def _make_mock_result(
    short_id: str = "2401.00001",
    title: str = "Test Paper",
    summary: str = "An abstract.",
    authors: list[str] | None = None,
    published: datetime | None = None,
    entry_id: str = "https://arxiv.org/abs/2401.00001",
) -> MagicMock:
    result = MagicMock()
    result.get_short_id.return_value = short_id
    result.title = title
    result.summary = summary
    result.authors = [
        MagicMock(__str__=lambda self, _a=a: _a) for a in (authors or ["Alice", "Bob"])
    ]
    result.published = published or datetime(2024, 1, 1, tzinfo=UTC)
    result.entry_id = entry_id
    return result


class TestArxivSearch:
    @pytest.mark.asyncio
    async def test_search_returns_results(self):
        mock_result = _make_mock_result()
        with patch("arxiv.Client") as mock_arxiv_client:
            mock_client_instance = MagicMock()
            mock_client_instance.results.return_value = iter([mock_result])
            mock_arxiv_client.return_value = mock_client_instance

            tool = ArxivSearch()
            result = await tool.execute(query="transformer models", max_results=1)

        assert result.success is True
        assert result.data["count"] == 1
        papers = result.data["papers"]
        assert len(papers) == 1
        assert papers[0]["arxiv_id"] == "2401.00001"
        assert papers[0]["title"] == "Test Paper"
        assert papers[0]["abstract"] == "An abstract."
        assert "Alice" in papers[0]["authors"]
        assert papers[0]["published"] is not None
        assert papers[0]["url"] == "https://arxiv.org/abs/2401.00001"

    @pytest.mark.asyncio
    async def test_empty_results(self):
        with patch("arxiv.Client") as mock_arxiv_client:
            mock_client_instance = MagicMock()
            mock_client_instance.results.return_value = iter([])
            mock_arxiv_client.return_value = mock_client_instance

            tool = ArxivSearch()
            result = await tool.execute(query="xyzzy nonexistent paper 12345", max_results=5)

        assert result.success is True
        assert result.data["count"] == 0
        assert result.data["papers"] == []

    def test_schema(self):
        tool = ArxivSearch()
        schema = tool.get_schema()
        assert schema["name"] == "arxiv_search"
        assert "parameters" in schema
        props = schema["parameters"]["properties"]
        assert "query" in props
        assert "max_results" in props

    @pytest.mark.asyncio
    async def test_missing_query_returns_error(self):
        tool = ArxivSearch()
        result = await tool.execute(max_results=5)
        assert result.success is False
        assert "query is required" in result.error
