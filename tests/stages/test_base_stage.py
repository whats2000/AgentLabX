from __future__ import annotations

import pytest

from agentlabx.core.state import PipelineState, create_initial_state
from agentlabx.stages.base import BaseStage, StageContext, StageResult


class ConcreteStage(BaseStage):
    name = "test_stage"
    description = "A test stage"
    required_agents = ["phd_student"]
    required_tools = ["arxiv_search"]

    async def run(self, state: PipelineState, context: StageContext) -> StageResult:
        return StageResult(output={"test": "data"}, status="done", reason="Test completed")


class IncompleteStage(BaseStage):
    name = "incomplete"
    description = "Incomplete"
    required_agents = []
    required_tools = []


class TestBaseStage:
    def test_concrete_stage_instantiates(self):
        stage = ConcreteStage()
        assert stage.name == "test_stage"
        assert stage.required_agents == ["phd_student"]

    def test_abstract_stage_cannot_instantiate(self):
        with pytest.raises(TypeError):
            IncompleteStage()

    async def test_run_returns_stage_result(self):
        stage = ConcreteStage()
        state = create_initial_state(session_id="s1", user_id="u1", research_topic="test")
        context = StageContext(settings={}, event_bus=None, registry=None)
        result = await stage.run(state, context)
        assert result.status == "done"
        assert result.output == {"test": "data"}

    def test_validate_default_returns_true(self):
        stage = ConcreteStage()
        state = create_initial_state(session_id="s1", user_id="u1", research_topic="test")
        assert stage.validate(state) is True

    def test_on_enter_returns_state(self):
        stage = ConcreteStage()
        state = create_initial_state(session_id="s1", user_id="u1", research_topic="test")
        result = stage.on_enter(state)
        assert result["session_id"] == "s1"


class TestStageResult:
    def test_done_status(self):
        result = StageResult(output={}, status="done", reason="Complete")
        assert result.next_hint is None
        assert result.feedback is None
        assert result.requests is None

    def test_backtrack_with_hint(self):
        result = StageResult(
            output={},
            status="backtrack",
            next_hint="data_preparation",
            reason="Data quality issues",
            feedback="Need cleaner dataset",
        )
        assert result.status == "backtrack"
        assert result.next_hint == "data_preparation"

    def test_negative_result(self):
        result = StageResult(
            output={"finding": "no significant improvement"},
            status="negative_result",
            reason="CoT did not improve accuracy beyond baseline",
        )
        assert result.status == "negative_result"

    def test_request_status(self):
        from agentlabx.core.state import CrossStageRequest

        req = CrossStageRequest(
            from_stage="report_writing",
            to_stage="experimentation",
            request_type="experiment",
            description="Need ablation study",
            status="pending",
        )
        result = StageResult(
            output={}, status="request", reason="Missing ablation for paper", requests=[req]
        )
        assert len(result.requests) == 1
