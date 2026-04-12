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
from agentlabx.core.state import PipelineState
from agentlabx.stages.base import BaseStage, StageContext, StageResult
from agentlabx.stages.literature_review import LiteratureReviewStage
from agentlabx.stages.peer_review import PeerReviewStage
from agentlabx.stages.plan_formulation import PlanFormulationStage
from agentlabx.stages.report_writing import ReportWritingStage

__all__ = [
    "LiteratureReviewStage",
    "PlanFormulationStage",
    "ReportWritingStage",
    "PeerReviewStage",
]


class DataExplorationStage(BaseStage):
    """Placeholder — real implementation in Plan 4+."""

    name = "data_exploration"
    description = "Explore dataset structure, distributions, and quality"
    required_agents = ["phd_student"]
    required_tools = ["code_executor", "dataset_loader"]

    async def run(self, state: PipelineState, context: StageContext) -> StageResult:
        return StageResult(
            output={},
            status="done",
            reason="Data exploration stage completed (skeleton)",
        )


class DataPreparationStage(BaseStage):
    """Placeholder — real implementation in Plan 4+."""

    name = "data_preparation"
    description = "Clean, normalise, and prepare dataset for modelling"
    required_agents = ["phd_student"]
    required_tools = ["code_executor"]

    async def run(self, state: PipelineState, context: StageContext) -> StageResult:
        return StageResult(
            output={},
            status="done",
            reason="Data preparation stage completed (skeleton)",
        )


class ExperimentationStage(BaseStage):
    """Placeholder — real implementation in Plan 4+."""

    name = "experimentation"
    description = "Design and execute experiments to test hypotheses"
    required_agents = ["phd_student"]
    required_tools = ["code_executor", "experiment_tracker"]

    async def run(self, state: PipelineState, context: StageContext) -> StageResult:
        return StageResult(
            output={},
            status="done",
            reason="Experimentation stage completed (skeleton)",
        )


class ResultsInterpretationStage(BaseStage):
    """Placeholder — real implementation in Plan 4+."""

    name = "results_interpretation"
    description = "Interpret results, update hypotheses, and identify next steps"
    required_agents = ["pi_agent", "phd_student"]
    required_tools = []

    async def run(self, state: PipelineState, context: StageContext) -> StageResult:
        return StageResult(
            output={},
            status="done",
            reason="Results interpretation stage completed (skeleton)",
        )


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
