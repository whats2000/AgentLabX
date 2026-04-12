"""Semantic Scholar citation search tool."""

from __future__ import annotations

import asyncio
from typing import Any

from pydantic import BaseModel
from semanticscholar import SemanticScholar

from agentlabx.tools.base import BaseTool, ToolResult


class SemanticScholarConfig(BaseModel):
    query: str
    max_results: int = 5


class SemanticScholarSearch(BaseTool):
    name = "semantic_scholar"
    description = "Search Semantic Scholar for academic papers with citation counts."
    config_schema = SemanticScholarConfig

    async def execute(self, **kwargs: Any) -> ToolResult:
        query = kwargs.get("query", "")
        max_results = kwargs.get("max_results", 5)
        if not query:
            return ToolResult(success=False, error="query is required")
        try:
            papers = await asyncio.to_thread(self._search_sync, query, max_results)
            return ToolResult(success=True, data={"papers": papers, "count": len(papers)})
        except Exception as e:
            return ToolResult(success=False, error=f"Semantic Scholar search failed: {e}")

    def _search_sync(self, query: str, max_results: int) -> list[dict[str, Any]]:
        sch = SemanticScholar()
        results = sch.search_paper(query, limit=max_results)
        papers: list[dict[str, Any]] = []
        for p in results:
            papers.append(
                {
                    "paper_id": getattr(p, "paperId", "") or "",
                    "title": getattr(p, "title", "") or "",
                    "abstract": getattr(p, "abstract", "") or "",
                    "year": getattr(p, "year", None),
                    "citation_count": getattr(p, "citationCount", 0) or 0,
                    "authors": [getattr(a, "name", "") for a in (getattr(p, "authors", []) or [])],
                    "url": getattr(p, "url", "") or "",
                }
            )
        return papers
