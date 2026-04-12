"""Tests for SessionManager persistence wrappers and restore."""

from __future__ import annotations

import pytest

from agentlabx.core.session import SessionManager, SessionStatus
from agentlabx.providers.storage.sqlite_backend import SQLiteBackend


@pytest.fixture()
async def storage(tmp_path):
    s = SQLiteBackend(
        database_url=f"sqlite+aiosqlite:///{tmp_path / 'sessions.db'}",
        artifacts_path=tmp_path / "artifacts",
    )
    await s.initialize()
    yield s
    await s.close()


class TestPersistSession:
    async def test_persist_saves_metadata(self, storage):
        manager = SessionManager(storage=storage)
        session = manager.create_session(
            user_id="alice",
            research_topic="test topic",
            config_overrides={"llm": {"default_model": "gpt-4o"}},
        )
        await manager.persist_session(session)

        raw = await storage.load_state(session.session_id, "session_metadata")
        assert raw is not None
        assert raw["user_id"] == "alice"
        assert raw["research_topic"] == "test topic"
        assert raw["status"] == "created"
        assert raw["config_overrides"] == {"llm": {"default_model": "gpt-4o"}}

    async def test_persist_without_storage_noop(self):
        """Persistence is a no-op when storage is None."""
        manager = SessionManager()
        session = manager.create_session(user_id="u", research_topic="t")
        # Should not raise
        await manager.persist_session(session)

    async def test_persist_overwrites_existing(self, storage):
        manager = SessionManager(storage=storage)
        session = manager.create_session(user_id="u", research_topic="t")
        await manager.persist_session(session)

        # Transition and re-persist
        session.start()
        await manager.persist_session(session)

        raw = await storage.load_state(session.session_id, "session_metadata")
        assert raw["status"] == "running"


class TestRestoreSession:
    async def test_restore_returns_session(self, storage):
        manager_a = SessionManager(storage=storage)
        session = manager_a.create_session(user_id="alice", research_topic="topic")
        session.start()
        session.update_preferences(mode="hitl")
        await manager_a.persist_session(session)

        # New manager with same storage — restart scenario
        manager_b = SessionManager(storage=storage)
        restored = await manager_b.restore_session(session.session_id)

        assert restored is not None
        assert restored.session_id == session.session_id
        assert restored.user_id == "alice"
        assert restored.research_topic == "topic"
        assert restored.status == SessionStatus.RUNNING
        assert restored.preferences.mode == "hitl"

    async def test_restore_missing_returns_none(self, storage):
        manager = SessionManager(storage=storage)
        result = await manager.restore_session("sess-nonexistent")
        assert result is None

    async def test_restore_without_storage_returns_none(self):
        manager = SessionManager()
        result = await manager.restore_session("any-id")
        assert result is None

    async def test_restore_already_in_memory_returns_same(self, storage):
        manager = SessionManager(storage=storage)
        session = manager.create_session(user_id="u", research_topic="t")
        # Not yet persisted
        restored = await manager.restore_session(session.session_id)
        assert restored is session  # Exact same object


class TestAsyncTransitionWrappers:
    async def test_start_session_wrapper_persists(self, storage):
        manager = SessionManager(storage=storage)
        session = manager.create_session(user_id="u", research_topic="t")
        await manager.start_session(session.session_id)

        raw = await storage.load_state(session.session_id, "session_metadata")
        assert raw["status"] == "running"

    async def test_pause_session_wrapper_persists(self, storage):
        manager = SessionManager(storage=storage)
        session = manager.create_session(user_id="u", research_topic="t")
        session.start()
        await manager.pause_session(session.session_id)
        raw = await storage.load_state(session.session_id, "session_metadata")
        assert raw["status"] == "paused"

    async def test_resume_session_wrapper_persists(self, storage):
        manager = SessionManager(storage=storage)
        session = manager.create_session(user_id="u", research_topic="t")
        session.start()
        session.pause()
        await manager.resume_session(session.session_id)
        raw = await storage.load_state(session.session_id, "session_metadata")
        assert raw["status"] == "running"

    async def test_complete_session_wrapper_persists(self, storage):
        manager = SessionManager(storage=storage)
        session = manager.create_session(user_id="u", research_topic="t")
        session.start()
        await manager.complete_session(session.session_id)
        raw = await storage.load_state(session.session_id, "session_metadata")
        assert raw["status"] == "completed"

    async def test_fail_session_wrapper_persists(self, storage):
        manager = SessionManager(storage=storage)
        session = manager.create_session(user_id="u", research_topic="t")
        await manager.fail_session(session.session_id)
        raw = await storage.load_state(session.session_id, "session_metadata")
        assert raw["status"] == "failed"

    async def test_wrapper_raises_keyerror_for_missing_session(self, storage):
        manager = SessionManager(storage=storage)
        with pytest.raises(KeyError):
            await manager.start_session("sess-missing")

    async def test_wrapper_propagates_invalid_transition(self, storage):
        """ValueError from session transition should propagate through wrapper."""
        manager = SessionManager(storage=storage)
        session = manager.create_session(user_id="u", research_topic="t")
        # Can't pause from CREATED
        with pytest.raises(ValueError, match="Invalid transition"):
            await manager.pause_session(session.session_id)

    async def test_persist_errors_propagate(self, tmp_path):
        """If storage raises during persist, the wrapper surfaces the error.

        This is the critical contract of Fix F — NO silent error swallowing.
        """
        from unittest.mock import AsyncMock

        manager = SessionManager(storage=None)
        # Create with no storage, then attach a storage that always fails
        session = manager.create_session(user_id="u", research_topic="t")

        broken_storage = AsyncMock()
        broken_storage.save_state.side_effect = RuntimeError("disk full")
        manager._storage = broken_storage

        with pytest.raises(RuntimeError, match="disk full"):
            await manager.start_session(session.session_id)


class TestSessionSurvivesRestart:
    """Integration: session metadata survives a SessionManager restart."""

    async def test_full_restart_flow(self, storage):
        # First "process": create, start, persist
        manager1 = SessionManager(storage=storage)
        session = manager1.create_session(
            user_id="alice",
            research_topic="survives restart",
        )
        sid = session.session_id
        await manager1.start_session(sid)

        # Simulate restart — new manager, same storage
        manager2 = SessionManager(storage=storage)
        assert sid not in manager2._sessions  # Not loaded yet

        restored = await manager2.restore_session(sid)
        assert restored is not None
        assert restored.status == SessionStatus.RUNNING
        assert restored.research_topic == "survives restart"
        # Now in memory
        assert manager2.get_session(sid) is restored
