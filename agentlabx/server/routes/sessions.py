"""Session CRUD and lifecycle REST endpoints."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from agentlabx.agents.context import ContextAssembler
from agentlabx.core.registry import PluginType
from agentlabx.core.session import Session, SessionStatus

router = APIRouter(prefix="/api/sessions", tags=["sessions"])


class SessionCreateRequest(BaseModel):
    topic: str
    user_id: str = "default"
    config: dict[str, Any] = {}


class SessionSummary(BaseModel):
    session_id: str
    user_id: str
    research_topic: str
    status: str


class SessionDetail(SessionSummary):
    preferences: dict[str, Any]
    config_overrides: dict[str, Any]


class RedirectRequest(BaseModel):
    target_stage: str
    reason: str = ""


def _summarize(session: Session) -> SessionSummary:
    return SessionSummary(
        session_id=session.session_id,
        user_id=session.user_id,
        research_topic=session.research_topic,
        status=session.status.value,
    )


def _detail(session: Session) -> SessionDetail:
    return SessionDetail(
        session_id=session.session_id,
        user_id=session.user_id,
        research_topic=session.research_topic,
        status=session.status.value,
        preferences=session.preferences.model_dump(),
        config_overrides=session.config_overrides,
    )


@router.get("", response_model=list[SessionSummary])
async def list_sessions(request: Request, user_id: str | None = None):
    manager = request.app.state.context.session_manager
    if user_id:
        sessions = manager.list_sessions(user_id=user_id)
    else:
        sessions = manager.list_sessions()
    return [_summarize(s) for s in sessions]


@router.post("", response_model=SessionDetail, status_code=201)
async def create_session(request: Request, body: SessionCreateRequest):
    manager = request.app.state.context.session_manager
    session = manager.create_session(
        user_id=body.user_id,
        research_topic=body.topic,
        config_overrides=body.config,
    )
    return _detail(session)


@router.get("/{session_id}", response_model=SessionDetail)
async def get_session(request: Request, session_id: str):
    manager = request.app.state.context.session_manager
    try:
        session = manager.get_session(session_id)
    except KeyError:
        raise HTTPException(status_code=404, detail=f"Session '{session_id}' not found")
    return _detail(session)


@router.post("/{session_id}/start", status_code=202)
async def start_session(request: Request, session_id: str):
    context = request.app.state.context
    try:
        session = context.session_manager.get_session(session_id)
    except KeyError:
        raise HTTPException(status_code=404, detail="Session not found")

    if session.status != SessionStatus.CREATED:
        raise HTTPException(
            status_code=409,
            detail=f"Cannot start from '{session.status.value}'. Session must be CREATED.",
        )

    if context.executor is not None:
        await context.executor.start_session(session)
    else:
        # Fallback without executor: transition state only
        session.start()

    return {"session_id": session_id, "status": session.status.value}


@router.post("/{session_id}/pause", status_code=202)
async def pause_session(request: Request, session_id: str):
    context = request.app.state.context
    try:
        session = context.session_manager.get_session(session_id)
    except KeyError:
        raise HTTPException(status_code=404, detail="Session not found")

    if session.status != SessionStatus.RUNNING:
        raise HTTPException(
            status_code=409,
            detail=f"Cannot pause from '{session.status.value}'. Session must be RUNNING.",
        )

    if context.executor is not None:
        await context.executor.pause_session(session_id)
    else:
        session.pause()

    return {"session_id": session_id, "status": session.status.value}


@router.post("/{session_id}/resume", status_code=202)
async def resume_session(request: Request, session_id: str):
    context = request.app.state.context
    try:
        session = context.session_manager.get_session(session_id)
    except KeyError:
        raise HTTPException(status_code=404, detail="Session not found")

    if session.status != SessionStatus.PAUSED:
        raise HTTPException(
            status_code=409,
            detail=f"Cannot resume from '{session.status.value}'. Session must be PAUSED.",
        )

    if context.executor is not None:
        await context.executor.resume_session(session_id)
    else:
        session.resume()

    return {"session_id": session_id, "status": session.status.value}


@router.delete("/{session_id}", status_code=204)
async def delete_session(request: Request, session_id: str):
    """Delete a session and all its persisted state.

    If the session is running, cancel it first so the background task doesn't
    keep writing to the row we're about to delete. Idempotent — deleting an
    unknown session returns 204 rather than 404 so the frontend can retry
    safely.
    """
    context = request.app.state.context

    if context.executor is not None and context.executor.get_running(session_id) is not None:
        await context.executor.cancel_session(session_id)

    await context.session_manager.delete_session(session_id)
    return None


@router.post("/{session_id}/redirect", status_code=202)
async def redirect_session(request: Request, session_id: str, body: RedirectRequest):
    """Redirect the pipeline to a target stage. Session must be RUNNING (Fix I)."""
    context = request.app.state.context
    try:
        session = context.session_manager.get_session(session_id)
    except KeyError:
        raise HTTPException(status_code=404, detail="Session not found")

    # Fix I: reject when not running — otherwise we'd silently lose the redirect
    if session.status != SessionStatus.RUNNING:
        raise HTTPException(
            status_code=409,
            detail=(f"Cannot redirect from '{session.status.value}'. Session must be RUNNING."),
        )

    if context.executor is not None:
        await context.executor.redirect_session(
            session_id,
            body.target_stage,
            body.reason,
        )

    return {
        "session_id": session_id,
        "target_stage": body.target_stage,
        "reason": body.reason,
    }


# ---------------------------------------------------------------------------
# Observability endpoints (B11)
# ---------------------------------------------------------------------------


class TurnOut(BaseModel):
    turn_id: str
    parent_turn_id: str | None = None
    agent: str
    stage: str
    kind: str
    payload: dict
    system_prompt_hash: str | None = None
    tokens_in: int | None = None
    tokens_out: int | None = None
    cost_usd: float | None = None
    is_mock: bool
    ts: str


class HistoryOut(BaseModel):
    turns: list[TurnOut]
    next_cursor: str | None = None


async def _require_state(request: Request, session_id: str) -> dict[str, Any]:
    """Load latest checkpoint state for session, or raise 404.

    Mirrors the _get_state helper in artifacts.py: validates session exists,
    then pulls the LangGraph checkpoint snapshot through the executor handle.
    Returns an empty dict if the session has not been started yet (no snapshot).
    """
    context = request.app.state.context
    try:
        context.session_manager.get_session(session_id)
    except KeyError:
        raise HTTPException(status_code=404, detail=f"Session '{session_id}' not found")

    executor = context.executor
    if executor is None:
        return {}

    running = executor.get_running(session_id)
    if running is None:
        # Session exists but has never been started — no pipeline state yet.
        return {}

    config = {"configurable": {"thread_id": running.thread_id}}
    snapshot = await running.graph.aget_state(config)
    if snapshot is None:
        return {}
    values = snapshot.values if hasattr(snapshot, "values") else snapshot
    return dict(values) if values else {}


@router.get("/{session_id}/graph")
async def get_graph(session_id: str, request: Request):
    """Return the owned graph topology overlaid with runtime state."""
    from agentlabx.core.graph_mapper import build_topology

    context = request.app.state.context
    try:
        context.session_manager.get_session(session_id)
    except KeyError:
        raise HTTPException(status_code=404, detail=f"Session '{session_id}' not found")

    state = await _require_state(request, session_id)

    executor = context.executor
    running = executor.get_running(session_id) if executor is not None else None
    if running is None:
        # Session not started — use the pre-compiled default graph cached at
        # app startup; avoids rebuilding PipelineBuilder + compiling LangGraph
        # on every poll from the UI.
        return build_topology(context.default_graph, state, registry=context.registry)

    return build_topology(running.graph, state, registry=context.registry)


@router.get("/{session_id}/agents")
async def list_session_agents(session_id: str, request: Request):
    """List agents that have recorded memory entries in state, with registry metadata."""
    state = await _require_state(request, session_id)
    registry = request.app.state.context.registry
    out = []
    for name, rec in (state.get("agent_memory") or {}).items():
        try:
            cfg = registry.resolve(PluginType.AGENT, name)
            role = getattr(cfg, "role", name)
        except KeyError:
            role = name
        out.append(
            {
                "name": name,
                "role": role,
                "turn_count": rec.get("turn_count", 0),
                "last_active_stage": rec.get("last_active_stage"),
            }
        )
    return out


@router.get("/{session_id}/agents/{name}/context")
async def get_agent_context(session_id: str, name: str, request: Request):
    """Return the context view an agent would receive, based on its memory_scope."""
    state = await _require_state(request, session_id)
    registry = request.app.state.context.registry
    try:
        cfg = registry.resolve(PluginType.AGENT, name)
    except KeyError:
        raise HTTPException(status_code=404, detail=f"Agent '{name}' not found")

    scope = cfg.memory_scope
    assembler = ContextAssembler()
    preview = assembler.assemble(state, scope)
    return {
        "keys": sorted(preview.keys()),
        "preview": preview,
        "scope": {
            "read": list(scope.read),
            "summarize": dict(scope.summarize),
            "write": list(scope.write),
        },
    }


@router.get("/{session_id}/agents/{name}/history", response_model=HistoryOut)
async def get_agent_history(
    session_id: str,
    name: str,
    request: Request,
    limit: int = 200,
    after_ts: str | None = None,
):
    """Return paginated turn records for a specific agent in this session."""
    # Validate session exists first (storage query doesn't enforce this)
    context = request.app.state.context
    try:
        context.session_manager.get_session(session_id)
    except KeyError:
        raise HTTPException(status_code=404, detail=f"Session '{session_id}' not found")

    after = datetime.fromisoformat(after_ts) if after_ts else None
    rows = await context.storage.list_agent_turns(
        session_id, agent=name, after_ts=after, limit=limit
    )
    return HistoryOut(
        turns=[
            TurnOut(
                turn_id=r.turn_id,
                parent_turn_id=r.parent_turn_id,
                agent=r.agent,
                stage=r.stage,
                kind=r.kind,
                payload=r.payload,
                system_prompt_hash=r.system_prompt_hash,
                tokens_in=r.tokens_in,
                tokens_out=r.tokens_out,
                cost_usd=r.cost_usd,
                is_mock=r.is_mock,
                ts=r.ts.isoformat() if r.ts else "",
            )
            for r in rows
        ]
    )


@router.get("/{session_id}/stages/{stage_name}/history", response_model=HistoryOut)
async def get_stage_history(
    session_id: str,
    stage_name: str,
    request: Request,
    limit: int = 200,
    after_ts: str | None = None,
):
    """Return agent turns for a specific stage, aggregated across all agents.

    Used by ChatView's stage-grouped collapsible sections (Plan 7D T6) —
    when a user expands a stage panel, this returns all turns for that stage
    in chronological order, suitable for rendering as a conversation thread.

    Response: {"turns": [TurnOut, ...]} — same shape as
    /agents/{name}/history for frontend consistency.
    """
    context = request.app.state.context
    try:
        context.session_manager.get_session(session_id)
    except KeyError:
        raise HTTPException(status_code=404, detail=f"Session '{session_id}' not found")

    after = datetime.fromisoformat(after_ts) if after_ts else None
    rows = await context.storage.list_agent_turns(
        session_id, agent=None, stage=stage_name, after_ts=after, limit=limit
    )
    return HistoryOut(
        turns=[
            TurnOut(
                turn_id=r.turn_id,
                parent_turn_id=r.parent_turn_id,
                agent=r.agent,
                stage=r.stage,
                kind=r.kind,
                payload=r.payload,
                system_prompt_hash=r.system_prompt_hash,
                tokens_in=r.tokens_in,
                tokens_out=r.tokens_out,
                cost_usd=r.cost_usd,
                is_mock=r.is_mock,
                ts=r.ts.isoformat() if r.ts else "",
            )
            for r in rows
        ]
    )


@router.get("/{session_id}/agents/{name}/memory")
async def get_agent_memory(session_id: str, name: str, request: Request):
    """Return agent memory record from state, or empty defaults if not present."""
    state = await _require_state(request, session_id)
    rec = (state.get("agent_memory") or {}).get(name)
    return rec or {
        "working_memory": {},
        "notes": [],
        "last_active_stage": "",
        "turn_count": 0,
    }


@router.get("/{session_id}/pi/history")
async def get_pi_history(session_id: str, request: Request):
    """Return PI agent decision log from state."""
    state = await _require_state(request, session_id)
    return state.get("pi_decisions") or []


@router.get("/{session_id}/requests")
async def get_session_requests(session_id: str, request: Request):
    """Return pending and completed cross-stage requests."""
    state = await _require_state(request, session_id)

    def _ser(items: Any) -> list:
        out = []
        for item in items or []:
            if hasattr(item, "model_dump"):
                out.append(item.model_dump())
            elif isinstance(item, dict):
                out.append(item)
            else:
                out.append(str(item))
        return out

    return {
        "pending": _ser(state.get("pending_requests")),
        "completed": _ser(state.get("completed_requests")),
    }


@router.get("/{session_id}/stage_plans/{stage_name}")
async def get_stage_plans(session_id: str, stage_name: str, request: Request):
    """Return the versioned StagePlan history for a stage within a session.

    Response: {"stage_name": "<stage>", "plans": [<StagePlan>, ...]}
    The plans list is oldest→newest; the last entry is the latest plan.
    """
    context = request.app.state.context
    try:
        context.session_manager.get_session(session_id)
    except KeyError:
        raise HTTPException(status_code=404, detail=f"Session {session_id} not found")
    state = await _require_state(request, session_id)
    stage_plans = (state.get("stage_plans") or {}).get(stage_name, [])
    return {"stage_name": stage_name, "plans": stage_plans}


@router.get("/{session_id}/experiments")
async def get_session_experiments(session_id: str, request: Request):
    """Return experiment run results and the attempt log."""
    state = await _require_state(request, session_id)
    runs = []
    for idx, er in enumerate(state.get("experiment_results") or []):
        if hasattr(er, "model_dump"):
            runs.append({"index": idx, **er.model_dump()})
        elif isinstance(er, dict):
            runs.append({"index": idx, **er})
        else:
            runs.append({"index": idx})

    log = []
    for entry in state.get("experiment_log") or []:
        if hasattr(entry, "model_dump"):
            log.append(entry.model_dump())
        elif isinstance(entry, dict):
            log.append(entry)
        else:
            log.append(str(entry))

    return {"runs": runs, "log": log}
