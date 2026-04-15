from __future__ import annotations

from fastapi import APIRouter, Depends

from agentlabx.auth.protocol import Identity
from agentlabx.models.api import RunsListResponse
from agentlabx.server.dependencies import current_identity

router = APIRouter(prefix="/api/runs", tags=["runs"])


@router.get("", response_model=RunsListResponse)
async def list_runs(_: Identity = Depends(current_identity)) -> RunsListResponse:
    # Placeholder — A1 does not yet run stages. Later stages replace this.
    return RunsListResponse(runs=[])
