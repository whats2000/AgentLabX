"""Tests for real experimentation stage."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from agentlabx.agents.config_loader import AgentConfigLoader
from agentlabx.core.registry import PluginRegistry, PluginType
from agentlabx.core.state import Hypothesis, ResearchPlan, create_initial_state
from agentlabx.providers.execution.subprocess_backend import SubprocessBackend
from agentlabx.providers.llm.mock_provider import MockLLMProvider
from agentlabx.stages.base import StageContext
from agentlabx.stages.experimentation import ExperimentationStage
from agentlabx.tools.code_executor import CodeExecutor

CONFIGS_DIR = Path(__file__).parent.parent.parent / "agentlabx" / "agents" / "configs"

# Simple scripts that print metrics JSON as their final line
BASELINE_CODE = 'import json; print(json.dumps({"metrics": {"accuracy": 0.65, "f1": 0.60}}))'
MAIN_BETTER_CODE = 'import json; print(json.dumps({"metrics": {"accuracy": 0.80, "f1": 0.78}}))'
MAIN_WORSE_CODE = 'import json; print(json.dumps({"metrics": {"accuracy": 0.60, "f1": 0.58}}))'
ABLATION_CODE = 'import json; print(json.dumps({"metrics": {"accuracy": 0.75, "f1": 0.72}}))'


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
def state_with_plan_and_hypotheses():
    state = create_initial_state(session_id="s1", user_id="u1", research_topic="CoT")
    state["plan"] = [
        ResearchPlan(
            goals=["Improve accuracy"],
            methodology="Chain-of-thought prompting",
            hypotheses=["CoT improves accuracy"],
            full_text="full plan",
        )
    ]
    state["hypotheses"] = [
        Hypothesis(
            id="H1",
            statement="CoT improves accuracy",
            status="active",
            created_at_stage="plan_formulation",
        )
    ]
    return state


class TestExperimentationStage:
    async def test_complete_baseline_main_ablation_with_improvement(
        self, registry, state_with_plan_and_hypotheses
    ):
        """Full flow: baseline → main (improvement) → ablation → done."""
        provider = MockLLMProvider(
            responses=[
                json.dumps(
                    {
                        "code": BASELINE_CODE,
                        "description": "baseline",
                        "metrics": {"accuracy": 0.65},
                    }
                ),
                json.dumps(
                    {
                        "code": MAIN_BETTER_CODE,
                        "description": "main CoT",
                        "metrics": {"accuracy": 0.80},
                    }
                ),
                json.dumps(
                    {
                        "code": ABLATION_CODE,
                        "description": "ablation no CoT",
                        "metrics": {"accuracy": 0.75},
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
        stage = ExperimentationStage()
        result = await stage.run(state_with_plan_and_hypotheses, ctx)
        assert result.status == "done"
        assert "experiment_results" in result.output
        assert len(result.output["experiment_results"]) == 3
        tags = [r.tag for r in result.output["experiment_results"]]
        assert "baseline" in tags
        assert "main" in tags
        assert "ablation" in tags

    async def test_no_registry_backtrack(self):
        ctx = StageContext(settings={}, event_bus=None, registry=None)
        state = create_initial_state(session_id="s", user_id="u", research_topic="t")
        stage = ExperimentationStage()
        result = await stage.run(state, ctx)
        assert result.status == "backtrack"

    async def test_missing_baseline_backtracks(self, registry, state_with_plan_and_hypotheses):
        """If the ML agent returns no valid code for baseline, backtrack."""
        provider = MockLLMProvider(
            responses=[
                json.dumps({"code": "", "description": "bad baseline", "metrics": {}}),
                json.dumps(
                    {
                        "code": MAIN_BETTER_CODE,
                        "description": "main",
                        "metrics": {"accuracy": 0.80},
                    }
                ),
                json.dumps(
                    {
                        "code": ABLATION_CODE,
                        "description": "ablation",
                        "metrics": {"accuracy": 0.75},
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
        stage = ExperimentationStage()
        result = await stage.run(state_with_plan_and_hypotheses, ctx)
        assert result.status == "backtrack"
        assert result.next_hint == "plan_formulation"

    async def test_positive_result_no_ablation_backtracks(
        self, registry, state_with_plan_and_hypotheses
    ):
        """Main improves baseline but no ablation → backtrack with hint=experimentation."""
        # Provide baseline + main(better) but ablation has no code
        provider = MockLLMProvider(
            responses=[
                json.dumps(
                    {
                        "code": BASELINE_CODE,
                        "description": "baseline",
                        "metrics": {"accuracy": 0.65},
                    }
                ),
                json.dumps(
                    {
                        "code": MAIN_BETTER_CODE,
                        "description": "main",
                        "metrics": {"accuracy": 0.80},
                    }
                ),
                # ablation returns no code
                json.dumps({"code": "", "description": "ablation", "metrics": {}}),
            ]
        )
        ctx = StageContext(
            settings={},
            event_bus=None,
            registry=registry,
            llm_provider=provider,
        )
        stage = ExperimentationStage()
        result = await stage.run(state_with_plan_and_hypotheses, ctx)
        assert result.status == "backtrack"
        assert result.next_hint == "experimentation"

    async def test_no_improvement_negative_result(self, registry, state_with_plan_and_hypotheses):
        """Main does NOT improve over baseline → negative_result."""
        provider = MockLLMProvider(
            responses=[
                json.dumps(
                    {
                        "code": BASELINE_CODE,
                        "description": "baseline",
                        "metrics": {"accuracy": 0.65},
                    }
                ),
                json.dumps(
                    {
                        "code": MAIN_WORSE_CODE,
                        "description": "main worse",
                        "metrics": {"accuracy": 0.60},
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
        stage = ExperimentationStage()
        result = await stage.run(state_with_plan_and_hypotheses, ctx)
        assert result.status == "negative_result"

    async def test_code_execution_failure_handled(self, registry, state_with_plan_and_hypotheses):
        """Execution failure for a tier causes that tier to be skipped."""
        failing_code = "import this_module_does_not_exist"
        provider = MockLLMProvider(
            responses=[
                json.dumps(
                    {
                        "code": failing_code,
                        "description": "baseline fails",
                        "metrics": {},
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
        stage = ExperimentationStage()
        result = await stage.run(state_with_plan_and_hypotheses, ctx)
        # No baseline → backtrack
        assert result.status == "backtrack"

    async def test_stage_name(self):
        assert ExperimentationStage.name == "experimentation"
