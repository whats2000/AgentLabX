"""Tests for SQLiteBackend."""

from __future__ import annotations

from pathlib import Path

import pytest_asyncio

from agentlabx.providers.storage.sqlite_backend import SQLiteBackend


@pytest_asyncio.fixture
async def backend(tmp_path: Path) -> SQLiteBackend:
    db_path = tmp_path / "test.db"
    b = SQLiteBackend(
        database_url=f"sqlite+aiosqlite:///{db_path}",
        artifacts_path=tmp_path / "artifacts",
    )
    await b.initialize()
    yield b
    await b.close()


class TestSQLiteBackend:
    async def test_save_and_load_state(self, backend: SQLiteBackend):
        await backend.save_state("sess-1", "lit_review", {"papers": 5, "summary": "test"})
        state = await backend.load_state("sess-1", "lit_review")
        assert state == {"papers": 5, "summary": "test"}

    async def test_load_missing_returns_none(self, backend: SQLiteBackend):
        state = await backend.load_state("nonexistent", "stage")
        assert state is None

    async def test_save_overwrites(self, backend: SQLiteBackend):
        await backend.save_state("sess-1", "lit_review", {"v": 1})
        await backend.save_state("sess-1", "lit_review", {"v": 2})
        state = await backend.load_state("sess-1", "lit_review")
        assert state == {"v": 2}

    async def test_state_is_session_scoped(self, backend: SQLiteBackend):
        await backend.save_state("sess-a", "lit_review", {"owner": "a"})
        await backend.save_state("sess-b", "lit_review", {"owner": "b"})
        a = await backend.load_state("sess-a", "lit_review")
        b = await backend.load_state("sess-b", "lit_review")
        assert a["owner"] == "a"
        assert b["owner"] == "b"

    async def test_save_and_load_artifact(self, backend: SQLiteBackend):
        path = await backend.save_artifact("sess-1", "code", "train.py", b"print('hi')")
        data = await backend.load_artifact(path)
        assert data == b"print('hi')"

    async def test_artifact_missing_returns_none(self, backend: SQLiteBackend):
        data = await backend.load_artifact("nonexistent/path")
        assert data is None

    async def test_artifact_namespacing(self, backend: SQLiteBackend):
        """Artifacts for different sessions should not collide."""
        p1 = await backend.save_artifact("sess-a", "code", "file.py", b"a")
        p2 = await backend.save_artifact("sess-b", "code", "file.py", b"b")
        assert p1 != p2
        assert await backend.load_artifact(p1) == b"a"
        assert await backend.load_artifact(p2) == b"b"

    async def test_delete_session_removes_state(self, backend: SQLiteBackend):
        await backend.save_state("sess-1", "lit_review", {"v": 1})
        await backend.delete_session("sess-1")
        assert await backend.load_state("sess-1", "lit_review") is None

    async def test_delete_session_removes_artifact_files(self, backend: SQLiteBackend):
        path = await backend.save_artifact("sess-1", "code", "f.py", b"hello")
        assert Path(path).exists()
        await backend.delete_session("sess-1")
        assert not Path(path).exists()

    async def test_delete_session_is_session_scoped(self, backend: SQLiteBackend):
        """Deleting sess-a must leave sess-b untouched."""
        await backend.save_state("sess-a", "lit", {"o": "a"})
        await backend.save_state("sess-b", "lit", {"o": "b"})
        p_a = await backend.save_artifact("sess-a", "code", "f.py", b"a")
        p_b = await backend.save_artifact("sess-b", "code", "f.py", b"b")

        await backend.delete_session("sess-a")

        assert await backend.load_state("sess-a", "lit") is None
        assert await backend.load_state("sess-b", "lit") == {"o": "b"}
        assert not Path(p_a).exists()
        assert Path(p_b).exists()

    async def test_delete_session_is_idempotent(self, backend: SQLiteBackend):
        """Deleting a session that never existed is not an error."""
        await backend.delete_session("sess-never-existed")
