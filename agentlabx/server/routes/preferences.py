"""Live preference update endpoint — mode and per-stage controls."""

from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

router = APIRouter(prefix="/api/sessions", tags=["preferences"])


class PreferencesUpdateRequest(BaseModel):
    mode: Literal["auto", "hitl"] | None = None
    stage_controls: dict[str, Literal["auto", "notify", "approve", "edit"]] | None = None
    backtrack_control: Literal["auto", "notify", "approve"] | None = None


@router.patch("/{session_id}/preferences")
async def update_preferences(
    request: Request,
    session_id: str,
    body: PreferencesUpdateRequest,
):
    manager = request.app.state.context.session_manager
    try:
        session = manager.get_session(session_id)
    except KeyError:
        raise HTTPException(status_code=404, detail="Session not found")

    updates = body.model_dump(exclude_none=True)
    if updates:
        session.update_preferences(**updates)

    return {
        "session_id": session_id,
        "preferences": session.preferences.model_dump(),
    }
