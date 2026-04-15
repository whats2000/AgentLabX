"""Harness session bootstrap. Wraps the production PipelineExecutor for
harness use, with an event collector that mirrors the session's event bus into
a list accessible to tests.

Two boot modes:
- boot_mock(): MockLLMProvider. Fast unit-test mode for the harness itself.
- boot_live(): LiteLLMProvider reading AGENTLABX_LLM__DEFAULT_MODEL from env.
  Requires provider API key; gated by live_harness marker.
"""
from __future__ import annotations

import asyncio
import contextlib
from typing import Any

from agentlabx.core.events import Event
from agentlabx.core.session import Session, SessionManager
from agentlabx.providers.llm.litellm_provider import LiteLLMProvider
from agentlabx.providers.llm.mock_provider import MockLLMProvider
from agentlabx.server.deps import build_default_registry
from agentlabx.server.executor import PipelineExecutor


class HarnessSession:
    def __init__(
        self,
        *,
        executor: PipelineExecutor,
        session_manager: SessionManager,
        session: Session,
    ) -> None:
        self.executor = executor
        self.session_manager = session_manager
        self.session = session
        self.session_id = session.session_id
        self.event_bus = session.event_bus
        self.events: list[dict[str, Any]] = []
        self._mirror_task: asyncio.Task | None = None

    @property
    def state(self) -> dict[str, Any]:
        """Return session-level fields synchronously.

        Full LangGraph state lives in the checkpoint DB and requires an async
        call. Use ``await get_state()`` when pipeline fields (artifacts,
        stage_plans, etc.) are needed. This sync property is kept for
        boot-test compatibility.
        """
        return {
            "research_topic": getattr(self.session, "research_topic", ""),
            "session_id": self.session.session_id,
            "user_id": getattr(self.session, "user_id", ""),
        }

    async def get_state(self) -> dict[str, Any]:
        """Return full LangGraph pipeline state merged with Session-level fields.

        Async accessor used by Plan 8 spine tests to snapshot state at station
        boundaries. Pipeline state keys take precedence over Session fields so
        callers always see the most up-to-date values.
        """
        session_fields = self.state
        try:
            pipeline_state = await self.executor.get_pipeline_state(self.session_id)
        except Exception:
            pipeline_state = {}
        merged = dict(session_fields)
        merged.update(pipeline_state)
        return merged

    async def emit_synthetic_event(self, event: dict[str, Any]) -> None:
        """Append a synthetic event directly to the collector list."""
        self.events.append(event)

    async def _on_bus_event(self, event: Event) -> None:
        """Handler subscribed to the session's event bus; mirrors into self.events."""
        self.events.append(
            {
                "type": event.type,
                "data": event.data,
                "source": event.source,
                "timestamp": event.timestamp.isoformat(),
            }
        )

    def _start_mirror(self) -> None:
        """Subscribe the mirror handler to the session event bus."""
        self.event_bus.subscribe("*", self._on_bus_event)

    def _stop_mirror(self) -> None:
        """Unsubscribe the mirror handler from the session event bus."""
        self.event_bus.unsubscribe("*", self._on_bus_event)

    @classmethod
    async def _build_executor(
        cls, *, llm_provider: Any, tmp_db: str = ":memory:"
    ) -> tuple[PipelineExecutor, SessionManager]:
        import tempfile
        from pathlib import Path

        from agentlabx.core.registry import PluginType
        from agentlabx.providers.execution.subprocess_backend import SubprocessBackend
        from agentlabx.providers.storage.sqlite_backend import SQLiteBackend
        from agentlabx.tools.code_executor import CodeExecutor

        registry = build_default_registry()

        # Register code_executor — build_default_registry() omits it because the
        # production path constructs it after the execution backend is available
        # (see build_app_context). The harness needs it for data_exploration,
        # data_preparation, and experimentation stages.
        execution_backend = SubprocessBackend()
        registry.register(PluginType.EXECUTION_BACKEND, execution_backend.name, execution_backend)
        registry.register(PluginType.TOOL, "code_executor", CodeExecutor(backend=execution_backend))

        # Wire an in-memory SQLite storage backend so TracedLLMProvider emits
        # agent_llm_request events. Without storage, PipelineExecutor skips
        # TracedLLMProvider wrapping and no LLM events are recorded.
        storage_tmp_dir = tempfile.mkdtemp(prefix="harness_storage_")
        storage = SQLiteBackend(
            database_url="sqlite+aiosqlite:///:memory:",
            artifacts_path=Path(storage_tmp_dir),
        )
        await storage.initialize()

        session_manager = SessionManager()
        executor = PipelineExecutor(
            registry=registry,
            session_manager=session_manager,
            llm_provider=llm_provider,
            storage=storage,
            checkpoint_db_path=tmp_db,
        )
        await executor.initialize()
        return executor, session_manager

    @classmethod
    @contextlib.asynccontextmanager
    async def boot_mock(cls, *, topic: str = "test topic"):
        """Boot a HarnessSession backed by MockLLMProvider (no network calls)."""
        import tempfile
        import os

        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            tmp_db = f.name

        try:
            executor, manager = await cls._build_executor(
                llm_provider=MockLLMProvider(), tmp_db=tmp_db
            )
            try:
                session = manager.create_session(
                    user_id="harness",
                    research_topic=topic,
                )
                await executor.start_session(session)
                h = cls(executor=executor, session_manager=manager, session=session)
                h._start_mirror()
                try:
                    yield h
                finally:
                    h._stop_mirror()
                    try:
                        await executor.cancel_session(session.session_id)
                    except Exception:
                        pass
            finally:
                await executor.close()
        finally:
            try:
                os.unlink(tmp_db)
            except OSError:
                pass

    @classmethod
    @contextlib.asynccontextmanager
    async def boot_live(cls, *, topic: str = "live test topic"):
        """Boot a HarnessSession backed by LiteLLMProvider.

        Requires a valid API key in the environment. Gate behind
        @pytest.mark.live_harness.
        """
        import tempfile
        import os

        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            tmp_db = f.name

        try:
            executor, manager = await cls._build_executor(
                llm_provider=LiteLLMProvider(), tmp_db=tmp_db
            )
            try:
                session = manager.create_session(
                    user_id="harness",
                    research_topic=topic,
                )
                await executor.start_session(session)
                h = cls(executor=executor, session_manager=manager, session=session)
                h._start_mirror()
                try:
                    yield h
                finally:
                    h._stop_mirror()
                    try:
                        await executor.cancel_session(session.session_id)
                    except Exception:
                        pass
            finally:
                await executor.close()
        finally:
            try:
                os.unlink(tmp_db)
            except OSError:
                pass
