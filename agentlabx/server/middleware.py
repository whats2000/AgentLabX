from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import datetime, timezone

from fastapi import FastAPI, Request, Response
from itsdangerous import BadSignature, URLSafeTimedSerializer
from sqlalchemy import select

from agentlabx.auth.protocol import Identity
from agentlabx.db.schema import Capability, User
from agentlabx.db.schema import Session as SessionRow
from agentlabx.db.session import DatabaseHandle

COOKIE_NAME = "agentlabx_session"


@dataclass(frozen=True)
class SessionConfig:
    secret: bytes
    secure: bool  # True on LAN bind; False on loopback
    max_age_seconds: int = 60 * 60 * 12  # 12h
    remember_me_max_age_seconds: int = 60 * 60 * 24 * 30  # 30 days


def _decode_session_cookie(
    serializer: URLSafeTimedSerializer,
    cookie: str,
    cfg: SessionConfig,
) -> dict[str, str | bool] | None:
    """Decode and validate the session cookie with per-type max_age enforcement.

    Remember-me cookies (rm=true) are accepted up to remember_me_max_age_seconds;
    normal cookies are rejected by itsdangerous after max_age_seconds.
    """
    # First pass: accept with the longer remember-me window so we can read the payload.
    try:
        payload = serializer.loads(cookie, max_age=cfg.remember_me_max_age_seconds)
    except BadSignature:
        return None
    if not isinstance(payload, dict) or "sid" not in payload:
        return None
    # If not a remember-me cookie, re-validate with the stricter normal max_age.
    if not payload.get("rm"):
        try:
            serializer.loads(cookie, max_age=cfg.max_age_seconds)
        except BadSignature:
            return None
    return payload


def install_session_middleware(app: FastAPI, *, cfg: SessionConfig, db: DatabaseHandle) -> None:
    """Attach the session middleware with an eagerly-bound ``db`` handle.

    Used by the legacy ``async create_app`` path (test ASGI client) where
    the ``db`` handle exists at app-construction time. Production / Uvicorn
    setups should use :func:`install_session_middleware_lazy` instead — see
    its docstring for why.
    """

    serializer = URLSafeTimedSerializer(cfg.secret)

    @app.middleware("http")
    async def session_middleware(
        request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        return await _session_dispatch(
            request=request,
            call_next=call_next,
            cfg=cfg,
            serializer=serializer,
            db=db,
        )


def install_session_middleware_lazy(app: FastAPI, *, cfg: SessionConfig) -> None:
    """Attach session middleware that resolves ``db`` from ``app.state`` at request time.

    The ``async create_app`` path constructs the db handle synchronously
    in the caller's loop and binds it to a closure. Under Uvicorn that
    handle would be on a torn-down loop — every db access would fail.
    The lazy variant defers the binding until the first request fires, by
    which point the lifespan startup phase has populated
    ``app.state.db`` on Uvicorn's loop.
    """

    serializer = URLSafeTimedSerializer(cfg.secret)

    @app.middleware("http")
    async def session_middleware(
        request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        db: DatabaseHandle = request.app.state.db
        return await _session_dispatch(
            request=request,
            call_next=call_next,
            cfg=cfg,
            serializer=serializer,
            db=db,
        )


async def _session_dispatch(
    *,
    request: Request,
    call_next: Callable[[Request], Awaitable[Response]],
    cfg: SessionConfig,
    serializer: URLSafeTimedSerializer,
    db: DatabaseHandle,
) -> Response:
    request.state.identity = None
    request.state.session_config = cfg
    request.state.session_serializer = serializer
    request.state.session_remember_me = False
    request.state.db = db

    cookie = request.cookies.get(COOKIE_NAME)
    if cookie is not None:
        payload = _decode_session_cookie(serializer, cookie, cfg)
        if isinstance(payload, dict) and "sid" in payload:
            sid = payload["sid"]
            if isinstance(sid, str):
                identity = await _load_identity_for_session(db, sid)
                request.state.identity = identity
                request.state.session_remember_me = bool(payload.get("rm"))

    if request.state.identity is None:
        header = request.headers.get("Authorization", "")
        if header.startswith("Bearer "):
            token = header[len("Bearer ") :].strip()
            if token:
                request.state.identity = await _load_identity_for_bearer(db, token)

    return await call_next(request)


async def _load_identity_for_bearer(db: DatabaseHandle, token: str) -> Identity | None:
    from agentlabx.auth.protocol import AuthError
    from agentlabx.auth.token import TokenAuther

    try:
        return await TokenAuther(db).authenticate({"token": token})
    except AuthError:
        return None


async def _load_identity_for_session(db: DatabaseHandle, session_id: str) -> Identity | None:
    async with db.session() as session:
        row = (
            await session.execute(select(SessionRow).where(SessionRow.id == session_id))
        ).scalar_one_or_none()
        if row is None or row.revoked:
            return None
        expires_at = row.expires_at
        if expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=timezone.utc)
        if expires_at < datetime.now(tz=timezone.utc):
            return None
        user = (await session.execute(select(User).where(User.id == row.user_id))).scalar_one()
        caps = (
            (
                await session.execute(
                    select(Capability.capability).where(Capability.user_id == user.id)
                )
            )
            .scalars()
            .all()
        )
        row.last_seen_at = datetime.now(tz=timezone.utc)
        await session.commit()
        return Identity(
            id=user.id,
            auther_name=user.auther_name,
            display_name=user.display_name,
            email=user.email,
            capabilities=frozenset(caps),
        )
