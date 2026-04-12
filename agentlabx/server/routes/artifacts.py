"""Read-only endpoints for session state: artifacts, transitions, cost, hypotheses."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

router = APIRouter(prefix="/api/sessions", tags=["session-data"])


class ArtifactsResponse(BaseModel):
    literature_review: list[dict[str, Any]]
    plan: list[dict[str, Any]]
    data_exploration: list[dict[str, Any]]
    dataset_code: list[str]
    experiment_results: list[dict[str, Any]]
    interpretation: list[str]
    report: list[dict[str, Any]]
    review: list[dict[str, Any]]


class TransitionsResponse(BaseModel):
    transitions: list[dict[str, Any]]
    completed_stages: list[str]
    current_stage: str
    stage_iterations: dict[str, int]
    total_iterations: int


class CostResponse(BaseModel):
    total_tokens_in: int
    total_tokens_out: int
    total_cost: float


class HypothesesResponse(BaseModel):
    hypotheses: list[dict[str, Any]]
    total_records: int


async def _get_state(request: Request, session_id: str) -> dict[str, Any]:
    """Fetch current pipeline state for a session from the LangGraph checkpoint.

    Works for both running sessions and completed ones (Fix D + Fix C: the
    AsyncSqliteSaver checkpointer preserves state past task completion, and the
    executor keeps the graph handle in _running).
    """
    context = request.app.state.context
    executor = context.executor
    try:
        context.session_manager.get_session(session_id)
    except KeyError:
        raise HTTPException(status_code=404, detail="Session not found")

    if executor is None:
        return {}

    running = executor.get_running(session_id)
    if running is None:
        # Not currently running and never started — no state to show
        return {}

    config = {"configurable": {"thread_id": running.thread_id}}
    snapshot = await running.graph.aget_state(config)
    if snapshot is None:
        return {}
    values = snapshot.values if hasattr(snapshot, "values") else snapshot
    return dict(values) if values else {}


def _serialize(items: Any) -> Any:
    """Serialize Pydantic models to dicts, pass other values through."""
    if isinstance(items, list):
        return [_serialize(i) for i in items]
    if hasattr(items, "model_dump"):
        return items.model_dump()
    return items


@router.get("/{session_id}/artifacts", response_model=ArtifactsResponse)
async def list_artifacts(request: Request, session_id: str):
    """Return all stage outputs (lit reviews, plans, experiments, reports)."""
    state = await _get_state(request, session_id)
    return {
        "literature_review": _serialize(state.get("literature_review", [])),
        "plan": _serialize(state.get("plan", [])),
        "data_exploration": _serialize(state.get("data_exploration", [])),
        "dataset_code": _serialize(state.get("dataset_code", [])),
        "experiment_results": _serialize(state.get("experiment_results", [])),
        "interpretation": _serialize(state.get("interpretation", [])),
        "report": _serialize(state.get("report", [])),
        "review": _serialize(state.get("review", [])),
    }


@router.get("/{session_id}/transitions", response_model=TransitionsResponse)
async def list_transitions(request: Request, session_id: str):
    """Return the transition log and stage tracking info."""
    state = await _get_state(request, session_id)
    return {
        "transitions": _serialize(state.get("transition_log", [])),
        "completed_stages": state.get("completed_stages", []),
        "current_stage": state.get("current_stage", ""),
        "stage_iterations": state.get("stage_iterations", {}),
        "total_iterations": state.get("total_iterations", 0),
    }


@router.get("/{session_id}/cost", response_model=CostResponse)
async def get_cost(request: Request, session_id: str):
    """Return current LLM usage and cost for the session."""
    context = request.app.state.context
    try:
        context.session_manager.get_session(session_id)
    except KeyError:
        raise HTTPException(status_code=404, detail="Session not found")

    executor = context.executor
    if executor is None:
        return {"total_tokens_in": 0, "total_tokens_out": 0, "total_cost": 0.0}

    running = executor.get_running(session_id)
    if running is None:
        return {"total_tokens_in": 0, "total_tokens_out": 0, "total_cost": 0.0}

    tracker = running.cost_tracker
    return {
        "total_tokens_in": tracker.total_tokens_in,
        "total_tokens_out": tracker.total_tokens_out,
        "total_cost": tracker.total_cost,
    }


@router.get("/{session_id}/hypotheses", response_model=HypothesesResponse)
async def list_hypotheses(request: Request, session_id: str):
    """Return active hypotheses (latest record per ID — Fix H)."""
    from agentlabx.core.state import active_hypotheses

    state = await _get_state(request, session_id)
    raw_hypotheses = state.get("hypotheses", [])
    latest = active_hypotheses(raw_hypotheses)
    return {
        "hypotheses": _serialize(latest),
        "total_records": len(raw_hypotheses),  # Includes history
    }
