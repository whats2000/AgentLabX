"""Tests for PipelineBuilder — LangGraph StateGraph assembly with dynamic routing."""

from __future__ import annotations

import pytest

from agentlabx.core.pipeline import PipelineBuilder
from agentlabx.core.registry import PluginRegistry
from agentlabx.core.state import create_initial_state
from agentlabx.stages.skeleton import register_default_stages


@pytest.fixture()
def registry():
    reg = PluginRegistry()
    register_default_stages(reg)
    return reg


@pytest.fixture()
def builder(registry):
    return PipelineBuilder(registry=registry)


class TestPipelineBuilder:
    def test_build_compiles_graph(self, builder):
        graph = builder.build(
            stage_sequence=["literature_review", "plan_formulation", "experimentation"],
        )
        assert graph is not None

    async def test_run_single_stage(self, builder):
        graph = builder.build(stage_sequence=["literature_review"])
        initial = create_initial_state(
            session_id="s1",
            user_id="u1",
            research_topic="MATH benchmark",
            default_sequence=["literature_review"],
        )
        config = {"configurable": {"thread_id": "test-1"}}
        result = await graph.ainvoke(initial, config=config)
        assert result["current_stage"] == "literature_review"
        assert result["total_iterations"] >= 1

    async def test_run_full_default_pipeline(self, builder):
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
        initial = create_initial_state(
            session_id="s1",
            user_id="u1",
            research_topic="MATH benchmark",
            default_sequence=sequence,
        )
        config = {"configurable": {"thread_id": "test-full"}}
        result = await graph.ainvoke(initial, config=config)
        assert result["total_iterations"] == len(sequence)

    async def test_stream_produces_events(self, builder):
        graph = builder.build(stage_sequence=["literature_review", "plan_formulation"])
        initial = create_initial_state(
            session_id="s1",
            user_id="u1",
            research_topic="test",
            default_sequence=["literature_review", "plan_formulation"],
        )
        config = {"configurable": {"thread_id": "test-stream"}}
        events = []
        async for event in graph.astream(initial, config=config):
            events.append(event)
        assert len(events) >= 2
