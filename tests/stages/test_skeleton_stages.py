"""Tests for all 8 skeleton research pipeline stages."""

from __future__ import annotations

import pytest

from agentlabx.core.registry import PluginRegistry, PluginType
from agentlabx.core.state import create_initial_state
from agentlabx.stages.base import StageContext
from agentlabx.stages.skeleton import (
    ALL_STAGES,
    DataExplorationStage,
    DataPreparationStage,
    ExperimentationStage,
    LiteratureReviewStage,
    PeerReviewStage,
    PlanFormulationStage,
    ReportWritingStage,
    ResultsInterpretationStage,
    register_default_stages,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def state():
    return create_initial_state(session_id="s1", user_id="u1", research_topic="test")


@pytest.fixture()
def context():
    return StageContext(settings={}, event_bus=None, registry=None)


# ---------------------------------------------------------------------------
# Individual stage tests
# ---------------------------------------------------------------------------


class TestLiteratureReviewStage:
    async def test_runs_and_returns_done(self, state, context):
        result = await LiteratureReviewStage().run(state, context)
        assert result.status == "done"

    def test_name(self):
        assert LiteratureReviewStage.name == "literature_review"


class TestPlanFormulationStage:
    async def test_runs_and_returns_done(self, state, context):
        result = await PlanFormulationStage().run(state, context)
        assert result.status == "done"

    def test_name(self):
        assert PlanFormulationStage.name == "plan_formulation"


class TestDataExplorationStage:
    async def test_runs_and_returns_done(self, state, context):
        result = await DataExplorationStage().run(state, context)
        assert result.status == "done"

    def test_name(self):
        assert DataExplorationStage.name == "data_exploration"


class TestDataPreparationStage:
    async def test_runs_and_returns_done(self, state, context):
        result = await DataPreparationStage().run(state, context)
        assert result.status == "done"

    def test_name(self):
        assert DataPreparationStage.name == "data_preparation"


class TestExperimentationStage:
    async def test_runs_and_returns_done(self, state, context):
        result = await ExperimentationStage().run(state, context)
        assert result.status == "done"

    def test_name(self):
        assert ExperimentationStage.name == "experimentation"


class TestResultsInterpretationStage:
    async def test_runs_and_returns_done(self, state, context):
        result = await ResultsInterpretationStage().run(state, context)
        assert result.status == "done"

    def test_name(self):
        assert ResultsInterpretationStage.name == "results_interpretation"


class TestReportWritingStage:
    async def test_runs_and_returns_done(self, state, context):
        result = await ReportWritingStage().run(state, context)
        assert result.status == "done"

    def test_name(self):
        assert ReportWritingStage.name == "report_writing"


class TestPeerReviewStage:
    async def test_runs_and_returns_done(self, state, context):
        result = await PeerReviewStage().run(state, context)
        assert result.status == "done"

    def test_name(self):
        assert PeerReviewStage.name == "peer_review"


# ---------------------------------------------------------------------------
# Cross-stage invariant tests
# ---------------------------------------------------------------------------


class TestSkeletonStageInvariants:
    def test_all_stages_have_unique_names(self):
        names = [cls.name for cls in ALL_STAGES]
        assert len(names) == len(set(names)), "Stage names must be unique"

    def test_all_eight_stages_present(self):
        assert len(ALL_STAGES) == 8

    def test_all_stages_have_descriptions(self):
        for cls in ALL_STAGES:
            assert cls.description, f"{cls.name} missing description"

    def test_all_stages_have_required_agents_list(self):
        for cls in ALL_STAGES:
            assert isinstance(cls.required_agents, list), f"{cls.name}.required_agents not a list"

    def test_all_stages_have_required_tools_list(self):
        for cls in ALL_STAGES:
            assert isinstance(cls.required_tools, list), f"{cls.name}.required_tools not a list"

    async def test_all_stages_run_successfully(self, state, context):
        for cls in ALL_STAGES:
            result = await cls().run(state, context)
            assert result.status == "done", f"{cls.name} did not return status='done'"

    def test_names_match_default_sequence(self):
        from agentlabx.core.config import PipelineConfig

        expected = PipelineConfig().default_sequence
        actual = [cls.name for cls in ALL_STAGES]
        assert actual == expected


# ---------------------------------------------------------------------------
# Registry tests
# ---------------------------------------------------------------------------


class TestRegisterDefaultStages:
    def test_all_stages_registered(self):
        registry = PluginRegistry()
        register_default_stages(registry)
        plugins = registry.list_plugins(PluginType.STAGE)
        assert len(plugins) == 8

    def test_each_stage_name_resolvable(self):
        registry = PluginRegistry()
        register_default_stages(registry)
        for cls in ALL_STAGES:
            resolved = registry.resolve(PluginType.STAGE, cls.name)
            assert resolved is cls

    def test_register_twice_raises(self):
        registry = PluginRegistry()
        register_default_stages(registry)
        with pytest.raises(ValueError, match="already registered"):
            register_default_stages(registry)

    def test_register_twice_with_override(self):
        registry = PluginRegistry()
        register_default_stages(registry)
        # Should succeed when using override=True
        for cls in ALL_STAGES:
            registry.register(PluginType.STAGE, cls.name, cls, override=True)
        assert len(registry.list_plugins(PluginType.STAGE)) == 8
