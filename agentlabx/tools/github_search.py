"""GitHub repository search tool."""

from __future__ import annotations

import asyncio
import os
from typing import Any

from github import Auth, Github
from pydantic import BaseModel

from agentlabx.tools.base import BaseTool, ToolResult


class GitHubSearchConfig(BaseModel):
    query: str
    max_results: int = 5


class GitHubSearch(BaseTool):
    name = "github_search"
    description = "Search GitHub repositories matching a query. Requires GITHUB_TOKEN env var."
    config_schema = GitHubSearchConfig

    async def execute(self, **kwargs: Any) -> ToolResult:
        query = kwargs.get("query", "")
        max_results = kwargs.get("max_results", 5)
        if not query:
            return ToolResult(success=False, error="query is required")
        token = os.getenv("GITHUB_TOKEN")
        if not token:
            return ToolResult(success=False, error="GITHUB_TOKEN env var not set")
        try:
            repos = await asyncio.to_thread(self._search_sync, token, query, max_results)
            return ToolResult(success=True, data={"repos": repos, "count": len(repos)})
        except Exception as e:
            return ToolResult(success=False, error=f"GitHub search failed: {e}")

    def _search_sync(self, token: str, query: str, max_results: int) -> list[dict[str, Any]]:
        gh = Github(auth=Auth.Token(token))
        try:
            results = gh.search_repositories(query=query)
            repos: list[dict[str, Any]] = []
            for i, repo in enumerate(results):
                if i >= max_results:
                    break
                repos.append(
                    {
                        "full_name": repo.full_name,
                        "description": repo.description or "",
                        "stars": repo.stargazers_count,
                        "language": repo.language or "",
                        "url": repo.html_url,
                        "clone_url": repo.clone_url,
                    }
                )
            return repos
        finally:
            gh.close()
