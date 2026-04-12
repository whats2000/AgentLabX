"""PipelineExecutor — manages running sessions as asyncio tasks.

Each session runs in its own asyncio task. The executor handles:
- Graph construction with AsyncSqliteSaver checkpointer (Fix C)
- Cooperative pause via asyncio.Event on StageContext (Fix A)
- Session status transitions (including fail-on-cancel, Fix E)
- Single event subscription per session for WS fan-out (Fix G)
- State preserved in checkpoint for post-completion queries (Fix D)

Note: session_id is used as the LangGraph thread_id. With AsyncSqliteSaver
this means a session can be restarted and will continue from its last
checkpoint rather than starting fresh (Fix L). To re-run from scratch,
create a new session.
"""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path
from typing import Any

import aiosqlite
from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver

from agentlabx.core.events import Event, EventBus
from agentlabx.core.pipeline import PipelineBuilder
from agentlabx.core.registry import PluginRegistry
from agentlabx.core.session import Session, SessionManager
from agentlabx.core.state import CostTracker, create_initial_state
from agentlabx.providers.llm.base import BaseLLMProvider
from agentlabx.stages.base import StageContext

logger = logging.getLogger(__name__)


class RunningSession:
    """In-memory handle for a session with a live asyncio task."""

    def __init__(
        self,
        *,
        session: Session,
        graph: Any,
        event_bus: EventBus,
        cost_tracker: CostTracker,
        task: asyncio.Task,
        thread_id: str,
        paused_event: asyncio.Event,
    ) -> None:
        self.session = session
        self.graph = graph
        self.event_bus = event_bus
        self.cost_tracker = cost_tracker
        self.task = task
        self.thread_id = thread_id
        self.paused_event = paused_event


class PipelineExecutor:
    """Runs pipelines per session as independent asyncio tasks."""

    def __init__(
        self,
        *,
        registry: PluginRegistry,
        session_manager: SessionManager,
        llm_provider: BaseLLMProvider,
        checkpoint_db_path: str = "data/checkpoints.db",
        event_forwarder: Any = None,
    ) -> None:
        """Create an executor.

        event_forwarder: optional async callable(session_id, event_dict) that
        receives every event from every session's event_bus. Set by the app
        to the WS connection manager's broadcast method (Fix G).
        """
        self.registry = registry
        self.session_manager = session_manager
        self.llm_provider = llm_provider
        self.checkpoint_db_path = checkpoint_db_path
        self.event_forwarder = event_forwarder
        self._running: dict[str, RunningSession] = {}
        self._checkpointer: AsyncSqliteSaver | None = None
        self._checkpointer_conn: Any | None = None

    async def initialize(self) -> None:
        """Open the persistent checkpoint DB (Fix C). Call once at app startup."""
        Path(self.checkpoint_db_path).parent.mkdir(parents=True, exist_ok=True)
        self._checkpointer_conn = await aiosqlite.connect(self.checkpoint_db_path)
        # Compatibility shim: AsyncSqliteSaver (langgraph-checkpoint-sqlite 2.x)
        # calls conn.is_alive() which aiosqlite >=0.20 no longer provides (the
        # Connection class dropped its Thread base). Since we only reach setup()
        # after awaiting aiosqlite.connect(...) the connection is already live,
        # so a trivial stub is safe.
        if not hasattr(self._checkpointer_conn, "is_alive"):
            self._checkpointer_conn.is_alive = lambda: True  # type: ignore[attr-defined]
        self._checkpointer = AsyncSqliteSaver(self._checkpointer_conn)

    async def close(self) -> None:
        """Cancel all running tasks and close the checkpoint DB."""
        for session_id in list(self._running.keys()):
            await self.cancel_session(session_id)
        if self._checkpointer_conn is not None:
            await self._checkpointer_conn.close()
            self._checkpointer_conn = None
            self._checkpointer = None

    def get_running(self, session_id: str) -> RunningSession | None:
        """Return the RunningSession for this id, or None if not running."""
        return self._running.get(session_id)

    async def start_session(self, session: Session) -> RunningSession:
        """Begin running a session's pipeline as an asyncio task.

        The session_id is used as the LangGraph thread_id. With AsyncSqliteSaver
        this means restarting a session continues from its last checkpoint (Fix L).
        To re-run from scratch, create a new session with a fresh session_id.
        """
        if session.session_id in self._running:
            raise RuntimeError(f"Session {session.session_id} is already running")

        if self._checkpointer is None:
            raise RuntimeError("Executor not initialized — call initialize() first")

        session.start()

        # Build stage sequence from config overrides OR default
        from agentlabx.core.config import PipelineConfig

        pipeline_overrides = session.config_overrides.get("pipeline", {})
        default_sequence = (
            pipeline_overrides.get("default_sequence") or PipelineConfig().default_sequence
        )

        event_bus = session.event_bus  # Fix B: reuse session-owned bus
        cost_tracker = CostTracker()

        # Cooperative pause event (Fix A) — set means running
        paused_event = asyncio.Event()
        paused_event.set()

        # Build stage context with pause event wired in
        stage_context = StageContext(
            settings={},
            event_bus=event_bus,
            registry=self.registry,
            llm_provider=self.llm_provider,
            cost_tracker=cost_tracker,
            paused_event=paused_event,
        )

        # Subscribe single forwarder per session (Fix G) — WS handler does not
        # subscribe per-client; all broadcasts go through the executor
        if self.event_forwarder is not None:
            forwarder = self.event_forwarder
            session_id = session.session_id

            async def forward_to_ws(event: Event) -> None:
                await forwarder(
                    session_id,
                    {
                        "type": event.type,
                        "data": event.data,
                        "source": event.source,
                    },
                )

            event_bus.subscribe("*", forward_to_ws)

        builder = PipelineBuilder(
            registry=self.registry,
            preferences=session.preferences,
        )
        graph = builder.build(
            stage_sequence=default_sequence,
            checkpointer=self._checkpointer,
            stage_context=stage_context,  # Fix A: context with paused_event
        )

        initial_state = create_initial_state(
            session_id=session.session_id,
            user_id=session.user_id,
            research_topic=session.research_topic,
            default_sequence=default_sequence,
        )
        thread_id = session.session_id
        config = {"configurable": {"thread_id": thread_id}}

        session_manager = self.session_manager

        async def run_pipeline() -> None:
            try:
                await graph.ainvoke(initial_state, config=config)
                session.complete()
                # Task 10 wraps persist_session in SessionManager transition methods.
                # Here we call persist directly if available (graceful fallback for now).
                if hasattr(session_manager, "persist_session"):
                    try:
                        await session_manager.persist_session(session)
                    except Exception:
                        logger.exception(
                            "Failed to persist session %s on complete", session.session_id
                        )
            except asyncio.CancelledError:
                # Fix E: mark session as FAILED on cancel
                logger.info("Session %s cancelled", session.session_id)
                try:
                    session.fail()
                    if hasattr(session_manager, "persist_session"):
                        try:
                            await session_manager.persist_session(session)
                        except Exception:
                            logger.exception(
                                "Failed to persist cancelled session %s", session.session_id
                            )
                except Exception:
                    # If transition was invalid (already terminal), swallow
                    pass
                raise
            except Exception as e:
                logger.exception("Pipeline error for %s: %s", session.session_id, e)
                try:
                    session.fail()
                    if hasattr(session_manager, "persist_session"):
                        try:
                            await session_manager.persist_session(session)
                        except Exception:
                            logger.exception(
                                "Failed to persist failed session %s", session.session_id
                            )
                except Exception:
                    pass
            # Fix D: do NOT pop from _running on completion/failure. Graph state
            # is checkpointed to SQLite; the handle remains valid for state
            # queries. Cleanup happens via explicit cancel_session or close().

        task = asyncio.create_task(
            run_pipeline(),
            name=f"pipeline-{session.session_id}",
        )
        running = RunningSession(
            session=session,
            graph=graph,
            event_bus=event_bus,
            cost_tracker=cost_tracker,
            task=task,
            thread_id=thread_id,
            paused_event=paused_event,
        )
        self._running[session.session_id] = running
        return running

    async def pause_session(self, session_id: str) -> None:
        """Clear the paused_event so StageRunner blocks at next boundary."""
        running = self._running.get(session_id)
        if running is None:
            raise KeyError(session_id)
        running.session.pause()
        running.paused_event.clear()

    async def resume_session(self, session_id: str) -> None:
        """Set the paused_event so blocked StageRunner continues."""
        running = self._running.get(session_id)
        if running is None:
            raise KeyError(session_id)
        running.session.resume()
        running.paused_event.set()

    async def redirect_session(
        self,
        session_id: str,
        target_stage: str,
        reason: str,
    ) -> None:
        """Update graph state with human_override to redirect on next transition."""
        running = self._running.get(session_id)
        if running is None:
            raise KeyError(session_id)
        config = {"configurable": {"thread_id": running.thread_id}}
        await running.graph.aupdate_state(config, {"human_override": target_stage})

    async def cancel_session(self, session_id: str) -> None:
        """Cancel the running task and remove the entry."""
        running = self._running.get(session_id)
        if running is None:
            return
        running.task.cancel()
        try:
            await running.task
        except asyncio.CancelledError:
            pass
        except Exception:
            logger.exception("Error awaiting cancelled task for %s", session_id)
        # Fix E: ensure session transitioned to FAILED even if the task was
        # cancelled before entering our try/except (e.g., cancelled immediately
        # after create_task before run_pipeline had a chance to start).
        from agentlabx.core.session import SessionStatus

        if running.session.status in (SessionStatus.RUNNING, SessionStatus.PAUSED):
            try:
                running.session.fail()
                if hasattr(self.session_manager, "persist_session"):
                    try:
                        await self.session_manager.persist_session(running.session)
                    except Exception:
                        logger.exception("Failed to persist cancelled session %s", session_id)
            except Exception:
                pass
        # Now we remove from _running (explicit cancellation path)
        self._running.pop(session_id, None)
