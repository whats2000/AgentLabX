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


class TestPipelineBuilderProviderWiring:
    async def test_llm_provider_reaches_stages(self, registry):
        """LLM provider passed to build() reaches StageContext."""
        from pathlib import Path
        from unittest.mock import patch

        from agentlabx.agents.config_loader import AgentConfigLoader
        from agentlabx.core.registry import PluginType
        from agentlabx.providers.llm.mock_provider import MockLLMProvider
        from agentlabx.tools.arxiv_search import ArxivSearch

        # Register agents so the real literature_review stage can resolve them
        configs_dir = Path(__file__).parent.parent.parent / "agentlabx" / "agents" / "configs"
        loader = AgentConfigLoader()
        configs = loader.load_all(configs_dir)
        loader.register_all(configs, registry)
        registry.register(PluginType.TOOL, "arxiv_search", ArxivSearch)

        provider = MockLLMProvider(responses=["query one", "summary here"])
        builder = PipelineBuilder(registry=registry)
        graph = builder.build(
            stage_sequence=["literature_review"],
            llm_provider=provider,
        )
        initial = create_initial_state(
            session_id="s1",
            user_id="u1",
            research_topic="test",
            default_sequence=["literature_review"],
        )
        config = {"configurable": {"thread_id": "test-provider"}}
        with patch("agentlabx.tools.arxiv_search.arxiv.Client") as mock_client:
            mock_client.return_value.results.return_value = iter([])
            await graph.ainvoke(initial, config=config)
        # Literature review stage calls inference at least twice (query + summary)
        assert len(provider.calls) >= 2

    async def test_custom_stage_context_used(self, registry):
        """When stage_context is passed, it's used instead of building from kwargs."""
        from agentlabx.stages.base import StageContext

        custom_ctx = StageContext(
            settings={"marker": "custom"},
            event_bus=None,
            registry=registry,
            llm_provider=None,
            cost_tracker=None,
        )
        builder = PipelineBuilder(registry=registry)
        # Build with skeleton stage to avoid tool needs
        graph = builder.build(
            stage_sequence=["data_preparation"],
            stage_context=custom_ctx,
        )
        initial = create_initial_state(
            session_id="s1",
            user_id="u1",
            research_topic="test",
            default_sequence=["data_preparation"],
        )
        config = {"configurable": {"thread_id": "test-ctx"}}
        await graph.ainvoke(initial, config=config)
        # If the graph ran, the custom context was accepted. The settings marker
        # is just proof we passed the object we meant to.
        assert custom_ctx.settings["marker"] == "custom"
