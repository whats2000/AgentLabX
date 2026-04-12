from __future__ import annotations

from datetime import UTC, datetime

import pytest

from agentlabx.core.state import StageError, create_initial_state
from agentlabx.stages.base import StageContext
from agentlabx.stages.lab_meeting import LabMeeting, LabMeetingTrigger


@pytest.fixture()
def state():
    return create_initial_state(session_id="s1", user_id="u1", research_topic="MATH benchmark")


@pytest.fixture()
def context():
    return StageContext(settings={}, event_bus=None, registry=None)


class TestLabMeetingTrigger:
    def test_no_trigger_on_fresh_state(self, state):
        trigger = LabMeetingTrigger(consecutive_failures=3, score_plateau_rounds=2)
        assert trigger.should_trigger(state) is False

    def test_triggers_on_consecutive_failures(self, state):
        trigger = LabMeetingTrigger(consecutive_failures=3, score_plateau_rounds=2)
        errors = []
        for i in range(3):
            errors.append(
                StageError(
                    stage="experimentation",
                    error_type="RuntimeError",
                    message=f"Failure {i}",
                    timestamp=datetime.now(UTC),
                )
            )
        state["errors"] = errors
        assert trigger.should_trigger(state) is True

    def test_does_not_trigger_below_threshold(self, state):
        trigger = LabMeetingTrigger(consecutive_failures=3, score_plateau_rounds=2)
        state["errors"] = [
            StageError(
                stage="experimentation",
                error_type="RuntimeError",
                message="Failure",
                timestamp=datetime.now(UTC),
            )
        ]
        assert trigger.should_trigger(state) is False


class TestLabMeeting:
    async def test_lab_meeting_runs(self, state, context):
        meeting = LabMeeting()
        result = await meeting.run(state, context)
        assert result.status == "done"
        assert "action_items" in result.output

    async def test_lab_meeting_returns_action_items(self, state, context):
        meeting = LabMeeting()
        result = await meeting.run(state, context)
        assert isinstance(result.output["action_items"], list)
        assert len(result.output["action_items"]) > 0
