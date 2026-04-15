from __future__ import annotations

from pathlib import Path

import httpx
import pytest

from agentlabx.auth.oauth import (
    DeviceFlowInitiation,
    OAuthAuther,
    OAuthProviderConfig,
)
from agentlabx.auth.protocol import AuthError
from agentlabx.db.migrations import apply_migrations
from agentlabx.db.session import DatabaseHandle


def _mock_transport_with_tokens() -> httpx.MockTransport:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/device/code"):
            return httpx.Response(
                200,
                json={
                    "device_code": "dc_abc",
                    "user_code": "WXYZ-1234",
                    "verification_uri": "https://example.com/verify",
                    "interval": 1,
                    "expires_in": 900,
                },
            )
        if request.url.path.endswith("/token"):
            return httpx.Response(
                200,
                json={
                    "access_token": "at_123",
                    "refresh_token": "rt_456",
                    "expires_in": 3600,
                    "token_type": "Bearer",
                },
            )
        return httpx.Response(404)

    return httpx.MockTransport(handler)


@pytest.mark.asyncio
async def test_initiate_returns_user_code(tmp_workspace: Path) -> None:
    handle = DatabaseHandle(tmp_workspace / "t.db")
    await handle.connect()
    try:
        await apply_migrations(handle)
        auther = OAuthAuther(
            db=handle,
            transport=_mock_transport_with_tokens(),
            providers={
                "demo": OAuthProviderConfig(
                    client_id="c",
                    device_code_url="https://example.com/device/code",
                    token_url="https://example.com/token",
                    scopes=("read",),
                )
            },
        )
        init = await auther.initiate(provider="demo")
        assert isinstance(init, DeviceFlowInitiation)
        assert init.user_code == "WXYZ-1234"
    finally:
        await handle.close()


@pytest.mark.asyncio
async def test_complete_stores_tokens_and_returns_identity(tmp_workspace: Path) -> None:
    handle = DatabaseHandle(tmp_workspace / "t.db")
    await handle.connect()
    try:
        await apply_migrations(handle)
        from cryptography.fernet import Fernet

        from agentlabx.security.fernet_store import FernetStore

        # Generate a real Fernet key for this test — do NOT hardcode a placeholder.
        fernet_key = Fernet.generate_key()

        auther = OAuthAuther(
            db=handle,
            transport=_mock_transport_with_tokens(),
            providers={
                "demo": OAuthProviderConfig(
                    client_id="c",
                    device_code_url="https://example.com/device/code",
                    token_url="https://example.com/token",
                    scopes=("read",),
                )
            },
            crypto=FernetStore(key=fernet_key),
        )
        init = await auther.initiate(provider="demo")
        identity = await auther.complete(
            provider="demo",
            device_code=init.device_code,
            display_name="Raj",
            email="raj@example.com",
        )
        assert identity.display_name == "Raj"
        assert identity.auther_name == "oauth"
        assert identity.email == "raj@example.com"
    finally:
        await handle.close()


@pytest.mark.asyncio
async def test_unknown_provider_raises(tmp_workspace: Path) -> None:
    handle = DatabaseHandle(tmp_workspace / "t.db")
    await handle.connect()
    try:
        await apply_migrations(handle)
        auther = OAuthAuther(
            db=handle,
            transport=_mock_transport_with_tokens(),
            providers={},
        )
        with pytest.raises(AuthError):
            await auther.initiate(provider="missing")
    finally:
        await handle.close()
