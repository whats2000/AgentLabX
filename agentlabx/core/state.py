"""Typed pipeline state definitions for LangGraph."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal, TypedDict

from pydantic import BaseModel


class EvidenceLink(BaseModel):
    experiment_result_index: int
    metric: str
    value: float
    interpretation: str


class Hypothesis(BaseModel):
    id: str
    statement: str
    status: Literal["active", "supported", "refuted", "abandoned"]
    evidence_for: list[EvidenceLink] = []
    evidence_against: list[EvidenceLink] = []
    parent_hypothesis: str | None = None
    created_at_stage: str
    resolved_at_stage: str | None = None


class ReproducibilityRecord(BaseModel):
    random_seed: int
    environment_hash: str
    run_command: str
    container_image: str | None = None
    git_ref: str | None = None
    dependencies_snapshot: dict[str, str] = {}
    timestamp: datetime


class ExperimentResult(BaseModel):
    tag: Literal["baseline", "main", "ablation"]
    metrics: dict[str, float]
    description: str
    reproducibility: ReproducibilityRecord
    hypothesis_id: str | None = None
    code_path: str | None = None


class CrossStageRequest(BaseModel):
    from_stage: str
    to_stage: str
    request_type: str
    description: str
    status: Literal["pending", "in_progress", "completed", "cancelled"]
    result: Any | None = None


class CostTracker(BaseModel):
    total_tokens_in: int = 0
    total_tokens_out: int = 0
    total_cost: float = 0.0

    def add_usage(self, *, tokens_in: int, tokens_out: int, cost: float) -> None:
        self.total_tokens_in += tokens_in
        self.total_tokens_out += tokens_out
        self.total_cost += cost


class Transition(BaseModel):
    from_stage: str
    to_stage: str
    reason: str
    triggered_by: Literal["agent", "pi_agent", "human", "system"]
    timestamp: datetime


class AgentMessage(BaseModel):
    agent_name: str
    role: Literal["user", "assistant", "system", "tool"]
    content: str
    stage: str
    timestamp: datetime


class StageError(BaseModel):
    stage: str
    error_type: str
    message: str
    timestamp: datetime
    recovered: bool = False


class LitReviewResult(BaseModel):
    papers: list[dict[str, Any]]
    summary: str


class ResearchPlan(BaseModel):
    goals: list[str]
    methodology: str
    hypotheses: list[str]
    full_text: str


class EDAResult(BaseModel):
    findings: list[str]
    data_quality_issues: list[str]
    recommendations: list[str]


class ReportResult(BaseModel):
    latex_source: str
    sections: dict[str, str]
    compiled_pdf_path: str | None = None


class ReviewResult(BaseModel):
    decision: Literal["accept", "revise", "reject"]
    scores: dict[str, float]
    feedback: str
    reviewer_id: str


class PipelineState(TypedDict):
    session_id: str
    user_id: str
    research_topic: str
    hypotheses: list[Hypothesis]
    literature_review: list[LitReviewResult]
    plan: list[ResearchPlan]
    data_exploration: list[EDAResult]
    dataset_code: list[str]
    experiment_results: list[ExperimentResult]
    interpretation: list[str]
    report: list[ReportResult]
    review: list[ReviewResult]
    pending_requests: list[CrossStageRequest]
    completed_requests: list[CrossStageRequest]
    current_stage: str
    stage_config: dict[str, Any]
    next_stage: str | None
    human_override: str | None
    default_sequence: list[str]
    completed_stages: list[str]
    stage_iterations: dict[str, int]
    total_iterations: int
    max_stage_iterations: dict[str, int]
    max_total_iterations: int
    transition_log: list[Transition]
    review_feedback: list[ReviewResult]
    messages: list[AgentMessage]
    cost_tracker: CostTracker
    errors: list[StageError]


def create_initial_state(
    *,
    session_id: str,
    user_id: str,
    research_topic: str,
    default_sequence: list[str] | None = None,
    max_total_iterations: int = 50,
    max_stage_iterations: dict[str, int] | None = None,
) -> PipelineState:
    from agentlabx.core.config import PipelineConfig

    if default_sequence is None:
        default_sequence = PipelineConfig().default_sequence

    return PipelineState(
        session_id=session_id,
        user_id=user_id,
        research_topic=research_topic,
        hypotheses=[],
        literature_review=[],
        plan=[],
        data_exploration=[],
        dataset_code=[],
        experiment_results=[],
        interpretation=[],
        report=[],
        review=[],
        pending_requests=[],
        completed_requests=[],
        current_stage="",
        stage_config={},
        next_stage=None,
        human_override=None,
        default_sequence=default_sequence,
        completed_stages=[],
        stage_iterations={},
        total_iterations=0,
        max_stage_iterations=max_stage_iterations or {},
        max_total_iterations=max_total_iterations,
        transition_log=[],
        review_feedback=[],
        messages=[],
        cost_tracker=CostTracker(),
        errors=[],
    )
