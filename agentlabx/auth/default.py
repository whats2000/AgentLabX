from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from agentlabx.auth.protocol import AuthError, EmailAlreadyRegisteredError, Identity
from agentlabx.db.schema import Capability, User, UserConfig
from agentlabx.db.session import DatabaseHandle
from agentlabx.security.passwords import hash_passphrase, verify_passphrase

_PASSPHRASE_SLOT = "auth:default:passphrase_hash"


class DefaultAuther:
    """Passphrase-backed local auther. First registered identity is admin."""

    name = "default"

    def __init__(self, db: DatabaseHandle) -> None:
        self._db = db

    async def _load_identity(self, session: AsyncSession, user_id: str) -> Identity:
        """Re-query user + capabilities and return a fresh Identity."""
        user = (
            await session.execute(select(User).where(User.id == user_id))
        ).scalar_one_or_none()
        if user is None:
            raise AuthError("unknown identity")
        caps = (
            await session.execute(
                select(Capability.capability).where(Capability.user_id == user_id)
            )
        ).scalars().all()
        return Identity(
            id=user.id,
            auther_name=user.auther_name,
            display_name=user.display_name,
            email=user.email,
            capabilities=frozenset(caps),
        )

    async def register(self, *, display_name: str, email: str, passphrase: str) -> Identity:
        normalized_email = email.strip().lower()
        user_id = str(uuid.uuid4())
        digest = hash_passphrase(passphrase)
        async with self._db.session() as session:
            existing = (
                await session.execute(select(User).where(User.email == normalized_email))
            ).scalar_one_or_none()
            if existing is not None:
                raise EmailAlreadyRegisteredError(normalized_email)
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
                session.add(Capability(user_id=user_id, capability="owner"))
                caps.update({"admin", "owner"})
            try:
                await session.commit()
            except IntegrityError as exc:
                await session.rollback()
                raise EmailAlreadyRegisteredError(normalized_email) from exc
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
            return await self._load_identity(session, user.id)

    async def update_display_name(
        self, *, identity_id: str, new_display_name: str
    ) -> Identity:
        """Update the display name. No passphrase required."""
        async with self._db.session() as session:
            user = (
                await session.execute(select(User).where(User.id == identity_id))
            ).scalar_one_or_none()
            if user is None:
                raise AuthError("unknown identity")
            user.display_name = new_display_name
            await session.commit()
            return await self._load_identity(session, identity_id)

    async def update_email(
        self, *, identity_id: str, new_email: str, passphrase: str
    ) -> Identity:
        """Update the email. Requires current passphrase."""
        normalized_email = new_email.strip().lower()
        async with self._db.session() as session:
            user = (
                await session.execute(select(User).where(User.id == identity_id))
            ).scalar_one_or_none()
            if user is None:
                raise AuthError("unknown identity")
            row = (
                await session.execute(
                    select(UserConfig).where(
                        UserConfig.user_id == identity_id,
                        UserConfig.slot == _PASSPHRASE_SLOT,
                    )
                )
            ).scalar_one_or_none()
            if row is None:
                raise AuthError("no passphrase set")
            if not verify_passphrase(row.ciphertext.decode("utf-8"), passphrase):
                raise AuthError("wrong passphrase")
            # Pre-check for collision
            existing = (
                await session.execute(
                    select(User).where(User.email == normalized_email)
                )
            ).scalar_one_or_none()
            if existing is not None and existing.id != identity_id:
                raise EmailAlreadyRegisteredError(normalized_email)
            user.email = normalized_email
            try:
                await session.commit()
            except IntegrityError as exc:
                await session.rollback()
                raise EmailAlreadyRegisteredError(normalized_email) from exc
            return await self._load_identity(session, identity_id)

    async def update_passphrase(
        self, *, identity_id: str, old_passphrase: str, new_passphrase: str
    ) -> Identity:
        """Change passphrase. Requires current passphrase."""
        async with self._db.session() as session:
            user = (
                await session.execute(select(User).where(User.id == identity_id))
            ).scalar_one_or_none()
            if user is None:
                raise AuthError("unknown identity")
            row = (
                await session.execute(
                    select(UserConfig).where(
                        UserConfig.user_id == identity_id,
                        UserConfig.slot == _PASSPHRASE_SLOT,
                    )
                )
            ).scalar_one_or_none()
            if row is None:
                raise AuthError("no passphrase set")
            if not verify_passphrase(row.ciphertext.decode("utf-8"), old_passphrase):
                raise AuthError("wrong passphrase")
            row.ciphertext = hash_passphrase(new_passphrase).encode("utf-8")
            await session.commit()
            return await self._load_identity(session, identity_id)

    async def get_identity(self, user_id: str) -> Identity:
        """Public wrapper to load a fresh Identity by user_id."""
        async with self._db.session() as session:
            return await self._load_identity(session, user_id)


async def reset_passphrase_by_email(
    db: DatabaseHandle, *, email: str, new_passphrase: str
) -> Identity:
    """Out-of-band passphrase reset by email. Bypasses old-passphrase check.
    Revokes all sessions + tokens for the user on success.
    """
    from agentlabx.db.schema import Session as SessionRow
    from agentlabx.db.schema import UserToken

    normalized = email.strip().lower()
    async with db.session() as session:
        user = (
            await session.execute(select(User).where(User.email == normalized))
        ).scalar_one_or_none()
        if user is None:
            raise AuthError(f"no identity with email: {email}")
        # Update passphrase hash
        row = (
            await session.execute(
                select(UserConfig).where(
                    UserConfig.user_id == user.id,
                    UserConfig.slot == _PASSPHRASE_SLOT,
                )
            )
        ).scalar_one_or_none()
        digest = hash_passphrase(new_passphrase).encode("utf-8")
        if row is None:
            session.add(UserConfig(user_id=user.id, slot=_PASSPHRASE_SLOT, ciphertext=digest))
        else:
            row.ciphertext = digest
        # Revoke sessions
        sessions = (
            await session.execute(select(SessionRow).where(SessionRow.user_id == user.id))
        ).scalars().all()
        for s in sessions:
            s.revoked = True
        # Revoke tokens
        tokens = (
            await session.execute(select(UserToken).where(UserToken.user_id == user.id))
        ).scalars().all()
        for t in tokens:
            t.revoked = True
        await session.commit()
    # Re-read identity for return value
    auther = DefaultAuther(db)
    return await auther.get_identity(user.id)
