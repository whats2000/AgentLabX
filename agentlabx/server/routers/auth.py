from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy import select

from agentlabx.auth.default import DefaultAuther
from agentlabx.auth.protocol import AuthError, EmailAlreadyRegisteredError, Identity
from agentlabx.db.schema import Session as SessionRow
from agentlabx.db.session import DatabaseHandle
from agentlabx.events.bus import Event, EventBus
from agentlabx.models.api import (
    IdentityResponse,
    LoginRequest,
    RegisterRequest,
    UpdateDisplayNameRequest,
    UpdateEmailRequest,
    UpdatePassphraseRequest,
)
from agentlabx.server.dependencies import current_identity
from agentlabx.server.middleware import COOKIE_NAME, SessionConfig

router = APIRouter(prefix="/api/auth", tags=["auth"])


def _identity_response(identity: Identity) -> IdentityResponse:
    return IdentityResponse(
        id=identity.id,
        display_name=identity.display_name,
        email=identity.email,
        auther_name=identity.auther_name,
        capabilities=sorted(identity.capabilities),
    )


async def _emit(
    request: Request,
    kind: str,
    payload: dict[str, str | int | float | bool | None],
) -> None:
    bus: EventBus = request.state.events
    await bus.emit(Event(kind=kind, payload=payload))


@router.post("/register", status_code=status.HTTP_201_CREATED, response_model=IdentityResponse)
async def register(payload: RegisterRequest, request: Request) -> IdentityResponse:
    db: DatabaseHandle = request.state.db
    auther = DefaultAuther(db)
    email = payload.email.strip().lower()
    try:
        identity = await auther.register(
            display_name=payload.display_name, email=email, passphrase=payload.passphrase
        )
    except EmailAlreadyRegisteredError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"email already registered: {email}",
        ) from exc
    await _emit(
        request,
        "auth.registered",
        {
            "actor_id": identity.id,
            "actor_email": identity.email,
            "display_name": identity.display_name,
        },
    )
    return _identity_response(identity)


@router.post("/login", response_model=IdentityResponse)
async def login(payload: LoginRequest, request: Request, response: Response) -> IdentityResponse:
    db: DatabaseHandle = request.state.db
    auther = DefaultAuther(db)
    try:
        identity = await auther.authenticate(
            {"email": payload.email, "passphrase": payload.passphrase}
        )
    except AuthError as exc:
        await _emit(
            request,
            "auth.login_failed",
            {"attempted_email": payload.email},
        )
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
    await _emit(
        request,
        "auth.login_success",
        {"actor_id": identity.id, "actor_email": identity.email},
    )
    return _identity_response(identity)


@router.get("/me", response_model=IdentityResponse)
async def me(identity: Identity = Depends(current_identity)) -> IdentityResponse:
    return _identity_response(identity)


@router.patch("/me/display-name", response_model=IdentityResponse)
async def update_display_name(
    payload: UpdateDisplayNameRequest,
    request: Request,
    identity: Identity = Depends(current_identity),
) -> IdentityResponse:
    db: DatabaseHandle = request.state.db
    auther = DefaultAuther(db)
    try:
        updated = await auther.update_display_name(
            identity_id=identity.id, new_display_name=payload.display_name
        )
    except AuthError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    await _emit(
        request,
        "auth.display_name_updated",
        {
            "actor_id": identity.id,
            "actor_email": identity.email,
            "new_display_name": payload.display_name,
        },
    )
    return _identity_response(updated)


@router.patch("/me/email", response_model=IdentityResponse)
async def update_email(
    payload: UpdateEmailRequest,
    request: Request,
    identity: Identity = Depends(current_identity),
) -> IdentityResponse:
    db: DatabaseHandle = request.state.db
    auther = DefaultAuther(db)
    old_email = identity.email
    try:
        updated = await auther.update_email(
            identity_id=identity.id,
            new_email=payload.new_email,
            passphrase=payload.passphrase,
        )
    except EmailAlreadyRegisteredError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"email already registered: {payload.new_email}",
        ) from exc
    except AuthError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(exc)) from exc
    await _emit(
        request,
        "auth.email_updated",
        {
            "actor_id": identity.id,
            "old_email": old_email,
            "new_email": updated.email,
        },
    )
    return _identity_response(updated)


@router.patch("/me/passphrase", response_model=IdentityResponse)
async def update_passphrase(
    payload: UpdatePassphraseRequest,
    request: Request,
    identity: Identity = Depends(current_identity),
) -> IdentityResponse:
    db: DatabaseHandle = request.state.db
    auther = DefaultAuther(db)
    try:
        updated = await auther.update_passphrase(
            identity_id=identity.id,
            old_passphrase=payload.old_passphrase,
            new_passphrase=payload.new_passphrase,
        )
    except AuthError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(exc)) from exc
    await _emit(
        request,
        "auth.passphrase_updated",
        {"actor_id": identity.id, "actor_email": identity.email},
    )
    return _identity_response(updated)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(request: Request, response: Response) -> None:
    identity: Identity | None = request.state.identity
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

    if identity is not None:
        await _emit(
            request,
            "auth.logout",
            {"actor_id": identity.id, "actor_email": identity.email},
        )
    else:
        await _emit(request, "auth.logout", {})
