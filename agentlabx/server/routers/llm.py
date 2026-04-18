from __future__ import annotations

import litellm
from fastapi import APIRouter, Depends

from agentlabx.auth.protocol import Identity
from agentlabx.models.api import ModelResponse, ProviderResponse
from agentlabx.server.dependencies import current_identity

router = APIRouter(prefix="/api/llm", tags=["llm"])


@router.get("/providers", response_model=list[ProviderResponse])
async def list_providers(
    identity: Identity = Depends(current_identity),
) -> list[ProviderResponse]:
    """Return all providers known to LiteLLM with their models."""
    result: list[ProviderResponse] = []
    for provider_name, model_set in sorted(litellm.models_by_provider.items()):
        models = [
            ModelResponse(id=m, display_name=m, provider=provider_name)
            for m in sorted(model_set)
        ]
        result.append(
            ProviderResponse(
                name=provider_name,
                display_name=provider_name,
                credential_slot=provider_name,
                models=models,
            )
        )
    return result


@router.get("/models", response_model=list[ModelResponse])
async def list_models(
    identity: Identity = Depends(current_identity),
) -> list[ModelResponse]:
    """Return all models known to LiteLLM."""
    result: list[ModelResponse] = []
    for provider_name, model_set in sorted(litellm.models_by_provider.items()):
        for m in sorted(model_set):
            result.append(
                ModelResponse(id=m, display_name=m, provider=provider_name)
            )
    return result
