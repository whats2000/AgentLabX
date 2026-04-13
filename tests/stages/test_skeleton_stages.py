"""Tests for the research pipeline stages registered via skeleton.py.

All 8 stages now have real implementations with dedicated test modules. This
file covers cross-stage invariants and registry registration tests.

Real stage test modules:
  tests/stages/test_literature_review_real.py
  tests/stages/test_plan_formulation_real.py
  tests/stages/test_report_writing_real.py
  tests/stages/test_peer_review_real.py
  tests/stages/test_data_exploration_real.py
  tests/stages/test_data_preparation_real.py
  tests/stages/test_experimentation_real.py
  tests/stages/test_results_interpretation_real.py
"""

from __future__ import annotations

import pytest

from agentlabx.core.registry import PluginRegistry, PluginType
from agentlabx.core.state import create_initial_state
from agentlabx.stages.base import StageContext
from agentlabx.plugins._builtin import register_builtin_plugins
from agentlabx.stages.skeleton import (
    ALL_STAGES,
    DataExplorationStage,
    DataPreparationStage,
    ExperimentationStage,
    ResultsInterpretationStage,
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

    async def test_real_stages_backtrack_without_registry(self, state, context):
        # All 8 stages are now real implementations and return "backtrack" without registry.
        real_stages = [
            DataExplorationStage,
            DataPreparationStage,
            ExperimentationStage,
            ResultsInterpretationStage,
        ]
        for cls in real_stages:
            result = await cls().run(state, context)
            assert result.status == "backtrack", (
                f"{cls.name} did not return status='backtrack' without registry"
            )

    def test_names_match_default_sequence(self):
        from agentlabx.core.config import PipelineConfig

        expected = PipelineConfig().default_sequence
        actual = [cls.name for cls in ALL_STAGES]
        assert actual == expected


# ---------------------------------------------------------------------------
# Registry tests
# ---------------------------------------------------------------------------


class TestRegisterBuiltinPlugins:
    def test_all_stages_registered(self):
        registry = PluginRegistry()
        register_builtin_plugins(registry)
        plugins = registry.list_plugins(PluginType.STAGE)
        # 8 default pipeline stages + LabMeeting (invocable-only)
        assert len(plugins) == 9

    def test_each_default_stage_name_resolvable(self):
        registry = PluginRegistry()
        register_builtin_plugins(registry)
        for cls in ALL_STAGES:
            resolved = registry.resolve(PluginType.STAGE, cls.name)
            assert resolved is cls

    def test_register_twice_raises(self):
        registry = PluginRegistry()
        register_builtin_plugins(registry)
        with pytest.raises(ValueError, match="already registered"):
            register_builtin_plugins(registry)

    def test_register_twice_with_override(self):
        registry = PluginRegistry()
        register_builtin_plugins(registry)
        # Should succeed when using override=True
        for cls in ALL_STAGES:
            registry.register(PluginType.STAGE, cls.name, cls, override=True)
        assert len(registry.list_plugins(PluginType.STAGE)) == 9
