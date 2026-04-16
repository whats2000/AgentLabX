from __future__ import annotations

import json

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy import select

from agentlabx.auth.default import DefaultAuther
from agentlabx.auth.protocol import EmailAlreadyRegisteredError, Identity
from agentlabx.config.settings import AppSettings
from agentlabx.db.schema import Capability, User, UserConfig
from agentlabx.db.session import DatabaseHandle
from agentlabx.events.bus import Event, EventBus
from agentlabx.models.api import (
    AdminUserResponse,
    CredentialSlotResponse,
    EventResponse,
    GrantCapabilityRequest,
    RegisterRequest,
    StoreCredentialRequest,
)
from agentlabx.security.fernet_store import FernetStore
from agentlabx.server.dependencies import current_identity, require_admin

router = APIRouter(prefix="/api/settings", tags=["settings"])

_USER_KEY_PREFIX = "user:key:"


def _user_slot(slot: str) -> str:
    return f"{_USER_KEY_PREFIX}{slot}"


async def _emit(
    request: Request,
    kind: str,
    payload: dict[str, str | int | float | bool | None],
) -> None:
    bus: EventBus = request.state.events
    await bus.emit(Event(kind=kind, payload=payload))


@router.get("/credentials", response_model=list[CredentialSlotResponse])
async def list_credentials(
    request: Request, identity: Identity = Depends(current_identity)
) -> list[CredentialSlotResponse]:
    db: DatabaseHandle = request.state.db
    async with db.session() as session:
        rows = (
            await session.execute(
                select(UserConfig).where(
                    UserConfig.user_id == identity.id,
                    UserConfig.slot.like(f"{_USER_KEY_PREFIX}%"),
                )
            )
        ).scalars().all()
    return [
        CredentialSlotResponse(
            slot=r.slot.removeprefix(_USER_KEY_PREFIX), updated_at=r.updated_at.isoformat()
        )
        for r in rows
    ]


@router.put("/credentials/{slot}", status_code=status.HTTP_204_NO_CONTENT)
async def put_credential(
    slot: str,
    payload: StoreCredentialRequest,
    request: Request,
    identity: Identity = Depends(current_identity),
) -> None:
    db: DatabaseHandle = request.state.db
    crypto: FernetStore = request.state.crypto
    ciphertext = crypto.encrypt(payload.value.encode("utf-8"))
    async with db.session() as session:
        existing = (
            await session.execute(
                select(UserConfig).where(
                    UserConfig.user_id == identity.id,
                    UserConfig.slot == _user_slot(slot),
                )
            )
        ).scalar_one_or_none()
        if existing is not None:
            existing.ciphertext = ciphertext
        else:
            session.add(
                UserConfig(user_id=identity.id, slot=_user_slot(slot), ciphertext=ciphertext)
            )
        await session.commit()
    await _emit(
        request,
        "credential.stored",
        {"actor_id": identity.id, "actor_email": identity.email, "slot": slot},
    )


@router.delete("/credentials/{slot}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_credential(
    slot: str, request: Request, identity: Identity = Depends(current_identity)
) -> None:
    db: DatabaseHandle = request.state.db
    async with db.session() as session:
        row = (
            await session.execute(
                select(UserConfig).where(
                    UserConfig.user_id == identity.id,
                    UserConfig.slot == _user_slot(slot),
                )
            )
        ).scalar_one_or_none()
        if row is None:
            raise HTTPException(status_code=404, detail="no such slot")
        await session.delete(row)
        await session.commit()
    await _emit(
        request,
        "credential.deleted",
        {"actor_id": identity.id, "actor_email": identity.email, "slot": slot},
    )


@router.get("/credentials/{slot}/reveal")
async def reveal_credential(
    slot: str, request: Request, identity: Identity = Depends(current_identity)
) -> dict[str, str]:
    db: DatabaseHandle = request.state.db
    crypto: FernetStore = request.state.crypto
    async with db.session() as session:
        row = (
            await session.execute(
                select(UserConfig).where(
                    UserConfig.user_id == identity.id,
                    UserConfig.slot == _user_slot(slot),
                )
            )
        ).scalar_one_or_none()
        if row is None:
            raise HTTPException(status_code=404, detail="no such slot")
        return {"slot": slot, "value": crypto.decrypt(row.ciphertext).decode("utf-8")}


# --- admin-only endpoints ---


@router.get("/admin/users", response_model=list[AdminUserResponse])
async def list_users(
    request: Request, _: Identity = Depends(require_admin)
) -> list[AdminUserResponse]:
    db: DatabaseHandle = request.state.db
    async with db.session() as session:
        users = (await session.execute(select(User))).scalars().all()
        out: list[AdminUserResponse] = []
        for u in users:
            caps = (
                await session.execute(
                    select(Capability.capability).where(Capability.user_id == u.id)
                )
            ).scalars().all()
            out.append(
                AdminUserResponse(
                    id=u.id,
                    display_name=u.display_name,
                    email=u.email,
                    auther_name=u.auther_name,
                    capabilities=sorted(caps),
                )
            )
    return out


@router.post("/admin/users", response_model=AdminUserResponse, status_code=status.HTTP_201_CREATED)
async def create_user(
    payload: RegisterRequest,
    request: Request,
    admin: Identity = Depends(require_admin),
) -> AdminUserResponse:
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
        "admin.user_created",
        {
            "actor_id": admin.id,
            "actor_email": admin.email,
            "target_id": identity.id,
            "target_email": identity.email,
            "target_display_name": identity.display_name,
        },
    )
    return AdminUserResponse(
        id=identity.id,
        display_name=identity.display_name,
        email=identity.email,
        auther_name=identity.auther_name,
        capabilities=sorted(identity.capabilities),
    )


@router.post(
    "/admin/users/{user_id}/capabilities", status_code=status.HTTP_204_NO_CONTENT
)
async def grant_capability(
    user_id: str,
    payload: GrantCapabilityRequest,
    request: Request,
    admin: Identity = Depends(require_admin),
) -> None:
    db: DatabaseHandle = request.state.db
    async with db.session() as session:
        user = (
            await session.execute(select(User).where(User.id == user_id))
        ).scalar_one_or_none()
        if user is None:
            raise HTTPException(status_code=404, detail="no such user")
        existing = (
            await session.execute(
                select(Capability).where(
                    Capability.user_id == user_id, Capability.capability == payload.capability
                )
            )
        ).scalar_one_or_none()
        if existing is None:
            session.add(Capability(user_id=user_id, capability=payload.capability))
            await session.commit()
        target_email: str = user.email
    await _emit(
        request,
        "admin.capability_granted",
        {
            "actor_id": admin.id,
            "actor_email": admin.email,
            "target_id": user_id,
            "target_email": target_email,
            "capability": payload.capability,
        },
    )


@router.delete(
    "/admin/users/{user_id}", status_code=status.HTTP_204_NO_CONTENT
)
async def delete_user(
    user_id: str,
    request: Request,
    admin: Identity = Depends(require_admin),
) -> None:
    """Delete a user and cascade their configs/tokens/sessions/capabilities."""
    if user_id == admin.id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="cannot delete your own identity",
        )
    db: DatabaseHandle = request.state.db
    async with db.session() as session:
        user = (
            await session.execute(select(User).where(User.id == user_id))
        ).scalar_one_or_none()
        if user is None:
            raise HTTPException(status_code=404, detail="no such user")
        target_email: str = user.email
        await session.delete(user)
        await session.commit()
    await _emit(
        request,
        "admin.user_deleted",
        {
            "actor_id": admin.id,
            "actor_email": admin.email,
            "target_id": user_id,
            "target_email": target_email,
        },
    )


@router.delete(
    "/admin/users/{user_id}/capabilities/{capability}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def revoke_capability(
    user_id: str,
    capability: str,
    request: Request,
    admin: Identity = Depends(require_admin),
) -> None:
    """Revoke a capability from a user."""
    if user_id == admin.id and capability == "admin":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="cannot revoke your own admin capability",
        )
    db: DatabaseHandle = request.state.db
    async with db.session() as session:
        row = (
            await session.execute(
                select(Capability).where(
                    Capability.user_id == user_id,
                    Capability.capability == capability,
                )
            )
        ).scalar_one_or_none()
        if row is None:
            raise HTTPException(status_code=404, detail="capability not granted")
        user = (
            await session.execute(select(User).where(User.id == user_id))
        ).scalar_one_or_none()
        target_email: str = user.email if user is not None else ""
        await session.delete(row)
        await session.commit()
    await _emit(
        request,
        "admin.capability_revoked",
        {
            "actor_id": admin.id,
            "actor_email": admin.email,
            "target_id": user_id,
            "target_email": target_email,
            "capability": capability,
        },
    )


@router.delete("/admin/events", status_code=status.HTTP_204_NO_CONTENT)
async def clear_audit_log(
    request: Request,
    admin: Identity = Depends(require_admin),
) -> None:
    """Archive the JSONL audit log to a timestamped file, then emit the clear event
    so the clearing action becomes the first record of the new log."""
    from datetime import datetime, timezone

    settings: AppSettings = request.app.state.settings
    path = settings.audit_log_path
    if path.exists() and path.stat().st_size > 0:
        ts = datetime.now(tz=timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        archive = path.parent / f"audit.{ts}.cleared.jsonl"
        path.rename(archive)
    await _emit(
        request,
        "admin.audit_log_cleared",
        {"actor_id": admin.id, "actor_email": admin.email},
    )


@router.get("/admin/events", response_model=list[EventResponse])
async def list_events(
    request: Request,
    _: Identity = Depends(require_admin),
    limit: int = Query(200, ge=1, le=1000),
) -> list[EventResponse]:
    """Return the most recent N events from the JSONL audit log (newest first)."""
    from collections import deque

    settings: AppSettings = request.app.state.settings
    path = settings.audit_log_path
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8") as f:
        tail_lines: deque[str] = deque(f, maxlen=limit)
    events: list[EventResponse] = []
    for line in reversed(tail_lines):
        data = json.loads(line)
        events.append(
            EventResponse(kind=data["kind"], at=data["at"], payload=data["payload"])
        )
    return events
