"""Tests for session manager: SessionPreferences, Session, SessionManager."""

from __future__ import annotations

import pytest

from agentlabx.core.session import (
    Session,
    SessionManager,
    SessionPreferences,
    SessionStatus,
)


class TestSessionPreferences:
    def test_defaults(self):
        prefs = SessionPreferences()
        assert prefs.mode == "auto"
        assert prefs.stage_controls == {}
        assert prefs.backtrack_control == "auto"

    def test_get_stage_control_default(self):
        prefs = SessionPreferences()
        assert prefs.get_stage_control("literature_review") == "auto"

    def test_get_stage_control_custom(self):
        prefs = SessionPreferences(stage_controls={"experimentation": "hitl"})
        assert prefs.get_stage_control("experimentation") == "hitl"
        assert prefs.get_stage_control("literature_review") == "auto"

    def test_update_returns_new_instance(self):
        prefs = SessionPreferences()
        updated = prefs.update(mode="hitl", backtrack_control="hitl")
        assert updated.mode == "hitl"
        assert updated.backtrack_control == "hitl"
        # Original unchanged
        assert prefs.mode == "auto"

    def test_update_stage_controls(self):
        prefs = SessionPreferences()
        updated = prefs.update(stage_controls={"peer_review": "hitl"})
        assert updated.stage_controls["peer_review"] == "hitl"


class TestSession:
    def test_create_session(self):
        session = Session(
            session_id="sess-001",
            user_id="user-001",
            research_topic="Scaling laws",
        )
        assert session.session_id == "sess-001"
        assert session.user_id == "user-001"
        assert session.research_topic == "Scaling laws"
        assert session.status == SessionStatus.CREATED

    def test_status_transitions(self):
        session = Session(
            session_id="sess-001",
            user_id="user-001",
            research_topic="Test",
        )
        session.start()
        assert session.status == SessionStatus.RUNNING

        session.pause()
        assert session.status == SessionStatus.PAUSED

        session.resume()
        assert session.status == SessionStatus.RUNNING

        session.complete()
        assert session.status == SessionStatus.COMPLETED

    def test_fail_transition(self):
        session = Session(
            session_id="sess-001",
            user_id="user-001",
            research_topic="Test",
        )
        session.start()
        session.fail()
        assert session.status == SessionStatus.FAILED

    def test_invalid_transition_raises(self):
        session = Session(
            session_id="sess-001",
            user_id="user-001",
            research_topic="Test",
        )
        # Can't pause from CREATED
        with pytest.raises((ValueError, RuntimeError)):
            session.pause()

    def test_update_preferences_while_running(self):
        session = Session(
            session_id="sess-001",
            user_id="user-001",
            research_topic="Test",
        )
        session.start()
        new_prefs = SessionPreferences(mode="hitl")
        session.update_preferences(new_prefs)
        assert session.preferences.mode == "hitl"


class TestSessionManager:
    def setup_method(self):
        self.manager = SessionManager()

    def test_create_session(self):
        session = self.manager.create_session(
            user_id="user-001",
            research_topic="Scaling laws",
        )
        assert session.session_id is not None
        assert session.user_id == "user-001"
        assert session.research_topic == "Scaling laws"
        assert session.status == SessionStatus.CREATED

    def test_get_session(self):
        session = self.manager.create_session(
            user_id="user-001",
            research_topic="Test",
        )
        retrieved = self.manager.get_session(session.session_id)
        assert retrieved is session

    def test_get_nonexistent_raises(self):
        with pytest.raises((KeyError, ValueError)):
            self.manager.get_session("nonexistent-id")

    def test_list_sessions(self):
        s1 = self.manager.create_session(user_id="user-001", research_topic="T1")
        s2 = self.manager.create_session(user_id="user-002", research_topic="T2")
        all_sessions = self.manager.list_sessions()
        assert s1 in all_sessions
        assert s2 in all_sessions

    def test_list_by_user(self):
        s1 = self.manager.create_session(user_id="user-001", research_topic="T1")
        s2 = self.manager.create_session(user_id="user-001", research_topic="T2")
        s3 = self.manager.create_session(user_id="user-002", research_topic="T3")
        user_sessions = self.manager.list_sessions(user_id="user-001")
        assert s1 in user_sessions
        assert s2 in user_sessions
        assert s3 not in user_sessions

    def test_unique_ids(self):
        sessions = [
            self.manager.create_session(user_id="user-001", research_topic=f"T{i}")
            for i in range(10)
        ]
        ids = [s.session_id for s in sessions]
        assert len(set(ids)) == 10


class TestSessionEventBus:
    def test_session_has_event_bus_on_creation(self):
        from agentlabx.core.events import EventBus

        session = Session(
            session_id="s1",
            user_id="u1",
            research_topic="test",
        )
        assert isinstance(session.event_bus, EventBus)

    def test_each_session_has_own_bus(self):
        s1 = Session(session_id="a", user_id="u", research_topic="t")
        s2 = Session(session_id="b", user_id="u", research_topic="t")
        assert s1.event_bus is not s2.event_bus

    async def test_session_bus_receives_events(self):
        from agentlabx.core.events import Event

        session = Session(session_id="s1", user_id="u1", research_topic="test")
        received = []

        async def handler(event):
            received.append(event)

        session.event_bus.subscribe("test", handler)
        await session.event_bus.emit(Event(type="test", data={"x": 1}))
        assert len(received) == 1
