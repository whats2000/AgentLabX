from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import cast

import httpx
from sqlalchemy import select

from agentlabx.auth.protocol import AuthError, Identity
from agentlabx.db.schema import Capability, OAuthToken, User
from agentlabx.db.session import DatabaseHandle
from agentlabx.security.fernet_store import FernetStore


@dataclass(frozen=True)
class OAuthProviderConfig:
    client_id: str
    device_code_url: str
    token_url: str
    scopes: tuple[str, ...]


@dataclass(frozen=True)
class DeviceFlowInitiation:
    device_code: str
    user_code: str
    verification_uri: str
    interval: int
    expires_at: datetime


class OAuthAuther:
    """Generic RFC 8628 device-flow auther. Stores access+refresh tokens encrypted."""

    name = "oauth"

    def __init__(
        self,
        *,
        db: DatabaseHandle,
        providers: dict[str, OAuthProviderConfig],
        transport: httpx.AsyncBaseTransport | None = None,
        crypto: FernetStore | None = None,
    ) -> None:
        self._db = db
        self._providers = providers
        self._transport = transport
        self._crypto = crypto

    def _client(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(transport=self._transport)

    def _fernet(self) -> FernetStore:
        if self._crypto is None:
            self._crypto = FernetStore.from_keyring()
        return self._crypto

    async def initiate(self, *, provider: str) -> DeviceFlowInitiation:
        cfg = self._providers.get(provider)
        if cfg is None:
            raise AuthError(f"unknown provider: {provider}")
        async with self._client() as client:
            response = await client.post(
                cfg.device_code_url,
                data={"client_id": cfg.client_id, "scope": " ".join(cfg.scopes)},
                headers={"Accept": "application/json"},
            )
            response.raise_for_status()
            body = cast(dict[str, str | int], response.json())
        return DeviceFlowInitiation(
            device_code=str(body["device_code"]),
            user_code=str(body["user_code"]),
            verification_uri=str(body["verification_uri"]),
            interval=int(body.get("interval", 5)),
            expires_at=datetime.now(tz=timezone.utc) + timedelta(seconds=int(body["expires_in"])),
        )

    async def complete(
        self, *, provider: str, device_code: str, display_name: str
    ) -> Identity:
        cfg = self._providers.get(provider)
        if cfg is None:
            raise AuthError(f"unknown provider: {provider}")
        async with self._client() as client:
            response = await client.post(
                cfg.token_url,
                data={
                    "client_id": cfg.client_id,
                    "device_code": device_code,
                    "grant_type": "urn:ietf:params:oauth:grant-type:device_code",
                },
                headers={"Accept": "application/json"},
            )
            response.raise_for_status()
            token_body = cast(dict[str, str | int], response.json())
        if "access_token" not in token_body:
            raise AuthError(f"device authorization pending or failed: {token_body}")

        user_id = str(uuid.uuid4())
        fernet = self._fernet()
        access_ct = fernet.encrypt(str(token_body["access_token"]).encode("utf-8"))
        refresh_ct: bytes | None = None
        refresh = token_body.get("refresh_token")
        if isinstance(refresh, str):
            refresh_ct = fernet.encrypt(refresh.encode("utf-8"))

        expires_at: datetime | None = None
        if "expires_in" in token_body:
            expires_at = datetime.now(tz=timezone.utc) + timedelta(
                seconds=int(token_body["expires_in"])
            )

        async with self._db.session() as session:
            user_count = (
                await session.execute(select(User).with_only_columns(User.id))
            ).all()
            session.add(User(id=user_id, display_name=display_name, auther_name=self.name))
            session.add(
                OAuthToken(
                    user_id=user_id,
                    provider=provider,
                    access_ciphertext=access_ct,
                    refresh_ciphertext=refresh_ct,
                    expires_at=expires_at,
                )
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
            capabilities=frozenset(caps),
        )

    async def authenticate(self, credentials: dict[str, str]) -> Identity:
        # Authentication after completion is done by session cookie; OAuthAuther
        # does not re-authenticate arbitrary access tokens in A1. Out-of-band
        # calls raise explicitly so misuse is visible.
        raise AuthError("OAuthAuther.authenticate is not used; complete device flow instead")
