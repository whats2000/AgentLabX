"""End-to-end pipeline test — verifies the full orchestration works."""

from __future__ import annotations

import pytest

from agentlabx.core.pipeline import PipelineBuilder
from agentlabx.core.registry import PluginRegistry
from agentlabx.core.session import SessionManager
from agentlabx.core.state import create_initial_state
from agentlabx.plugins._builtin import register_builtin_plugins


@pytest.fixture()
def full_pipeline():
    registry = PluginRegistry()
    register_builtin_plugins(registry)
    builder = PipelineBuilder(registry=registry)
    sequence = [
        "literature_review",
        "plan_formulation",
        "data_exploration",
        "data_preparation",
        "experimentation",
        "results_interpretation",
        "report_writing",
        "peer_review",
    ]
    graph = builder.build(stage_sequence=sequence)
    return graph, sequence


class TestPipelineE2E:
    async def test_full_pipeline_completes(self, full_pipeline):
        graph, sequence = full_pipeline
        state = create_initial_state(
            session_id="e2e-001",
            user_id="default",
            research_topic="Improve MATH benchmark accuracy with CoT",
            default_sequence=sequence,
        )
        config = {"configurable": {"thread_id": "e2e-test-1"}}
        result = await graph.ainvoke(state, config=config)
        assert result["total_iterations"] == 8
        assert len(result["completed_stages"]) == 8
        for stage_name in sequence:
            assert stage_name in result["completed_stages"]

    async def test_pipeline_with_session_manager(self, full_pipeline):
        graph, sequence = full_pipeline
        manager = SessionManager()
        session = manager.create_session(
            user_id="researcher_a",
            research_topic="NLP transfer learning",
        )
        session.start()
        assert session.status.value == "running"

        state = create_initial_state(
            session_id=session.session_id,
            user_id=session.user_id,
            research_topic=session.research_topic,
            default_sequence=sequence,
        )
        config = {"configurable": {"thread_id": session.session_id}}
        result = await graph.ainvoke(state, config=config)

        session.complete()
        assert session.status.value == "completed"
        assert result["total_iterations"] == 8

    async def test_pipeline_streaming(self, full_pipeline):
        graph, sequence = full_pipeline
        state = create_initial_state(
            session_id="stream-001",
            user_id="default",
            research_topic="Test streaming",
            default_sequence=sequence,
        )
        config = {"configurable": {"thread_id": "stream-test"}}
        events = []
        async for event in graph.astream(state, config=config):
            events.append(event)
        assert len(events) > 0

    async def test_partial_pipeline(self):
        registry = PluginRegistry()
        register_builtin_plugins(registry)
        builder = PipelineBuilder(registry=registry)
        short_sequence = ["literature_review", "plan_formulation"]
        graph = builder.build(stage_sequence=short_sequence)
        state = create_initial_state(
            session_id="partial-001",
            user_id="default",
            research_topic="Quick test",
            default_sequence=short_sequence,
        )
        config = {"configurable": {"thread_id": "partial-test"}}
        result = await graph.ainvoke(state, config=config)
        assert result["total_iterations"] == 2
        assert "literature_review" in result["completed_stages"]
        assert "plan_formulation" in result["completed_stages"]
