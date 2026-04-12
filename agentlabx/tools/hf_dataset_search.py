"""HuggingFace dataset search tool."""

from __future__ import annotations

import asyncio
from typing import Any

from huggingface_hub import list_datasets
from pydantic import BaseModel

from agentlabx.tools.base import BaseTool, ToolResult


class HFDatasetSearchConfig(BaseModel):
    query: str
    max_results: int = 5


class HFDatasetSearch(BaseTool):
    name = "hf_dataset_search"
    description = "Search HuggingFace datasets by name or description."
    config_schema = HFDatasetSearchConfig

    async def execute(self, **kwargs: Any) -> ToolResult:
        query = kwargs.get("query", "")
        max_results = kwargs.get("max_results", 5)
        if not query:
            return ToolResult(success=False, error="query is required")
        try:
            datasets = await asyncio.to_thread(self._search_sync, query, max_results)
            return ToolResult(success=True, data={"datasets": datasets, "count": len(datasets)})
        except Exception as e:
            return ToolResult(success=False, error=f"HuggingFace search failed: {e}")

    def _search_sync(self, query: str, max_results: int) -> list[dict[str, Any]]:
        results = []
        for ds in list_datasets(search=query, limit=max_results):
            results.append(
                {
                    "id": ds.id,
                    "description": getattr(ds, "description", "") or "",
                    "downloads": getattr(ds, "downloads", 0),
                    "likes": getattr(ds, "likes", 0),
                    "tags": list(getattr(ds, "tags", []) or []),
                }
            )
        return results
