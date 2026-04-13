"""Default pipeline sequence constant.

Exposes `ALL_STAGES` — the ordered list of stage classes used as the default
pipeline sequence. Registration happens in `agentlabx.plugins._builtin`;
this module now exists solely to centralise the default sequence order and
to re-export stage classes for convenience imports in test code.
"""

from __future__ import annotations

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
