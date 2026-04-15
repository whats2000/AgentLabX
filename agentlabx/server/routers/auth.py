from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy import select

from agentlabx.auth.default import DefaultAuther
from agentlabx.auth.protocol import AuthError, Identity
from agentlabx.db.schema import Session as SessionRow
from agentlabx.db.session import DatabaseHandle
from agentlabx.models.api import IdentityResponse, LoginRequest, RegisterRequest
from agentlabx.server.dependencies import current_identity
from agentlabx.server.middleware import COOKIE_NAME, SessionConfig

router = APIRouter(prefix="/api/auth", tags=["auth"])


def _identity_response(identity: Identity) -> IdentityResponse:
    return IdentityResponse(
        id=identity.id,
        display_name=identity.display_name,
        auther_name=identity.auther_name,
        capabilities=sorted(identity.capabilities),
    )


@router.post("/register", status_code=status.HTTP_201_CREATED, response_model=IdentityResponse)
async def register(payload: RegisterRequest, request: Request) -> IdentityResponse:
    db: DatabaseHandle = request.state.db
    auther = DefaultAuther(db)
    identity = await auther.register(
        display_name=payload.display_name, passphrase=payload.passphrase
    )
    return _identity_response(identity)


@router.post("/login", response_model=IdentityResponse)
async def login(payload: LoginRequest, request: Request, response: Response) -> IdentityResponse:
    db: DatabaseHandle = request.state.db
    auther = DefaultAuther(db)
    try:
        identity = await auther.authenticate(
            {"identity_id": payload.identity_id, "passphrase": payload.passphrase}
        )
    except AuthError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(exc)) from exc

    cfg: SessionConfig = request.state.session_config
    session_id = str(uuid.uuid4())
    async with db.session() as session:
        session.add(
            SessionRow(
                id=session_id,
                user_id=identity.id,
                expires_at=datetime.now(tz=timezone.utc) + timedelta(seconds=cfg.max_age_seconds),
            )
        )
        await session.commit()

    cookie_value = request.state.session_serializer.dumps({"sid": session_id})
    response.set_cookie(
        key=COOKIE_NAME,
        value=cookie_value,
        max_age=cfg.max_age_seconds,
        httponly=True,
        secure=cfg.secure,
        samesite="lax",
    )
    return _identity_response(identity)


@router.get("/me", response_model=IdentityResponse)
async def me(identity: Identity = Depends(current_identity)) -> IdentityResponse:
    return _identity_response(identity)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(request: Request, response: Response) -> Response:
    cookie = request.cookies.get(COOKIE_NAME)
    if cookie is not None:
        try:
            payload = request.state.session_serializer.loads(cookie)
        except Exception:
            payload = None
        if isinstance(payload, dict) and "sid" in payload:
            db: DatabaseHandle = request.state.db
            async with db.session() as session:
                row = (
                    await session.execute(
                        select(SessionRow).where(SessionRow.id == payload["sid"])
                    )
                ).scalar_one_or_none()
                if row is not None:
                    row.revoked = True
                    await session.commit()
    response.delete_cookie(COOKIE_NAME)
    return response
