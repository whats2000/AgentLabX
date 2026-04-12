"""Tests for real results interpretation stage."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from agentlabx.agents.config_loader import AgentConfigLoader
from agentlabx.core.registry import PluginRegistry
from agentlabx.core.state import (
    ExperimentResult,
    Hypothesis,
    ReproducibilityRecord,
    create_initial_state,
)
from agentlabx.providers.llm.mock_provider import MockLLMProvider
from agentlabx.stages.base import StageContext
from agentlabx.stages.results_interpretation import ResultsInterpretationStage

CONFIGS_DIR = Path(__file__).parent.parent.parent / "agentlabx" / "agents" / "configs"


def _make_repro() -> ReproducibilityRecord:
    return ReproducibilityRecord(
        random_seed=42,
        environment_hash="abc",
        run_command="python run.py",
        timestamp=datetime.now(UTC),
    )


@pytest.fixture()
def registry() -> PluginRegistry:
    reg = PluginRegistry()
    loader = AgentConfigLoader()
    configs = loader.load_all(CONFIGS_DIR)
    loader.register_all(configs, reg)
    return reg


@pytest.fixture()
def state_with_experiments():
    state = create_initial_state(session_id="s1", user_id="u1", research_topic="CoT")
    state["hypotheses"] = [
        Hypothesis(
            id="H1",
            statement="CoT improves accuracy",
            status="active",
            created_at_stage="plan_formulation",
        ),
        Hypothesis(
            id="H2",
            statement="CoT reduces hallucination",
            status="active",
            created_at_stage="plan_formulation",
        ),
    ]
    state["experiment_results"] = [
        ExperimentResult(
            tag="baseline",
            metrics={"accuracy": 0.65},
            description="baseline",
            reproducibility=_make_repro(),
        ),
        ExperimentResult(
            tag="main",
            metrics={"accuracy": 0.80},
            description="main",
            reproducibility=_make_repro(),
        ),
    ]
    return state


class TestResultsInterpretationStage:
    async def test_hypothesis_status_supported(self, registry, state_with_experiments):
        """H1 is supported, H2 is inconclusive → check updated hypotheses."""
        final_json = json.dumps(
            {
                "interpretation": "CoT improved accuracy from 0.65 to 0.80 (H1 supported). "
                "H2 remains inconclusive without hallucination metrics.",
                "hypothesis_updates": [
                    {
                        "id": "H1",
                        "new_status": "supported",
                        "evidence": [
                            {
                                "experiment_result_index": 1,
                                "metric": "accuracy",
                                "value": 0.80,
                                "interpretation": "Main beat baseline by 15pp",
                            }
                        ],
                    },
                    {
                        "id": "H2",
                        "new_status": "active",
                        "evidence": [],
                    },
                ],
            }
        )
        provider = MockLLMProvider(
            responses=[
                "Postdoc draft: CoT clearly works for accuracy.",
                "PhD nuance: Small sample size limits generalization.",
                final_json,
            ]
        )
        ctx = StageContext(
            settings={},
            event_bus=None,
            registry=registry,
            llm_provider=provider,
        )
        stage = ResultsInterpretationStage()
        result = await stage.run(state_with_experiments, ctx)
        assert result.status == "done"
        assert "interpretation" in result.output
        assert len(result.output["interpretation"]) == 1
        assert "hypotheses" in result.output
        updated = {h.id: h for h in result.output["hypotheses"]}
        assert updated["H1"].status == "supported"
        assert len(updated["H1"].evidence_for) == 1
        assert updated["H1"].resolved_at_stage == "results_interpretation"
        assert updated["H2"].status == "active"
        assert updated["H2"].resolved_at_stage is None

    async def test_hypothesis_status_refuted(self, registry, state_with_experiments):
        final_json = json.dumps(
            {
                "interpretation": "CoT did not help. H1 refuted.",
                "hypothesis_updates": [
                    {
                        "id": "H1",
                        "new_status": "refuted",
                        "evidence": [
                            {
                                "experiment_result_index": 1,
                                "metric": "accuracy",
                                "value": 0.60,
                                "interpretation": "Main was worse than baseline",
                            }
                        ],
                    },
                ],
            }
        )
        provider = MockLLMProvider(
            responses=[
                "Draft: no improvement.",
                "Nuance: consider different seed.",
                final_json,
            ]
        )
        ctx = StageContext(
            settings={},
            event_bus=None,
            registry=registry,
            llm_provider=provider,
        )
        stage = ResultsInterpretationStage()
        result = await stage.run(state_with_experiments, ctx)
        assert result.status == "done"
        updated = {h.id: h for h in result.output["hypotheses"]}
        assert updated["H1"].status == "refuted"
        assert len(updated["H1"].evidence_against) == 1

    async def test_unknown_hypothesis_id_ignored(self, registry, state_with_experiments):
        """Unknown hypothesis IDs in updates should be silently skipped."""
        final_json = json.dumps(
            {
                "interpretation": "All good.",
                "hypothesis_updates": [
                    {"id": "H99", "new_status": "supported", "evidence": []},
                ],
            }
        )
        provider = MockLLMProvider(
            responses=[
                "Draft.",
                "PhD input.",
                final_json,
            ]
        )
        ctx = StageContext(
            settings={},
            event_bus=None,
            registry=registry,
            llm_provider=provider,
        )
        stage = ResultsInterpretationStage()
        result = await stage.run(state_with_experiments, ctx)
        assert result.status == "done"
        # No hypotheses updated (H99 doesn't exist)
        assert "hypotheses" not in result.output or len(result.output.get("hypotheses", [])) == 0

    async def test_malformed_json_falls_back_to_draft(self, registry, state_with_experiments):
        """If final JSON is malformed, interpretation uses draft + PhD concatenation."""
        provider = MockLLMProvider(
            responses=[
                "Postdoc draft text.",
                "PhD caveat text.",
                "not valid json at all",
            ]
        )
        ctx = StageContext(
            settings={},
            event_bus=None,
            registry=registry,
            llm_provider=provider,
        )
        stage = ResultsInterpretationStage()
        result = await stage.run(state_with_experiments, ctx)
        assert result.status == "done"
        interp = result.output["interpretation"][0]
        assert "Postdoc draft" in interp
        assert "PhD caveat" in interp

    async def test_no_registry_backtrack(self):
        ctx = StageContext(settings={}, event_bus=None, registry=None)
        state = create_initial_state(session_id="s", user_id="u", research_topic="t")
        stage = ResultsInterpretationStage()
        result = await stage.run(state, ctx)
        assert result.status == "backtrack"

    async def test_stage_name(self):
        assert ResultsInterpretationStage.name == "results_interpretation"
