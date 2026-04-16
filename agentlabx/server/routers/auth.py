from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy import select

from agentlabx.auth.default import DefaultAuther
from agentlabx.auth.protocol import AuthError, EmailAlreadyRegisteredError, Identity
from agentlabx.auth.token import TokenAuther
from agentlabx.db.schema import Session as SessionRow
from agentlabx.db.session import DatabaseHandle
from agentlabx.events.bus import Event, EventBus
from agentlabx.models.api import (
    IdentityResponse,
    IssuedTokenResponse,
    IssueTokenRequest,
    LoginRequest,
    RegisterRequest,
    SessionResponse,
    TokenRecordResponse,
    UpdateDisplayNameRequest,
    UpdateEmailRequest,
    UpdatePassphraseRequest,
)
from agentlabx.server.dependencies import current_identity
from agentlabx.server.middleware import COOKIE_NAME, SessionConfig
from agentlabx.server.rate_limit import LoginRateLimiter

router = APIRouter(prefix="/api/auth", tags=["auth"])


def _current_session_id(request: Request) -> str | None:
    """Return the session ID from the request cookie, or None if absent / invalid."""
    cookie = request.cookies.get(COOKIE_NAME)
    if cookie is None:
        return None
    try:
        payload = request.state.session_serializer.loads(cookie)
    except Exception:
        return None
    if isinstance(payload, dict) and "sid" in payload:
        sid = payload["sid"]
        return str(sid) if isinstance(sid, str) else None
    return None


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
    limiter: LoginRateLimiter = request.state.login_limiter
    retry_after = limiter.check(payload.email)
    if retry_after is not None:
        await _emit(
            request,
            "auth.login_rate_limited",
            {"attempted_email": payload.email, "retry_after_seconds": int(retry_after)},
        )
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"too many failed attempts; retry in {int(retry_after)}s",
            headers={"Retry-After": str(int(retry_after))},
        )

    db: DatabaseHandle = request.state.db
    auther = DefaultAuther(db)
    try:
        identity = await auther.authenticate(
            {"email": payload.email, "passphrase": payload.passphrase}
        )
    except AuthError as exc:
        locked = limiter.record_failure(payload.email)
        await _emit(
            request,
            "auth.login_failed",
            {"attempted_email": payload.email},
        )
        if locked is not None:
            await _emit(
                request,
                "auth.login_rate_limited",
                {"attempted_email": payload.email, "retry_after_seconds": int(locked)},
            )
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail=f"too many failed attempts; retry in {int(locked)}s",
                headers={"Retry-After": str(int(locked))},
            ) from exc
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail=str(exc)
        ) from exc

    limiter.record_success(payload.email)

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


@router.get("/me/sessions", response_model=list[SessionResponse])
async def list_my_sessions(
    request: Request,
    identity: Identity = Depends(current_identity),
) -> list[SessionResponse]:
    db: DatabaseHandle = request.state.db
    current_sid = _current_session_id(request)
    async with db.session() as session:
        rows = (
            await session.execute(
                select(SessionRow)
                .where(SessionRow.user_id == identity.id, SessionRow.revoked == False)  # noqa: E712
                .order_by(SessionRow.last_seen_at.desc())
            )
        ).scalars().all()
    return [
        SessionResponse(
            id=r.id,
            issued_at=r.issued_at.isoformat(),
            expires_at=r.expires_at.isoformat(),
            last_seen_at=r.last_seen_at.isoformat(),
            is_current=(r.id == current_sid),
        )
        for r in rows
    ]


@router.delete("/me/sessions/{session_id}", status_code=status.HTTP_204_NO_CONTENT)
async def revoke_my_session(
    session_id: str,
    request: Request,
    response: Response,
    identity: Identity = Depends(current_identity),
) -> None:
    db: DatabaseHandle = request.state.db
    current_sid = _current_session_id(request)
    async with db.session() as session:
        row = (
            await session.execute(
                select(SessionRow).where(
                    SessionRow.id == session_id, SessionRow.user_id == identity.id
                )
            )
        ).scalar_one_or_none()
        if row is None:
            raise HTTPException(status_code=404, detail="no such session")
        row.revoked = True
        await session.commit()
    await _emit(
        request,
        "auth.session_revoked",
        {"actor_id": identity.id, "actor_email": identity.email, "session_id": session_id},
    )
    # If they just revoked their own current session, clear the cookie.
    if session_id == current_sid:
        response.delete_cookie(COOKIE_NAME)


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


@router.post(
    "/me/tokens", status_code=status.HTTP_201_CREATED, response_model=IssuedTokenResponse
)
async def issue_my_token(
    payload: IssueTokenRequest,
    request: Request,
    identity: Identity = Depends(current_identity),
) -> IssuedTokenResponse:
    db: DatabaseHandle = request.state.db
    ta = TokenAuther(db)
    issued = await ta.issue(identity_id=identity.id, label=payload.label)
    await _emit(
        request,
        "auth.token_issued",
        {
            "actor_id": identity.id,
            "actor_email": identity.email,
            "token_id": issued.id,
            "label": issued.label,
        },
    )
    return IssuedTokenResponse(id=issued.id, label=issued.label, token=issued.token)


@router.get("/me/tokens", response_model=list[TokenRecordResponse])
async def list_my_tokens(
    request: Request, identity: Identity = Depends(current_identity)
) -> list[TokenRecordResponse]:
    ta = TokenAuther(request.state.db)
    rows = await ta.list_for(identity_id=identity.id)
    return [
        TokenRecordResponse(
            id=r.id,
            label=r.label,
            created_at=r.created_at.isoformat(),
            last_used_at=r.last_used_at.isoformat() if r.last_used_at else None,
            revoked=r.revoked,
        )
        for r in rows
    ]


@router.delete(
    "/me/tokens/{token_id}", status_code=status.HTTP_204_NO_CONTENT
)
async def revoke_my_token(
    token_id: str,
    request: Request,
    identity: Identity = Depends(current_identity),
) -> None:
    ta = TokenAuther(request.state.db)
    try:
        await ta.revoke(identity_id=identity.id, token_id=token_id)
    except AuthError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    await _emit(
        request,
        "auth.token_revoked",
        {
            "actor_id": identity.id,
            "actor_email": identity.email,
            "token_id": token_id,
        },
    )
