"""Session management: preferences, lifecycle, and multi-user session tracking."""

from __future__ import annotations

import uuid
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


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


class SessionStatus(str, Enum):
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

    def update_preferences(self, preferences: SessionPreferences) -> None:
        """Replace session preferences."""
        self.preferences = preferences


class SessionManager:
    """Manages multiple sessions across users."""

    def __init__(self) -> None:
        self._sessions: dict[str, Session] = {}

    def create_session(
        self,
        *,
        user_id: str,
        research_topic: str,
        preferences: SessionPreferences | None = None,
    ) -> Session:
        """Create a new session with a unique UUID-based ID."""
        session_id = str(uuid.uuid4())
        session = Session(
            session_id=session_id,
            user_id=user_id,
            research_topic=research_topic,
            preferences=preferences or SessionPreferences(),
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
