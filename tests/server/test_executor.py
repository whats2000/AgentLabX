"""Tests for PipelineExecutor."""

from __future__ import annotations

import asyncio

import pytest

from agentlabx.agents.config_loader import AgentConfigLoader
from agentlabx.core.registry import PluginRegistry
from agentlabx.core.session import Session, SessionManager, SessionStatus
from agentlabx.providers.llm.mock_provider import MockLLMProvider
from agentlabx.providers.storage.sqlite_backend import SQLiteBackend
from agentlabx.server.deps import AGENT_CONFIGS_DIR
from agentlabx.server.executor import PipelineExecutor
from agentlabx.plugins._builtin import register_builtin_plugins


@pytest.fixture()
async def registry():
    reg = PluginRegistry()
    loader = AgentConfigLoader()
    configs = loader.load_all(AGENT_CONFIGS_DIR)
    loader.register_all(configs, reg)
    register_builtin_plugins(reg)
    return reg


@pytest.fixture()
async def executor(registry, tmp_path):
    storage = SQLiteBackend(
        database_url=f"sqlite+aiosqlite:///{tmp_path / 'test.db'}",
        artifacts_path=tmp_path / "artifacts",
    )
    await storage.initialize()
    manager = SessionManager(storage=storage)
    ex = PipelineExecutor(
        registry=registry,
        session_manager=manager,
        llm_provider=MockLLMProvider(),
        checkpoint_db_path=str(tmp_path / "checkpoints.db"),
    )
    await ex.initialize()
    yield ex
    await ex.close()
    await storage.close()


class TestPipelineExecutor:
    async def test_initialize_creates_checkpoint_db(self, registry, tmp_path):
        db_path = tmp_path / "cp.db"
        ex = PipelineExecutor(
            registry=registry,
            session_manager=SessionManager(),
            llm_provider=MockLLMProvider(),
            checkpoint_db_path=str(db_path),
        )
        await ex.initialize()
        assert db_path.exists()
        await ex.close()

    async def test_start_session_creates_running_entry(self, executor):
        session = Session(
            session_id="sess-001",
            user_id="u1",
            research_topic="test",
        )
        executor.session_manager._sessions[session.session_id] = session
        running = await executor.start_session(session)
        assert running.session is session
        assert running.thread_id == session.session_id
        assert executor.get_running("sess-001") is running
        assert session.status == SessionStatus.RUNNING
        # Cleanup: wait for task to complete
        try:
            await asyncio.wait_for(running.task, timeout=5.0)
        except TimeoutError:
            await executor.cancel_session("sess-001")

    async def test_start_session_twice_raises(self, executor):
        session = Session(
            session_id="sess-dup",
            user_id="u",
            research_topic="t",
        )
        executor.session_manager._sessions[session.session_id] = session
        await executor.start_session(session)
        with pytest.raises(RuntimeError, match="already running"):
            await executor.start_session(session)
        await executor.cancel_session("sess-dup")

    async def test_pause_clears_event(self, executor):
        session = Session(
            session_id="sess-pause",
            user_id="u",
            research_topic="t",
        )
        executor.session_manager._sessions[session.session_id] = session
        running = await executor.start_session(session)
        assert running.paused_event.is_set()

        await executor.pause_session("sess-pause")
        assert not running.paused_event.is_set()
        assert session.status == SessionStatus.PAUSED

        # Resume
        await executor.resume_session("sess-pause")
        assert running.paused_event.is_set()
        assert session.status == SessionStatus.RUNNING
        await executor.cancel_session("sess-pause")

    async def test_pause_missing_raises_keyerror(self, executor):
        with pytest.raises(KeyError):
            await executor.pause_session("nonexistent")

    async def test_cancel_session_removes_entry(self, executor):
        session = Session(
            session_id="sess-cancel",
            user_id="u",
            research_topic="t",
        )
        executor.session_manager._sessions[session.session_id] = session
        await executor.start_session(session)
        assert executor.get_running("sess-cancel") is not None
        await executor.cancel_session("sess-cancel")
        # Fix E: cancelled sessions are marked FAILED
        assert session.status == SessionStatus.FAILED
        assert executor.get_running("sess-cancel") is None

    async def test_cancel_missing_is_noop(self, executor):
        # Should not raise
        await executor.cancel_session("nonexistent")

    async def test_redirect_updates_state(self, executor):
        session = Session(
            session_id="sess-redir",
            user_id="u",
            research_topic="t",
        )
        executor.session_manager._sessions[session.session_id] = session
        running = await executor.start_session(session)
        # Brief sleep to ensure graph has taken its initial checkpoint
        await asyncio.sleep(0.1)
        try:
            await executor.redirect_session("sess-redir", "plan_formulation", "test")
            # Verify the call does not raise — state update happens asynchronously
            config = {"configurable": {"thread_id": "sess-redir"}}
            await running.graph.aget_state(config)
        finally:
            await executor.cancel_session("sess-redir")

    async def test_running_entry_preserved_after_completion(self, executor):
        """Fix D: session stays in _running after completion for state queries."""
        session = Session(
            session_id="sess-complete",
            user_id="u",
            research_topic="t",
        )
        executor.session_manager._sessions[session.session_id] = session
        await executor.start_session(session)
        running = executor.get_running("sess-complete")
        # Wait for completion
        try:
            await asyncio.wait_for(running.task, timeout=10.0)
        except TimeoutError:
            pytest.fail("Pipeline did not complete within 10s")

        # Fix D: entry remains even after completion
        assert executor.get_running("sess-complete") is not None
        assert session.status in (SessionStatus.COMPLETED, SessionStatus.FAILED)

    async def test_event_forwarder_receives_events(self, registry, tmp_path):
        """Fix G: single forwarder subscribed at session start receives all events."""
        received: list[tuple[str, dict]] = []

        async def forwarder(session_id: str, event: dict) -> None:
            received.append((session_id, event))

        storage = SQLiteBackend(
            database_url=f"sqlite+aiosqlite:///{tmp_path / 't.db'}",
            artifacts_path=tmp_path / "artifacts",
        )
        await storage.initialize()
        manager = SessionManager(storage=storage)
        ex = PipelineExecutor(
            registry=registry,
            session_manager=manager,
            llm_provider=MockLLMProvider(),
            checkpoint_db_path=str(tmp_path / "cp.db"),
            event_forwarder=forwarder,
        )
        await ex.initialize()

        session = Session(
            session_id="sess-events",
            user_id="u",
            research_topic="t",
        )
        manager._sessions[session.session_id] = session

        running = await ex.start_session(session)
        try:
            await asyncio.wait_for(running.task, timeout=10.0)
        except TimeoutError:
            pass

        # Events should have been forwarded — at least stage_started events
        assert any(ev[1]["type"] == "stage_started" for ev in received)
        # All events carry the right session_id
        assert all(ev[0] == "sess-events" for ev in received)

        await ex.close()
        await storage.close()
