"""Session artifact search tool for cross-session code reuse."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel

from agentlabx.providers.storage.base import BaseStorageBackend
from agentlabx.tools.base import BaseTool, ToolResult


class SessionArtifactSearchConfig(BaseModel):
    user_id: str
    query: str
    artifact_type: str | None = None
    max_results: int = 10


class SessionArtifactSearch(BaseTool):
    name = "session_artifact_search"
    description = (
        "Search artifacts across prior sessions for the same user"
        " (\u2018elder student\u2019s code\u2019 pattern)."
    )
    config_schema = SessionArtifactSearchConfig

    def __init__(self, backend: BaseStorageBackend) -> None:
        self.backend = backend

    async def execute(self, **kwargs: Any) -> ToolResult:
        user_id = kwargs.get("user_id", "")
        query = kwargs.get("query", "")
        artifact_type = kwargs.get("artifact_type")
        max_results = kwargs.get("max_results", 10)
        if not user_id or not query:
            return ToolResult(success=False, error="user_id and query are required")
        try:
            matches = await self._search(user_id, query, artifact_type, max_results)
            return ToolResult(success=True, data={"artifacts": matches, "count": len(matches)})
        except Exception as e:
            return ToolResult(success=False, error=f"Session artifact search failed: {e}")

    async def _search(
        self, user_id: str, query: str, artifact_type: str | None, max_results: int
    ) -> list[dict[str, Any]]:
        # The backend doesn't expose a list-artifacts API in Plan 3.
        # For this skeleton, use the backend's internal session list if available,
        # else return empty. Plan 4+ extends BaseStorageBackend with list methods.
        if not hasattr(self.backend, "list_artifacts"):
            return []
        artifacts = await self.backend.list_artifacts(user_id=user_id)
        query_lower = query.lower()
        matches = []
        for art in artifacts:
            if artifact_type and art.get("artifact_type") != artifact_type:
                continue
            name = art.get("name", "").lower()
            if query_lower in name:
                matches.append(art)
                if len(matches) >= max_results:
                    break
        return matches
