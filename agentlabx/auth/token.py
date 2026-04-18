from __future__ import annotations

import hashlib
import secrets
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone

from sqlalchemy import select

from agentlabx.auth.protocol import AuthError, Identity
from agentlabx.db.schema import Capability, User, UserToken
from agentlabx.db.session import DatabaseHandle


def _hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class IssuedToken:
    """Returned once on issue so the caller can display/store it."""

    id: str
    label: str
    token: str  # the plaintext token — never stored server-side


@dataclass(frozen=True)
class TokenRecord:
    """Server-side view of a token for listing."""

    id: str
    label: str
    created_at: datetime
    last_used_at: datetime | None


class TokenAuther:
    """Bearer-token auther. Token plaintext is returned once on issue and never stored."""

    name = "token"

    def __init__(self, db: DatabaseHandle) -> None:
        self._db = db

    async def issue(self, *, identity_id: str, label: str) -> IssuedToken:
        token = "ax_" + secrets.token_urlsafe(32)
        token_id = str(uuid.uuid4())
        async with self._db.session() as session:
            user = (
                await session.execute(select(User).where(User.id == identity_id))
            ).scalar_one_or_none()
            if user is None:
                raise AuthError("unknown identity")
            session.add(
                UserToken(
                    id=token_id,
                    user_id=identity_id,
                    token_hash=_hash_token(token),
                    label=label,
                )
            )
            await session.commit()
        return IssuedToken(id=token_id, label=label, token=token)

    async def list_for(self, *, identity_id: str) -> list[TokenRecord]:
        async with self._db.session() as session:
            rows = (
                await session.execute(
                    select(UserToken)
                    .where(UserToken.user_id == identity_id)
                    .order_by(UserToken.created_at.desc())
                )
            ).scalars().all()
        return [
            TokenRecord(
                id=r.id,
                label=r.label,
                created_at=r.created_at,
                last_used_at=r.last_used_at,
            )
            for r in rows
        ]

    async def delete(self, *, identity_id: str, token_id: str) -> None:
        """Hard-delete a token. Immediately invalidates it."""
        async with self._db.session() as session:
            row = (
                await session.execute(
                    select(UserToken).where(
                        UserToken.id == token_id, UserToken.user_id == identity_id
                    )
                )
            ).scalar_one_or_none()
            if row is None:
                raise AuthError("no such token")
            await session.delete(row)
            await session.commit()

    async def delete_all_for(self, *, identity_id: str) -> None:
        """Hard-delete all tokens for a user (e.g. on passphrase reset)."""
        async with self._db.session() as session:
            rows = (
                await session.execute(
                    select(UserToken).where(UserToken.user_id == identity_id)
                )
            ).scalars().all()
            for r in rows:
                await session.delete(r)
            await session.commit()

    async def refresh(self, *, identity_id: str, token_id: str) -> IssuedToken:
        """Delete an existing token and issue a new one with the same label."""
        async with self._db.session() as session:
            row = (
                await session.execute(
                    select(UserToken).where(
                        UserToken.id == token_id, UserToken.user_id == identity_id
                    )
                )
            ).scalar_one_or_none()
            if row is None:
                raise AuthError("no such token")
            label = row.label
            await session.delete(row)
            await session.commit()
        return await self.issue(identity_id=identity_id, label=label)

    async def authenticate(self, credentials: dict[str, str]) -> Identity:
        token = credentials.get("token")
        if token is None:
            raise AuthError("token required")
        async with self._db.session() as session:
            row = (
                await session.execute(
                    select(UserToken).where(UserToken.token_hash == _hash_token(token))
                )
            ).scalar_one_or_none()
            if row is None:
                raise AuthError("invalid token")
            row.last_used_at = datetime.now(tz=timezone.utc)
            user = (
                await session.execute(select(User).where(User.id == row.user_id))
            ).scalar_one()
            caps = (
                await session.execute(
                    select(Capability.capability).where(Capability.user_id == user.id)
                )
            ).scalars().all()
            await session.commit()
            return Identity(
                id=user.id,
                email=user.email,
                auther_name=self.name,
                display_name=user.display_name,
                capabilities=frozenset(caps),
            )
