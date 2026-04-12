"""Default research pipeline stages.

Skeleton stages exist for pipeline orchestration testing (Plan 2). Real stage
implementations arrive progressively starting in Plan 3. The four Plan 3 stages
(literature_review, plan_formulation, report_writing, peer_review) are now real
implementations imported from their own modules.

Skeleton output is intentionally empty. Returning typed placeholder data
(e.g., a string for dataset_code which requires list[str]) would crash the
LangGraph reducer; returning a dict with unknown keys (e.g., "papers") would
also fail because PipelineState keys are typed. The correct stub is `{}`.
"""

from __future__ import annotations

from agentlabx.core.registry import PluginRegistry, PluginType
from agentlabx.stages.base import BaseStage
from agentlabx.stages.data_exploration import DataExplorationStage
from agentlabx.stages.data_preparation import DataPreparationStage
from agentlabx.stages.experimentation import ExperimentationStage
from agentlabx.stages.literature_review import LiteratureReviewStage
from agentlabx.stages.peer_review import PeerReviewStage
from agentlabx.stages.plan_formulation import PlanFormulationStage
from agentlabx.stages.report_writing import ReportWritingStage
from agentlabx.stages.results_interpretation import ResultsInterpretationStage

__all__ = [
    "LiteratureReviewStage",
    "PlanFormulationStage",
    "DataExplorationStage",
    "DataPreparationStage",
    "ExperimentationStage",
    "ResultsInterpretationStage",
    "ReportWritingStage",
    "PeerReviewStage",
]


# Ordered list matching PipelineConfig.default_sequence
ALL_STAGES: list[type[BaseStage]] = [
    LiteratureReviewStage,
    PlanFormulationStage,
    DataExplorationStage,
    DataPreparationStage,
    ExperimentationStage,
    ResultsInterpretationStage,
    ReportWritingStage,
    PeerReviewStage,
]


def register_default_stages(registry: PluginRegistry) -> None:
    """Register all 8 default research stages in the given PluginRegistry."""
    for stage_cls in ALL_STAGES:
        registry.register(PluginType.STAGE, stage_cls.name, stage_cls)
