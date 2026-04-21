from __future__ import annotations

from fastapi import HTTPException, Request, status

from agentlabx.auth.protocol import Identity


def is_admin(identity: Identity) -> bool:
    """Predicate: does ``identity`` carry the ``admin`` capability?

    Shared so router-level inline checks and dependency-level enforcement
    (:func:`require_admin`) cannot drift apart on the definition of "admin".
    """
    return "admin" in identity.capabilities


async def current_identity(request: Request) -> Identity:
    identity: Identity | None = getattr(request.state, "identity", None)
    if identity is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="not authenticated")
    return identity


async def require_admin(request: Request) -> Identity:
    identity = await current_identity(request)
    if not is_admin(identity):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="admin capability required"
        )
    return identity
