"""Tests for ExperimentAttempt logging and ExperimentResult execution metadata."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from agentlabx.agents.config_loader import AgentConfigLoader
from agentlabx.core.registry import PluginRegistry, PluginType
from agentlabx.core.state import ExperimentResult, Hypothesis, ResearchPlan, create_initial_state
from agentlabx.providers.execution.subprocess_backend import SubprocessBackend
from agentlabx.providers.llm.mock_provider import MockLLMProvider
from agentlabx.stages.base import StageContext
from agentlabx.stages.experimentation import ExperimentationStage, _classify_outcome
from agentlabx.tools.code_executor import CodeExecutor

CONFIGS_DIR = Path(__file__).parent.parent.parent / "agentlabx" / "agents" / "configs"

BASELINE_CODE = 'import json; print(json.dumps({"metrics": {"accuracy": 0.65, "f1": 0.60}}))'
MAIN_BETTER_CODE = 'import json; print(json.dumps({"metrics": {"accuracy": 0.80, "f1": 0.78}}))'
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
def state_with_plan() -> dict:
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


def _make_ctx(registry: PluginRegistry, responses: list[str]) -> StageContext:
    provider = MockLLMProvider(responses=responses)
    return StageContext(
        settings={},
        event_bus=None,
        registry=registry,
        llm_provider=provider,
    )


@pytest.mark.asyncio
async def test_attempt_appended_per_run(registry, state_with_plan):
    """After run completes, experiment_log has entries with expected structure."""
    responses = [
        json.dumps({"code": BASELINE_CODE, "description": "baseline run", "metrics": {}}),
        json.dumps({"code": MAIN_BETTER_CODE, "description": "main CoT run", "metrics": {}}),
        json.dumps({"code": ABLATION_CODE, "description": "ablation run", "metrics": {}}),
    ]
    ctx = _make_ctx(registry, responses)
    stage = ExperimentationStage()
    state = dict(state_with_plan, experiment_log=[], experiment_results=[])

    await stage.run(state, ctx)
    log = state.get("experiment_log", [])

    assert len(log) >= 1, "experiment_log should be populated"
    attempt = log[0]
    assert "attempt_id" in attempt
    assert attempt["outcome"] in ("success", "failure", "inconclusive")
    assert "ts" in attempt
    assert "approach_summary" in attempt
    assert "learnings" in attempt
    assert isinstance(attempt["learnings"], list)


@pytest.mark.asyncio
async def test_experiment_result_carries_exit_code_and_stdout(registry, state_with_plan):
    """ExperimentResult now carries exit_code, stdout, stderr, execution_time."""
    responses = [
        json.dumps({"code": BASELINE_CODE, "description": "baseline run", "metrics": {}}),
        json.dumps({"code": MAIN_BETTER_CODE, "description": "main CoT run", "metrics": {}}),
        json.dumps({"code": ABLATION_CODE, "description": "ablation run", "metrics": {}}),
    ]
    ctx = _make_ctx(registry, responses)
    stage = ExperimentationStage()
    state = dict(state_with_plan, experiment_log=[], experiment_results=[])

    result = await stage.run(state, ctx)
    ers = result.output.get("experiment_results", [])
    assert len(ers) >= 1

    er = ers[0]
    assert hasattr(er, "exit_code"), "ExperimentResult must have exit_code field"
    assert hasattr(er, "stdout"), "ExperimentResult must have stdout field"
    assert hasattr(er, "stderr"), "ExperimentResult must have stderr field"
    assert hasattr(er, "execution_time"), "ExperimentResult must have execution_time field"
    # Subprocess backend returns exit_code=0 for success
    assert er.exit_code == 0
    # stdout contains the JSON metrics line
    assert er.stdout is not None
    assert "metrics" in er.stdout


@pytest.mark.asyncio
async def test_experiment_log_entry_count_matches_results(registry, state_with_plan):
    """experiment_log should have one entry per successful ExperimentResult."""
    responses = [
        json.dumps({"code": BASELINE_CODE, "description": "baseline run", "metrics": {}}),
        json.dumps({"code": MAIN_BETTER_CODE, "description": "main CoT run", "metrics": {}}),
        json.dumps({"code": ABLATION_CODE, "description": "ablation run", "metrics": {}}),
    ]
    ctx = _make_ctx(registry, responses)
    stage = ExperimentationStage()
    state = dict(state_with_plan, experiment_log=[], experiment_results=[])

    result = await stage.run(state, ctx)
    ers = result.output.get("experiment_results", [])
    log = state.get("experiment_log", [])

    assert len(log) == len(ers), "one ExperimentAttempt per ExperimentResult"


# Unit tests for _classify_outcome — no I/O needed

def _make_er(**kwargs) -> ExperimentResult:
    from datetime import UTC, datetime

    from agentlabx.core.state import ReproducibilityRecord

    repro = ReproducibilityRecord(
        random_seed=42,
        environment_hash="abc",
        run_command="python script.py",
        timestamp=datetime.now(UTC),
    )
    defaults = dict(
        tag="baseline",
        metrics={},
        description="test",
        reproducibility=repro,
    )
    defaults.update(kwargs)
    return ExperimentResult(**defaults)


def test_classify_outcome_success():
    er = _make_er(exit_code=0, metrics={"accuracy": 0.8})
    outcome, reason = _classify_outcome(er)
    assert outcome == "success"
    assert reason is None


def test_classify_outcome_failure_nonzero_exit():
    er = _make_er(exit_code=1, metrics={"accuracy": 0.8})
    outcome, reason = _classify_outcome(er)
    assert outcome == "failure"
    assert "1" in reason


def test_classify_outcome_inconclusive_no_metrics():
    er = _make_er(exit_code=0, metrics={})
    outcome, reason = _classify_outcome(er)
    assert outcome == "inconclusive"
    assert reason is not None


def test_classify_outcome_none_exit_code_treated_as_success():
    er = _make_er(exit_code=None, metrics={"f1": 0.7})
    outcome, reason = _classify_outcome(er)
    assert outcome == "success"
    assert reason is None
