from __future__ import annotations

import hashlib
import secrets

from sqlalchemy import select

from agentlabx.auth.protocol import AuthError, Identity
from agentlabx.db.schema import Capability, User, UserConfig
from agentlabx.db.session import DatabaseHandle

_TOKEN_SLOT_PREFIX = "auth:token:"


def _hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


class TokenAuther:
    """Bearer-token auther. Tokens are opaque; only hashes are stored."""

    name = "token"

    def __init__(self, db: DatabaseHandle) -> None:
        self._db = db

    async def issue(self, *, identity_id: str) -> str:
        token = "ax_" + secrets.token_urlsafe(32)
        async with self._db.session() as session:
            user = (
                await session.execute(select(User).where(User.id == identity_id))
            ).scalar_one_or_none()
            if user is None:
                raise AuthError("unknown identity")
            session.add(
                UserConfig(
                    user_id=identity_id,
                    slot=f"{_TOKEN_SLOT_PREFIX}{_hash_token(token)}",
                    ciphertext=b"active",
                )
            )
            await session.commit()
        return token

    async def revoke(self, token: str) -> None:
        slot = f"{_TOKEN_SLOT_PREFIX}{_hash_token(token)}"
        async with self._db.session() as session:
            row = (
                await session.execute(
                    select(UserConfig).where(UserConfig.slot == slot)
                )
            ).scalar_one_or_none()
            if row is not None:
                row.ciphertext = b"revoked"
                await session.commit()

    async def authenticate(self, credentials: dict[str, str]) -> Identity:
        token = credentials.get("token")
        if token is None:
            raise AuthError("token required")
        slot = f"{_TOKEN_SLOT_PREFIX}{_hash_token(token)}"
        async with self._db.session() as session:
            row = (
                await session.execute(
                    select(UserConfig).where(UserConfig.slot == slot)
                )
            ).scalar_one_or_none()
            if row is None or row.ciphertext != b"active":
                raise AuthError("invalid or revoked token")
            user = (
                await session.execute(select(User).where(User.id == row.user_id))
            ).scalar_one()
            caps = (
                await session.execute(
                    select(Capability.capability).where(Capability.user_id == user.id)
                )
            ).scalars().all()
            return Identity(
                id=user.id,
                auther_name=self.name,
                display_name=user.display_name,
                email=user.email,
                capabilities=frozenset(caps),
            )
