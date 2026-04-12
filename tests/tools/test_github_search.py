"""Tests for GitHub repository search tool."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from agentlabx.tools.github_search import GitHubSearch


def _make_mock_repo(
    full_name: str = "openai/gpt-2",
    description: str = "GPT-2 model",
    stars: int = 20000,
    language: str = "Python",
    html_url: str = "https://github.com/openai/gpt-2",
    clone_url: str = "https://github.com/openai/gpt-2.git",
) -> MagicMock:
    repo = MagicMock()
    repo.full_name = full_name
    repo.description = description
    repo.stargazers_count = stars
    repo.language = language
    repo.html_url = html_url
    repo.clone_url = clone_url
    return repo


class TestGitHubSearch:
    @pytest.mark.asyncio
    async def test_search_returns_repos(self, monkeypatch):
        monkeypatch.setenv("GITHUB_TOKEN", "fake-token")
        mock_repo = _make_mock_repo()

        with patch("agentlabx.tools.github_search.Github") as mock_github_cls:
            mock_gh = MagicMock()
            mock_gh.search_repositories.return_value = iter([mock_repo])
            mock_github_cls.return_value = mock_gh

            tool = GitHubSearch()
            result = await tool.execute(query="gpt language:python", max_results=5)

        assert result.success is True
        assert result.data["count"] == 1
        repos = result.data["repos"]
        assert len(repos) == 1
        assert repos[0]["full_name"] == "openai/gpt-2"
        assert repos[0]["description"] == "GPT-2 model"
        assert repos[0]["stars"] == 20000
        assert repos[0]["language"] == "Python"
        assert repos[0]["url"] == "https://github.com/openai/gpt-2"
        assert repos[0]["clone_url"] == "https://github.com/openai/gpt-2.git"

    @pytest.mark.asyncio
    async def test_missing_token_returns_error(self, monkeypatch):
        monkeypatch.delenv("GITHUB_TOKEN", raising=False)
        tool = GitHubSearch()
        result = await tool.execute(query="gpt language:python")
        assert result.success is False
        assert "GITHUB_TOKEN" in result.error

    @pytest.mark.asyncio
    async def test_empty_query_returns_error(self, monkeypatch):
        monkeypatch.setenv("GITHUB_TOKEN", "fake-token")
        tool = GitHubSearch()
        result = await tool.execute()
        assert result.success is False
        assert "query is required" in result.error

    def test_schema(self):
        tool = GitHubSearch()
        schema = tool.get_schema()
        assert schema["name"] == "github_search"
        assert "parameters" in schema
        props = schema["parameters"]["properties"]
        assert "query" in props
        assert "max_results" in props
