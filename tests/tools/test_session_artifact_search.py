"""Tests for session artifact search tool."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from agentlabx.tools.session_artifact_search import SessionArtifactSearch


class TestSessionArtifactSearch:
    @pytest.mark.asyncio
    async def test_returns_matching_artifacts(self):
        backend = MagicMock()
        backend.list_artifacts = AsyncMock(
            return_value=[
                {"name": "training_script.py", "artifact_type": "code", "session_id": "s1"},
                {"name": "eval_results.json", "artifact_type": "data", "session_id": "s1"},
                {"name": "training_config.yaml", "artifact_type": "config", "session_id": "s2"},
            ]
        )

        tool = SessionArtifactSearch(backend=backend)
        result = await tool.execute(user_id="user1", query="training")

        assert result.success is True
        assert result.data["count"] == 2
        names = [a["name"] for a in result.data["artifacts"]]
        assert "training_script.py" in names
        assert "training_config.yaml" in names
        assert "eval_results.json" not in names

    @pytest.mark.asyncio
    async def test_filter_by_type(self):
        backend = MagicMock()
        backend.list_artifacts = AsyncMock(
            return_value=[
                {"name": "training_script.py", "artifact_type": "code", "session_id": "s1"},
                {"name": "training_notes.txt", "artifact_type": "notes", "session_id": "s1"},
            ]
        )

        tool = SessionArtifactSearch(backend=backend)
        result = await tool.execute(user_id="user1", query="training", artifact_type="code")

        assert result.success is True
        assert result.data["count"] == 1
        assert result.data["artifacts"][0]["name"] == "training_script.py"

    @pytest.mark.asyncio
    async def test_missing_user_id_returns_error(self):
        backend = MagicMock()
        tool = SessionArtifactSearch(backend=backend)
        result = await tool.execute(query="training")
        assert result.success is False
        assert "user_id and query are required" in result.error

    @pytest.mark.asyncio
    async def test_backend_without_list_artifacts_returns_empty(self):
        # A backend that doesn't have list_artifacts (plan 3 base backend)
        backend = MagicMock(spec=[])  # no attributes at all

        tool = SessionArtifactSearch(backend=backend)
        result = await tool.execute(user_id="user1", query="training")

        assert result.success is True
        assert result.data["count"] == 0
        assert result.data["artifacts"] == []
