"""Tests for real data exploration stage."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from agentlabx.agents.config_loader import AgentConfigLoader
from agentlabx.core.registry import PluginRegistry, PluginType
from agentlabx.core.state import ResearchPlan, create_initial_state
from agentlabx.providers.execution.subprocess_backend import SubprocessBackend
from agentlabx.providers.llm.mock_provider import MockLLMProvider
from agentlabx.stages.base import StageContext
from agentlabx.stages.data_exploration import DataExplorationStage
from agentlabx.tools.code_executor import CodeExecutor

CONFIGS_DIR = Path(__file__).parent.parent.parent / "agentlabx" / "agents" / "configs"


@pytest.fixture()
def registry() -> PluginRegistry:
    reg = PluginRegistry()
    loader = AgentConfigLoader()
    configs = loader.load_all(CONFIGS_DIR)
    loader.register_all(configs, reg)
    executor = CodeExecutor(backend=SubprocessBackend())
    reg.register(PluginType.TOOL, "code_executor", executor)
    return reg


@pytest.fixture()
def state_with_plan():
    state = create_initial_state(session_id="s1", user_id="u1", research_topic="MATH")
    state["plan"] = [
        ResearchPlan(
            goals=["Improve accuracy"],
            methodology="Use CoT prompting",
            hypotheses=["H1: CoT works"],
            full_text="full plan",
        )
    ]
    return state


class TestDataExplorationStage:
    async def test_runs_end_to_end(self, registry, state_with_plan):
        provider = MockLLMProvider(
            responses=[
                json.dumps(
                    {
                        "code": "print('shape: (100, 5)')\nprint('cols: a,b,c,d,e')",
                        "expected_outputs": ["shape", "cols"],
                    }
                ),
                json.dumps(
                    {
                        "findings": ["Dataset has 100 rows, 5 columns"],
                        "data_quality_issues": [],
                        "recommendations": ["Use stratified split"],
                    }
                ),
            ]
        )
        ctx = StageContext(
            settings={},
            event_bus=None,
            registry=registry,
            llm_provider=provider,
        )
        stage = DataExplorationStage()
        result = await stage.run(state_with_plan, ctx)
        assert result.status == "done"
        assert "data_exploration" in result.output
        eda = result.output["data_exploration"][0]
        assert len(eda.findings) > 0
        assert len(eda.recommendations) > 0

    async def test_no_registry_backtrack(self):
        ctx = StageContext(settings={}, event_bus=None, registry=None)
        state = create_initial_state(session_id="s", user_id="u", research_topic="t")
        stage = DataExplorationStage()
        result = await stage.run(state, ctx)
        assert result.status == "backtrack"

    async def test_malformed_json_returns_defaults(self, registry, state_with_plan):
        provider = MockLLMProvider(
            responses=[
                "not valid json",
                "also not valid json",
            ]
        )
        ctx = StageContext(
            settings={},
            event_bus=None,
            registry=registry,
            llm_provider=provider,
        )
        stage = DataExplorationStage()
        result = await stage.run(state_with_plan, ctx)
        assert result.status == "done"
        eda = result.output["data_exploration"][0]
        # Defaults apply — at least one finding
        assert len(eda.findings) >= 1

    async def test_stage_name(self):
        assert DataExplorationStage.name == "data_exploration"

    async def test_no_plan_in_state(self, registry):
        """Stage should work even with no plan in state."""
        provider = MockLLMProvider(
            responses=[
                json.dumps(
                    {
                        "code": "print('ok')",
                        "expected_outputs": ["ok"],
                    }
                ),
                json.dumps(
                    {
                        "findings": ["No plan provided but EDA ran"],
                        "data_quality_issues": [],
                        "recommendations": [],
                    }
                ),
            ]
        )
        state = create_initial_state(session_id="s1", user_id="u1", research_topic="NLP")
        ctx = StageContext(
            settings={},
            event_bus=None,
            registry=registry,
            llm_provider=provider,
        )
        stage = DataExplorationStage()
        result = await stage.run(state, ctx)
        assert result.status == "done"
