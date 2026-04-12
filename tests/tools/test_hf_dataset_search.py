"""Tests for HuggingFace dataset search tool."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from agentlabx.tools.hf_dataset_search import HFDatasetSearch


def _make_mock_dataset(
    id: str = "squad",
    description: str = "SQuAD dataset",
    downloads: int = 1000,
    likes: int = 50,
    tags: list[str] | None = None,
) -> MagicMock:
    ds = MagicMock()
    ds.id = id
    ds.description = description
    ds.downloads = downloads
    ds.likes = likes
    ds.tags = tags or ["nlp", "question-answering"]
    return ds


class TestHFDatasetSearch:
    @pytest.mark.asyncio
    async def test_search_returns_datasets(self):
        mock_ds = _make_mock_dataset()
        with patch("agentlabx.tools.hf_dataset_search.list_datasets") as mock_list:
            mock_list.return_value = iter([mock_ds])

            tool = HFDatasetSearch()
            result = await tool.execute(query="squad", max_results=5)

        assert result.success is True
        assert result.data["count"] == 1
        datasets = result.data["datasets"]
        assert len(datasets) == 1
        assert datasets[0]["id"] == "squad"
        assert datasets[0]["description"] == "SQuAD dataset"
        assert datasets[0]["downloads"] == 1000
        assert datasets[0]["likes"] == 50
        assert "nlp" in datasets[0]["tags"]

    @pytest.mark.asyncio
    async def test_empty_query_returns_error(self):
        tool = HFDatasetSearch()
        result = await tool.execute()
        assert result.success is False
        assert "query is required" in result.error

    def test_schema(self):
        tool = HFDatasetSearch()
        schema = tool.get_schema()
        assert schema["name"] == "hf_dataset_search"
        assert "parameters" in schema
        props = schema["parameters"]["properties"]
        assert "query" in props
        assert "max_results" in props
