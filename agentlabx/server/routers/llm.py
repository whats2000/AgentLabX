from __future__ import annotations

from fastapi import APIRouter, Depends, Request

from agentlabx.auth.protocol import Identity
from agentlabx.llm.catalog import ProviderCatalog
from agentlabx.models.api import ModelResponse, ProviderResponse
from agentlabx.server.dependencies import current_identity

router = APIRouter(prefix="/api/llm", tags=["llm"])


@router.get("/providers", response_model=list[ProviderResponse])
async def list_providers(
    request: Request,
    identity: Identity = Depends(current_identity),
) -> list[ProviderResponse]:
    catalog: ProviderCatalog = request.app.state.catalog
    return [
        ProviderResponse(
            name=p.name,
            display_name=p.display_name,
            credential_slot=p.credential_slot,
            models=[
                ModelResponse(id=m.id, display_name=m.display_name, provider=p.name)
                for m in p.models
            ],
        )
        for p in catalog.providers
    ]


@router.get("/models", response_model=list[ModelResponse])
async def list_models(
    request: Request,
    identity: Identity = Depends(current_identity),
) -> list[ModelResponse]:
    catalog: ProviderCatalog = request.app.state.catalog
    result: list[ModelResponse] = []
    for p in catalog.providers:
        for m in p.models:
            result.append(
                ModelResponse(id=m.id, display_name=m.display_name, provider=p.name)
            )
    return result
