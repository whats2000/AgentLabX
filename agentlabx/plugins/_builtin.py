"""Register all built-in plugins (stages, agents, tools) into a PluginRegistry.

This is the single entry point for wiring the default plugin set. Callers
(tests, the server app, CLI) call ``register_builtin_plugins(registry)`` once
at startup to populate a fresh registry with every built-in.
"""
from __future__ import annotations

from agentlabx.core.registry import PluginRegistry, PluginType
from agentlabx.stages.data_exploration import DataExplorationStage
from agentlabx.stages.data_preparation import DataPreparationStage
from agentlabx.stages.experimentation import ExperimentationStage
from agentlabx.stages.lab_meeting import LabMeeting
from agentlabx.stages.literature_review import LiteratureReviewStage
from agentlabx.stages.peer_review import PeerReviewStage
from agentlabx.stages.plan_formulation import PlanFormulationStage
from agentlabx.stages.report_writing import ReportWritingStage
from agentlabx.stages.results_interpretation import ResultsInterpretationStage

_BUILTIN_STAGES = [
    LiteratureReviewStage,
    PlanFormulationStage,
    DataExplorationStage,
    DataPreparationStage,
    ExperimentationStage,
    ResultsInterpretationStage,
    ReportWritingStage,
    PeerReviewStage,
    LabMeeting,
]


def register_builtin_plugins(registry: PluginRegistry) -> None:
    """Register all built-in stages (and future agents/tools) into *registry*."""
    for stage_cls in _BUILTIN_STAGES:
        registry.register(PluginType.STAGE, stage_cls.name, stage_cls)
