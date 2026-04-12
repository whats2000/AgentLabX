"""Tests for real data preparation stage."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from agentlabx.agents.config_loader import AgentConfigLoader
from agentlabx.core.registry import PluginRegistry, PluginType
from agentlabx.core.state import EDAResult, ResearchPlan, create_initial_state
from agentlabx.providers.execution.subprocess_backend import SubprocessBackend
from agentlabx.providers.llm.mock_provider import MockLLMProvider
from agentlabx.stages.base import StageContext
from agentlabx.stages.data_preparation import DataPreparationStage
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
def state_with_eda():
    state = create_initial_state(session_id="s1", user_id="u1", research_topic="NLP")
    state["plan"] = [
        ResearchPlan(
            goals=["Classify text"],
            methodology="Fine-tune BERT",
            hypotheses=["H1"],
            full_text="full plan",
        )
    ]
    state["data_exploration"] = [
        EDAResult(
            findings=["100 rows, 3 columns"],
            data_quality_issues=[],
            recommendations=["Use stratified split", "Normalize text"],
        )
    ]
    return state


class TestDataPreparationStage:
    async def test_runs_end_to_end_success(self, registry, state_with_eda):
        """ML specifies requirements, SW writes working code."""
        provider = MockLLMProvider(
            responses=[
                "Need train/test split of 80/20, tokenize text field, labels as int.",
                json.dumps({"code": "print('preprocessing done')"}),
            ]
        )
        ctx = StageContext(
            settings={},
            event_bus=None,
            registry=registry,
            llm_provider=provider,
        )
        stage = DataPreparationStage()
        result = await stage.run(state_with_eda, ctx)
        assert result.status == "done"
        assert "dataset_code" in result.output
        assert len(result.output["dataset_code"]) == 1

    async def test_no_registry_backtrack(self):
        ctx = StageContext(settings={}, event_bus=None, registry=None)
        state = create_initial_state(session_id="s", user_id="u", research_topic="t")
        stage = DataPreparationStage()
        result = await stage.run(state, ctx)
        assert result.status == "backtrack"

    async def test_debug_attempt_on_failure(self, registry, state_with_eda):
        """When code fails, SW gets a debug attempt with the fixed code."""
        # First SW code raises an error, debug produces working code
        bad_code = "raise RuntimeError('intentional failure')"
        good_code = "print('fixed')"
        provider = MockLLMProvider(
            responses=[
                "Use a 70/30 split.",
                json.dumps({"code": bad_code}),
                json.dumps({"code": good_code}),
            ]
        )
        ctx = StageContext(
            settings={},
            event_bus=None,
            registry=registry,
            llm_provider=provider,
        )
        stage = DataPreparationStage()
        result = await stage.run(state_with_eda, ctx)
        # After debug, code is updated (even if validation re-run not done)
        assert result.status == "done"
        assert result.output["dataset_code"][0] == good_code

    async def test_malformed_json_no_code_backtracks(self, registry, state_with_eda):
        """If SW never produces valid JSON code, we backtrack."""
        provider = MockLLMProvider(
            responses=[
                "Need data split.",
                "not json at all",
                "still not json",
            ]
        )
        ctx = StageContext(
            settings={},
            event_bus=None,
            registry=registry,
            llm_provider=provider,
        )
        stage = DataPreparationStage()
        result = await stage.run(state_with_eda, ctx)
        assert result.status == "backtrack"

    async def test_stage_name(self):
        assert DataPreparationStage.name == "data_preparation"
