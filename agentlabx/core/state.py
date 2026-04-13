"""Typed pipeline state definitions for LangGraph."""

from __future__ import annotations

import operator
from datetime import datetime
from typing import Annotated, Any, Literal, TypedDict

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
    exit_code: int | None = None
    stdout: str | None = None
    stderr: str | None = None
    execution_time: float | None = None


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


class AgentMemoryRecord(TypedDict):
    working_memory: dict[str, Any]
    notes: list[str]
    last_active_stage: str
    turn_count: int


class ExperimentAttempt(TypedDict):
    attempt_id: str
    approach_summary: str
    outcome: Literal["success", "failure", "inconclusive"]
    failure_reason: str | None
    learnings: list[str]
    linked_hypothesis_id: str | None
    ts: datetime


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
    """Typed state for LangGraph pipeline.

    Fields use Annotated[list, operator.add] for accumulating values across nodes.
    LangGraph uses these reducer annotations to merge node outputs into state —
    without them, returning a list field from a node would overwrite rather than append.

    Fields that get overwritten per-node (current_stage, next_stage, etc.) use plain types.
    """

    # Identity (set once, never changes)
    session_id: str
    user_id: str
    research_topic: str

    # Accumulating stage outputs — appended via operator.add reducer
    hypotheses: Annotated[list[Hypothesis], operator.add]
    literature_review: Annotated[list[LitReviewResult], operator.add]
    plan: Annotated[list[ResearchPlan], operator.add]
    data_exploration: Annotated[list[EDAResult], operator.add]
    dataset_code: Annotated[list[str], operator.add]
    experiment_results: Annotated[list[ExperimentResult], operator.add]
    interpretation: Annotated[list[str], operator.add]
    report: Annotated[list[ReportResult], operator.add]
    review: Annotated[list[ReviewResult], operator.add]

    # Cross-stage requests — accumulating
    pending_requests: Annotated[list[CrossStageRequest], operator.add]
    completed_requests: Annotated[list[CrossStageRequest], operator.add]

    # Pipeline control — overwritten per-node
    current_stage: str
    stage_config: dict[str, Any]

    # Routing — overwritten per-node
    next_stage: str | None
    human_override: str | None
    default_sequence: list[str]

    # Tracking — completed_stages accumulates, others overwritten
    completed_stages: Annotated[list[str], operator.add]
    stage_iterations: dict[str, int]
    total_iterations: int
    max_stage_iterations: dict[str, int]
    max_total_iterations: int

    # History — all accumulating
    transition_log: Annotated[list[Transition], operator.add]
    review_feedback: Annotated[list[ReviewResult], operator.add]
    messages: Annotated[list[AgentMessage], operator.add]
    errors: Annotated[list[StageError], operator.add]

    # Cost tracker — overwritten (CostTracker has internal mutation via add_usage)
    cost_tracker: CostTracker

    # Observability (Plan 6)
    agent_memory: dict[str, AgentMemoryRecord]
    experiment_log: Annotated[list[ExperimentAttempt], operator.add]
    pi_decisions: Annotated[list[dict], operator.add]

    # Backtrack governance (Plan 7A)
    # Keys are "origin_stage->target_stage" strings; tuple keys aren't
    # JSON-serializable and LangGraph's checkpointer needs JSON-safe state.
    backtrack_attempts: dict[str, int]
    backtrack_cost_spent: float
    backtrack_feedback: str | None


def apply_partial_rollback(
    state: PipelineState, *, target: str, feedback: str | None
) -> dict[str, Any]:
    """Return a partial state update rewinding current_stage to `target`.

    Deliberately returns only the three keys to overwrite. LangGraph's
    node-return merge semantics leave every other field untouched —
    hypotheses, experiment_log, experiment_results, completed_stages,
    cost_tracker, and agent_memory are preserved.

    The returned `next_stage` IS the routing destination (the target). Callers
    in a LangGraph node should merge this update as-is; the subsequent
    conditional router reads `next_stage` to route to the target's stage node.

    Real labs don't forget what they've learned when they revisit an earlier
    stage (spec §3.3.2).
    """
    return {
        "current_stage": target,
        "next_stage": target,
        "backtrack_feedback": feedback,
    }


def active_hypotheses(hypotheses: list[Hypothesis]) -> list[Hypothesis]:
    """Return the latest hypothesis record per ID (last-write-wins by position).

    The hypotheses field uses `Annotated[list, operator.add]` so the
    results_interpretation stage's updates append rather than overwrite.
    Callers that want the current state of each hypothesis should use this
    helper instead of walking the raw list.
    """
    latest: dict[str, Hypothesis] = {}
    for h in hypotheses:
        latest[h.id] = h
    return list(latest.values())


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
        agent_memory={},
        experiment_log=[],
        pi_decisions=[],
        backtrack_attempts={},
        backtrack_cost_spent=0.0,
        backtrack_feedback=None,
    )
