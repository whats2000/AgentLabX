"""Session CRUD and lifecycle REST endpoints."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

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
