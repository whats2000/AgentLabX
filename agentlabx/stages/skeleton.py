"""Skeleton implementations for all 8 default research pipeline stages.

These stages exist for pipeline orchestration testing. They return empty output
and status="done" so the pipeline flows through them without populating state.
Real stage implementations (with actual agent dialogue and tool use) arrive
progressively starting in Plan 3.

Skeleton output is intentionally empty. Returning typed placeholder data
(e.g., a string for dataset_code which requires list[str]) would crash the
LangGraph reducer; returning a dict with unknown keys (e.g., "papers") would
also fail because PipelineState keys are typed. The correct stub is `{}`.
"""

from __future__ import annotations

from agentlabx.core.registry import PluginRegistry, PluginType
from agentlabx.core.state import PipelineState
from agentlabx.stages.base import BaseStage, StageContext, StageResult


class LiteratureReviewStage(BaseStage):
    """Placeholder — real implementation in Plan 3."""

    name = "literature_review"
    description = "Search and summarise related academic literature"
    required_agents = ["phd_student"]
    required_tools = ["arxiv_search", "semantic_scholar"]

    async def run(self, state: PipelineState, context: StageContext) -> StageResult:
        return StageResult(
            output={},
            status="done",
            reason="Literature review stage completed (skeleton)",
        )


class PlanFormulationStage(BaseStage):
    """Placeholder — real implementation in Plan 3."""

    name = "plan_formulation"
    description = "Formulate research plan, goals, and initial hypotheses"
    required_agents = ["pi_agent", "phd_student"]
    required_tools = []

    async def run(self, state: PipelineState, context: StageContext) -> StageResult:
        return StageResult(
            output={},
            status="done",
            reason="Plan formulation stage completed (skeleton)",
        )


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


class ReportWritingStage(BaseStage):
    """Placeholder — real implementation in Plan 3."""

    name = "report_writing"
    description = "Write, structure, and refine the research paper"
    required_agents = ["phd_student"]
    required_tools = ["latex_compiler"]

    async def run(self, state: PipelineState, context: StageContext) -> StageResult:
        return StageResult(
            output={},
            status="done",
            reason="Report writing stage completed (skeleton)",
        )


class PeerReviewStage(BaseStage):
    """Placeholder — real implementation in Plan 3."""

    name = "peer_review"
    description = "Simulate peer review: score, decide, and provide feedback"
    required_agents = ["reviewer_agent"]
    required_tools = []

    async def run(self, state: PipelineState, context: StageContext) -> StageResult:
        return StageResult(
            output={},
            status="done",
            reason="Peer review stage completed (skeleton)",
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
