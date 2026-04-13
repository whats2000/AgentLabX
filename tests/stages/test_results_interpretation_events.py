"""Tests that ResultsInterpretationStage emits hypothesis_update events per applied change."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

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


@pytest.fixture()
def mock_event_bus():
    bus = MagicMock()
    bus.emit = AsyncMock()
    return bus


class TestResultsInterpretationEmitsEvents:
    async def test_emits_hypothesis_update_per_applied_change(
        self, registry, state_with_experiments, mock_event_bus
    ):
        """For each hypothesis the postdoc revises, a hypothesis_update event should fire."""
        final_json = json.dumps(
            {
                "interpretation": "CoT improved accuracy. H1 supported, H2 refuted.",
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
                        "new_status": "refuted",
                        "evidence": [
                            {
                                "experiment_result_index": 0,
                                "metric": "accuracy",
                                "value": 0.65,
                                "interpretation": "No hallucination metric measured",
                            }
                        ],
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
            event_bus=mock_event_bus,
            registry=registry,
            llm_provider=provider,
        )
        stage = ResultsInterpretationStage()
        result = await stage.run(state_with_experiments, ctx)

        assert result.status == "done"

        emitted_types = [c.args[0].type for c in mock_event_bus.emit.await_args_list]
        assert "hypothesis_update" in emitted_types, (
            f"Expected 'hypothesis_update' in emitted events, got: {emitted_types}"
        )

        update_events = [
            c.args[0]
            for c in mock_event_bus.emit.await_args_list
            if c.args[0].type == "hypothesis_update"
        ]
        # Two hypotheses were updated, so two events should have fired
        assert len(update_events) == 2

        hypothesis_ids = {e.data["hypothesis_id"] for e in update_events}
        assert hypothesis_ids == {"H1", "H2"}

        h1_event = next(e for e in update_events if e.data["hypothesis_id"] == "H1")
        assert h1_event.data["new_status"] == "supported"
        assert h1_event.data["new_status"] in {"active", "supported", "refuted", "abandoned"}

        h2_event = next(e for e in update_events if e.data["hypothesis_id"] == "H2")
        assert h2_event.data["new_status"] == "refuted"

    async def test_no_events_for_unknown_hypothesis_id(
        self, registry, state_with_experiments, mock_event_bus
    ):
        """No hypothesis_update event should be emitted for unknown IDs (they are skipped)."""
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
            event_bus=mock_event_bus,
            registry=registry,
            llm_provider=provider,
        )
        stage = ResultsInterpretationStage()
        await stage.run(state_with_experiments, ctx)

        emitted_types = [c.args[0].type for c in mock_event_bus.emit.await_args_list]
        assert "hypothesis_update" not in emitted_types

    async def test_event_source_is_postdoc(
        self, registry, state_with_experiments, mock_event_bus
    ):
        """hypothesis_update events should have source='postdoc'."""
        final_json = json.dumps(
            {
                "interpretation": "H1 is supported.",
                "hypothesis_updates": [
                    {
                        "id": "H1",
                        "new_status": "supported",
                        "evidence": [],
                    },
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
            event_bus=mock_event_bus,
            registry=registry,
            llm_provider=provider,
        )
        stage = ResultsInterpretationStage()
        await stage.run(state_with_experiments, ctx)

        update_events = [
            c.args[0]
            for c in mock_event_bus.emit.await_args_list
            if c.args[0].type == "hypothesis_update"
        ]
        assert len(update_events) == 1
        assert update_events[0].source == "postdoc"

    async def test_event_contains_evidence_link(
        self, registry, state_with_experiments, mock_event_bus
    ):
        """hypothesis_update event payload should contain evidence_link when provided."""
        evidence = {
            "experiment_result_index": 1,
            "metric": "accuracy",
            "value": 0.80,
            "interpretation": "Clearly better",
        }
        final_json = json.dumps(
            {
                "interpretation": "H1 supported with clear evidence.",
                "hypothesis_updates": [
                    {
                        "id": "H1",
                        "new_status": "supported",
                        "evidence": [evidence],
                    },
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
            event_bus=mock_event_bus,
            registry=registry,
            llm_provider=provider,
        )
        stage = ResultsInterpretationStage()
        await stage.run(state_with_experiments, ctx)

        update_events = [
            c.args[0]
            for c in mock_event_bus.emit.await_args_list
            if c.args[0].type == "hypothesis_update"
        ]
        assert len(update_events) == 1
        assert update_events[0].data["evidence_link"] == [evidence]
