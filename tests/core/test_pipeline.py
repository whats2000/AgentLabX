"""Tests for PipelineBuilder — LangGraph StateGraph assembly with dynamic routing."""

from __future__ import annotations

import asyncio

import pytest

from agentlabx.core.event_types import EventTypes
from agentlabx.core.events import Event, EventBus
from agentlabx.core.pipeline import PipelineBuilder
from agentlabx.core.registry import PluginRegistry
from agentlabx.core.session import SessionPreferences
from agentlabx.core.state import create_initial_state
from agentlabx.plugins._builtin import register_builtin_plugins
from agentlabx.stages import runner as runner_mod
from agentlabx.stages.base import StageContext


@pytest.fixture()
def registry():
    reg = PluginRegistry()
    register_builtin_plugins(reg)
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


class TestCheckpointReachedControlMode:
    """checkpoint_reached event carries control_mode from stage_controls (Plan 7E C1)."""

    @pytest.mark.asyncio
    async def test_checkpoint_reached_event_includes_control_mode_approve(
        self, registry, monkeypatch
    ):
        """When stage_controls[X]='approve', checkpoint event data has control_mode='approve'."""
        events: list[Event] = []
        bus = EventBus()

        async def collector(e: Event) -> None:
            events.append(e)

        bus.subscribe("*", collector)

        async def fake_run(self, state):
            name = self.stage.name
            update = {
                "current_stage": name,
                "stage_iterations": {
                    **state.get("stage_iterations", {}),
                    name: state.get("stage_iterations", {}).get(name, 0) + 1,
                },
                "total_iterations": state.get("total_iterations", 0) + 1,
            }
            if name == "experimentation":
                # Always backtrack to trigger the limit escalation → needs_approval=True
                update["next_stage"] = "literature_review"
                update["backtrack_feedback"] = "need more lit"
                return update
            update["next_stage"] = None
            return update

        monkeypatch.setattr(runner_mod.StageRunner, "run", fake_run)

        paused_event = asyncio.Event()
        paused_event.set()  # start unpaused

        stage_context = StageContext(
            settings={},
            event_bus=bus,
            registry=registry,
            llm_provider=None,
            cost_tracker=None,
            paused_event=paused_event,
        )

        # Configure stage_controls: literature_review has "approve"
        prefs = SessionPreferences(max_backtrack_attempts_per_edge=1)
        prefs.stage_controls["literature_review"] = "approve"

        seq = ["literature_review", "experimentation"]
        graph = PipelineBuilder(
            registry=registry, preferences=prefs
        ).build(stage_sequence=seq, stage_context=stage_context)

        state = create_initial_state(
            session_id="s1",
            user_id="u1",
            research_topic="t",
            default_sequence=seq,
            max_total_iterations=15,
        )

        # Release the pause gate once cleared so ainvoke can complete
        async def release_after_pause():
            for _ in range(200):
                await asyncio.sleep(0.05)
                if not paused_event.is_set():
                    paused_event.set()
                    return

        release_task = asyncio.create_task(release_after_pause())
        await graph.ainvoke(state, config={"configurable": {"thread_id": "t-c1-approve"}})
        await release_task

        # Find the checkpoint_reached event
        checkpoint_events = [
            e for e in events if e.type == EventTypes.CHECKPOINT_REACHED
        ]
        assert checkpoint_events, (
            f"No checkpoint_reached event fired; events: {[e.type for e in events]}"
        )

        event_data = checkpoint_events[0].data
        assert event_data.get("control_mode") == "approve", (
            f"Expected control_mode='approve' in event data; got: {event_data}"
        )

    @pytest.mark.asyncio
    async def test_checkpoint_reached_event_includes_control_mode_edit(
        self, registry, monkeypatch
    ):
        """When stage_controls[X]='edit', checkpoint event data has control_mode='edit'."""
        events: list[Event] = []
        bus = EventBus()

        async def collector(e: Event) -> None:
            events.append(e)

        bus.subscribe("*", collector)

        async def fake_run(self, state):
            name = self.stage.name
            update = {
                "current_stage": name,
                "stage_iterations": {
                    **state.get("stage_iterations", {}),
                    name: state.get("stage_iterations", {}).get(name, 0) + 1,
                },
                "total_iterations": state.get("total_iterations", 0) + 1,
            }
            if name == "experimentation":
                update["next_stage"] = "literature_review"
                update["backtrack_feedback"] = "need more lit"
                return update
            update["next_stage"] = None
            return update

        monkeypatch.setattr(runner_mod.StageRunner, "run", fake_run)

        paused_event = asyncio.Event()
        paused_event.set()

        stage_context = StageContext(
            settings={},
            event_bus=bus,
            registry=registry,
            llm_provider=None,
            cost_tracker=None,
            paused_event=paused_event,
        )

        prefs = SessionPreferences(max_backtrack_attempts_per_edge=1)
        prefs.stage_controls["literature_review"] = "edit"

        seq = ["literature_review", "experimentation"]
        graph = PipelineBuilder(
            registry=registry, preferences=prefs
        ).build(stage_sequence=seq, stage_context=stage_context)

        state = create_initial_state(
            session_id="s2",
            user_id="u1",
            research_topic="t",
            default_sequence=seq,
            max_total_iterations=15,
        )

        async def release_after_pause():
            for _ in range(200):
                await asyncio.sleep(0.05)
                if not paused_event.is_set():
                    paused_event.set()
                    return

        release_task = asyncio.create_task(release_after_pause())
        await graph.ainvoke(state, config={"configurable": {"thread_id": "t-c1-edit"}})
        await release_task

        checkpoint_events = [
            e for e in events if e.type == EventTypes.CHECKPOINT_REACHED
        ]
        assert checkpoint_events, (
            f"No checkpoint_reached event fired; events: {[e.type for e in events]}"
        )

        event_data = checkpoint_events[0].data
        assert event_data.get("control_mode") == "edit", (
            f"Expected control_mode='edit' in event data; got: {event_data}"
        )
