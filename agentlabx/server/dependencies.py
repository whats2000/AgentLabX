from __future__ import annotations

from fastapi import HTTPException, Request, status

from agentlabx.auth.protocol import Identity


async def current_identity(request: Request) -> Identity:
    identity: Identity | None = getattr(request.state, "identity", None)
    if identity is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="not authenticated")
    return identity


async def require_admin(request: Request) -> Identity:
    identity = await current_identity(request)
    if "admin" not in identity.capabilities:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="admin capability required"
        )
    return identity
