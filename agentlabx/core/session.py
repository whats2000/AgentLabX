"""Session management: preferences, lifecycle, and multi-user session tracking."""

from __future__ import annotations

import uuid
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field

from agentlabx.core.events import EventBus


class SessionPreferences(BaseModel):
    """User preferences for a research session."""

    mode: str = "auto"  # "auto" or "hitl"
    stage_controls: dict[str, str] = Field(default_factory=dict)
    backtrack_control: str = "auto"

    def get_stage_control(self, stage: str) -> str:
        """Return the control mode for a given stage (defaults to 'auto')."""
        return self.stage_controls.get(stage, "auto")

    def update(self, **kwargs: Any) -> SessionPreferences:
        """Return a new SessionPreferences with the given fields updated."""
        data = self.model_dump()
        data.update(kwargs)
        return SessionPreferences(**data)


class SessionStatus(StrEnum):
    """Lifecycle statuses for a research session."""

    CREATED = "created"
    RUNNING = "running"
    PAUSED = "paused"
    COMPLETED = "completed"
    FAILED = "failed"


# Valid transitions: from_status -> set of allowed to_status
_VALID_TRANSITIONS: dict[SessionStatus, set[SessionStatus]] = {
    SessionStatus.CREATED: {SessionStatus.RUNNING, SessionStatus.FAILED},
    SessionStatus.RUNNING: {SessionStatus.PAUSED, SessionStatus.COMPLETED, SessionStatus.FAILED},
    SessionStatus.PAUSED: {SessionStatus.RUNNING, SessionStatus.FAILED},
    SessionStatus.COMPLETED: set(),
    SessionStatus.FAILED: set(),
}


class Session(BaseModel):
    """A research session with lifecycle management."""

    session_id: str
    user_id: str
    research_topic: str
    status: SessionStatus = SessionStatus.CREATED
    preferences: SessionPreferences = Field(default_factory=SessionPreferences)
    config_overrides: dict[str, Any] = Field(default_factory=dict)
    event_bus: EventBus = Field(default_factory=EventBus)  # Fix B: own bus at creation

    model_config = {"arbitrary_types_allowed": True}

    def _transition(self, new_status: SessionStatus) -> None:
        allowed = _VALID_TRANSITIONS.get(self.status, set())
        if new_status not in allowed:
            msg = (
                f"Invalid transition from {self.status.value!r} to {new_status.value!r}. "
                f"Allowed: {[s.value for s in allowed]}"
            )
            raise ValueError(msg)
        self.status = new_status

    def start(self) -> None:
        """Transition from CREATED to RUNNING."""
        self._transition(SessionStatus.RUNNING)

    def pause(self) -> None:
        """Transition from RUNNING to PAUSED."""
        self._transition(SessionStatus.PAUSED)

    def resume(self) -> None:
        """Transition from PAUSED to RUNNING."""
        self._transition(SessionStatus.RUNNING)

    def complete(self) -> None:
        """Transition from RUNNING to COMPLETED."""
        self._transition(SessionStatus.COMPLETED)

    def fail(self) -> None:
        """Transition to FAILED from any non-terminal state."""
        self._transition(SessionStatus.FAILED)

    def update_preferences(
        self, preferences: SessionPreferences | None = None, **kwargs: Any
    ) -> None:
        """Update session preferences.

        Accepts either a full SessionPreferences object (legacy) or keyword
        arguments for partial updates (e.g. mode="hitl", stage_controls={...}).
        """
        if preferences is not None:
            self.preferences = preferences
        elif kwargs:
            self.preferences = self.preferences.update(**kwargs)


class SessionManager:
    """Manages multiple sessions across users."""

    def __init__(self, *, storage: Any = None) -> None:
        self._sessions: dict[str, Session] = {}
        self._storage = storage

    def create_session(
        self,
        *,
        user_id: str,
        research_topic: str,
        preferences: SessionPreferences | None = None,
        config_overrides: dict[str, Any] | None = None,
    ) -> Session:
        """Create a new session with a unique UUID-based ID."""
        session_id = f"sess-{uuid.uuid4()}"
        session = Session(
            session_id=session_id,
            user_id=user_id,
            research_topic=research_topic,
            preferences=preferences or SessionPreferences(),
            config_overrides=config_overrides or {},
        )
        self._sessions[session_id] = session
        return session

    def get_session(self, session_id: str) -> Session:
        """Retrieve a session by ID. Raises KeyError if not found."""
        if session_id not in self._sessions:
            msg = f"Session '{session_id}' not found."
            raise KeyError(msg)
        return self._sessions[session_id]

    def list_sessions(self, *, user_id: str | None = None) -> list[Session]:
        """List all sessions, optionally filtered by user_id."""
        sessions = list(self._sessions.values())
        if user_id is not None:
            sessions = [s for s in sessions if s.user_id == user_id]
        return sessions

    async def persist_session(self, session: Session) -> None:
        """Save session metadata to storage.

        No-op when storage is None (tests/in-memory mode). Errors propagate
        to the caller — persistence failures are not silently swallowed.
        """
        if self._storage is None:
            return
        await self._storage.save_state(
            session.session_id,
            "session_metadata",
            {
                "session_id": session.session_id,
                "user_id": session.user_id,
                "research_topic": session.research_topic,
                "status": session.status.value,
                "preferences": session.preferences.model_dump(),
                "config_overrides": session.config_overrides,
            },
        )

    async def restore_session(self, session_id: str) -> Session | None:
        """Load a session from storage if not already in memory.

        Returns the restored Session, or None if no metadata exists.
        """
        if session_id in self._sessions:
            return self._sessions[session_id]
        if self._storage is None:
            return None
        data = await self._storage.load_state(session_id, "session_metadata")
        if not data:
            return None
        session = Session(
            session_id=data["session_id"],
            user_id=data["user_id"],
            research_topic=data["research_topic"],
            config_overrides=data.get("config_overrides", {}),
        )
        session.status = SessionStatus(data["status"])
        session.preferences = SessionPreferences(**data.get("preferences", {}))
        self._sessions[session_id] = session
        return session

    async def restore_all(self, user_id: str | None = None) -> list[Session]:
        """Restore all sessions for a user from storage into memory.

        Best-effort — requires storage to expose list_sessions (Plan 5+ may add).
        For now, callers explicitly call restore_session(session_id) when they
        know the ID.
        """
        if self._storage is None:
            return []
        if not hasattr(self._storage, "list_sessions"):
            return []
        ids = await self._storage.list_sessions(user_id=user_id)
        restored: list[Session] = []
        for sid in ids:
            session = await self.restore_session(sid)
            if session is not None:
                restored.append(session)
        return restored

    # Async transition wrappers — transition the session AND persist.
    # Callers (REST routes, executor) go through these instead of calling
    # session.start()/pause()/etc. directly when persistence is desired.
    # Raw session.start()/pause()/... remain available on Session itself
    # for unit tests that don't want to touch storage.

    async def start_session(self, session_id: str) -> Session:
        """Transition CREATED -> RUNNING and persist."""
        session = self.get_session(session_id)
        session.start()
        await self.persist_session(session)
        return session

    async def pause_session(self, session_id: str) -> Session:
        """Transition RUNNING -> PAUSED and persist."""
        session = self.get_session(session_id)
        session.pause()
        await self.persist_session(session)
        return session

    async def resume_session(self, session_id: str) -> Session:
        """Transition PAUSED -> RUNNING and persist."""
        session = self.get_session(session_id)
        session.resume()
        await self.persist_session(session)
        return session

    async def complete_session(self, session_id: str) -> Session:
        """Transition RUNNING -> COMPLETED and persist."""
        session = self.get_session(session_id)
        session.complete()
        await self.persist_session(session)
        return session

    async def fail_session(self, session_id: str) -> Session:
        """Transition to FAILED and persist."""
        session = self.get_session(session_id)
        session.fail()
        await self.persist_session(session)
        return session

    async def delete_session(self, session_id: str) -> None:
        """Remove a session from memory and storage.

        Idempotent — unknown session IDs are tolerated so callers don't need
        to distinguish between "already gone" and "never existed". Storage
        deletion failures propagate so callers can surface them (e.g., as 500).
        """
        self._sessions.pop(session_id, None)
        if self._storage is not None and hasattr(self._storage, "delete_session"):
            await self._storage.delete_session(session_id)
