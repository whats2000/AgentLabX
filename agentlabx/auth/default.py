from __future__ import annotations

import uuid

from sqlalchemy import select

from agentlabx.auth.protocol import AuthError, Identity
from agentlabx.db.schema import Capability, User, UserConfig
from agentlabx.db.session import DatabaseHandle
from agentlabx.security.passwords import hash_passphrase, verify_passphrase

_PASSPHRASE_SLOT = "auth:default:passphrase_hash"


class DefaultAuther:
    """Passphrase-backed local auther. First registered identity is admin."""

    name = "default"

    def __init__(self, db: DatabaseHandle) -> None:
        self._db = db

    async def register(self, *, display_name: str, email: str, passphrase: str) -> Identity:
        normalized_email = email.strip().lower()
        user_id = str(uuid.uuid4())
        digest = hash_passphrase(passphrase)
        async with self._db.session() as session:
            user_count = (
                await session.execute(select(User).with_only_columns(User.id))
            ).all()
            user = User(
                id=user_id,
                display_name=display_name,
                email=normalized_email,
                auther_name=self.name,
            )
            session.add(user)
            ciphertext = digest.encode("utf-8")
            session.add(
                UserConfig(user_id=user_id, slot=_PASSPHRASE_SLOT, ciphertext=ciphertext)
            )
            caps: set[str] = set()
            if len(user_count) == 0:
                session.add(Capability(user_id=user_id, capability="admin"))
                caps.add("admin")
            await session.commit()
        return Identity(
            id=user_id,
            auther_name=self.name,
            display_name=display_name,
            email=normalized_email,
            capabilities=frozenset(caps),
        )

    async def authenticate(self, credentials: dict[str, str]) -> Identity:
        email = credentials.get("email")
        passphrase = credentials.get("passphrase")
        if email is None or passphrase is None:
            raise AuthError("email and passphrase required")
        normalized_email = email.strip().lower()
        async with self._db.session() as session:
            user = (
                await session.execute(select(User).where(User.email == normalized_email))
            ).scalar_one_or_none()
            if user is None or user.auther_name != self.name:
                raise AuthError("unknown identity")
            row = (
                await session.execute(
                    select(UserConfig).where(
                        UserConfig.user_id == user.id,
                        UserConfig.slot == _PASSPHRASE_SLOT,
                    )
                )
            ).scalar_one_or_none()
            if row is None:
                raise AuthError("no passphrase set")
            if not verify_passphrase(row.ciphertext.decode("utf-8"), passphrase):
                raise AuthError("wrong passphrase")
            caps = (
                await session.execute(
                    select(Capability.capability).where(Capability.user_id == user.id)
                )
            ).scalars().all()
            return Identity(
                id=user.id,
                auther_name=user.auther_name,
                display_name=user.display_name,
                email=user.email,
                capabilities=frozenset(caps),
            )
