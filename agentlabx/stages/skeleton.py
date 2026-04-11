"""Skeleton implementations for all 8 default research pipeline stages."""

from __future__ import annotations

from agentlabx.core.registry import PluginRegistry, PluginType
from agentlabx.core.state import PipelineState
from agentlabx.stages.base import BaseStage, StageContext, StageResult


class LiteratureReviewStage(BaseStage):
    """Searches and summarises related work."""

    name = "literature_review"
    description = "Search and summarise related academic literature"
    required_agents = ["phd_student"]
    required_tools = ["arxiv_search", "semantic_scholar"]

    async def run(self, state: PipelineState, context: StageContext) -> StageResult:
        return StageResult(
            output={"papers": [], "summary": "Literature review placeholder"},
            status="done",
            reason="Literature review stage completed (skeleton)",
        )


class PlanFormulationStage(BaseStage):
    """Formulates a structured research plan and hypotheses."""

    name = "plan_formulation"
    description = "Formulate research plan, goals, and initial hypotheses"
    required_agents = ["pi_agent", "phd_student"]
    required_tools = []

    async def run(self, state: PipelineState, context: StageContext) -> StageResult:
        return StageResult(
            output={
                "goals": [],
                "methodology": "To be determined",
                "hypotheses": [],
            },
            status="done",
            reason="Plan formulation stage completed (skeleton)",
        )


class DataExplorationStage(BaseStage):
    """Performs exploratory data analysis on the target dataset."""

    name = "data_exploration"
    description = "Explore dataset structure, distributions, and quality"
    required_agents = ["phd_student"]
    required_tools = ["code_executor", "dataset_loader"]

    async def run(self, state: PipelineState, context: StageContext) -> StageResult:
        return StageResult(
            output={
                "findings": [],
                "data_quality_issues": [],
                "recommendations": [],
            },
            status="done",
            reason="Data exploration stage completed (skeleton)",
        )


class DataPreparationStage(BaseStage):
    """Cleans and prepares the dataset for experiments."""

    name = "data_preparation"
    description = "Clean, normalise, and prepare dataset for modelling"
    required_agents = ["phd_student"]
    required_tools = ["code_executor"]

    async def run(self, state: PipelineState, context: StageContext) -> StageResult:
        return StageResult(
            output={"dataset_code": "# placeholder preprocessing script"},
            status="done",
            reason="Data preparation stage completed (skeleton)",
        )


class ExperimentationStage(BaseStage):
    """Runs experiments and records results."""

    name = "experimentation"
    description = "Design and execute experiments to test hypotheses"
    required_agents = ["phd_student"]
    required_tools = ["code_executor", "experiment_tracker"]

    async def run(self, state: PipelineState, context: StageContext) -> StageResult:
        return StageResult(
            output={"experiment_results": []},
            status="done",
            reason="Experimentation stage completed (skeleton)",
        )


class ResultsInterpretationStage(BaseStage):
    """Interprets experiment results and updates hypotheses."""

    name = "results_interpretation"
    description = "Interpret results, update hypotheses, and identify next steps"
    required_agents = ["pi_agent", "phd_student"]
    required_tools = []

    async def run(self, state: PipelineState, context: StageContext) -> StageResult:
        return StageResult(
            output={"interpretation": "Results interpretation placeholder"},
            status="done",
            reason="Results interpretation stage completed (skeleton)",
        )


class ReportWritingStage(BaseStage):
    """Drafts and refines the research report."""

    name = "report_writing"
    description = "Write, structure, and refine the research paper"
    required_agents = ["phd_student"]
    required_tools = ["latex_compiler"]

    async def run(self, state: PipelineState, context: StageContext) -> StageResult:
        return StageResult(
            output={
                "latex_source": "% placeholder report",
                "sections": {},
            },
            status="done",
            reason="Report writing stage completed (skeleton)",
        )


class PeerReviewStage(BaseStage):
    """Simulates peer review of the completed paper."""

    name = "peer_review"
    description = "Simulate peer review: score, decide, and provide feedback"
    required_agents = ["reviewer_agent"]
    required_tools = []

    async def run(self, state: PipelineState, context: StageContext) -> StageResult:
        return StageResult(
            output={
                "decision": "accept",
                "scores": {},
                "feedback": "Peer review placeholder",
            },
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
