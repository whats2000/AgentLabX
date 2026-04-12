"""ArXiv paper search tool."""

from __future__ import annotations

import asyncio
from typing import Any

import arxiv
from pydantic import BaseModel

from agentlabx.tools.base import BaseTool, ToolResult


class ArxivSearchConfig(BaseModel):
    query: str
    max_results: int = 5


class ArxivSearch(BaseTool):
    name = "arxiv_search"
    description = (
        "Search arXiv for academic papers by keyword. Returns titles, abstracts,"
        " authors, and arxiv IDs."
    )
    config_schema = ArxivSearchConfig

    async def execute(self, **kwargs: Any) -> ToolResult:
        query = kwargs.get("query", "")
        max_results = kwargs.get("max_results", 5)
        if not query:
            return ToolResult(success=False, error="query is required")
        try:
            papers = await asyncio.to_thread(self._search_sync, query, max_results)
            return ToolResult(success=True, data={"papers": papers, "count": len(papers)})
        except Exception as e:
            return ToolResult(success=False, error=f"arXiv search failed: {e}")

    def _search_sync(self, query: str, max_results: int) -> list[dict[str, Any]]:
        client = arxiv.Client()
        search = arxiv.Search(
            query=query,
            max_results=max_results,
            sort_by=arxiv.SortCriterion.Relevance,
        )
        papers: list[dict[str, Any]] = []
        for result in client.results(search):
            papers.append(
                {
                    "arxiv_id": result.get_short_id(),
                    "title": result.title,
                    "abstract": result.summary,
                    "authors": [str(a) for a in result.authors],
                    "published": result.published.isoformat() if result.published else None,
                    "url": result.entry_id,
                }
            )
        return papers
