from __future__ import annotations

from pathlib import Path

import pytest

from agentlabx.auth.default import DefaultAuther
from agentlabx.auth.protocol import AuthError
from agentlabx.auth.token import TokenAuther
from agentlabx.db.migrations import apply_migrations
from agentlabx.db.session import DatabaseHandle


@pytest.mark.asyncio
async def test_issue_and_verify(tmp_workspace: Path) -> None:
    handle = DatabaseHandle(tmp_workspace / "t.db")
    await handle.connect()
    try:
        await apply_migrations(handle)
        default = DefaultAuther(handle)
        identity = await default.register(display_name="A", passphrase="p")
        token_auther = TokenAuther(handle)
        token = await token_auther.issue(identity_id=identity.id)
        assert token.startswith("ax_")
        authed = await token_auther.authenticate({"token": token})
        assert authed.id == identity.id
    finally:
        await handle.close()


@pytest.mark.asyncio
async def test_revoked_token_rejected(tmp_workspace: Path) -> None:
    handle = DatabaseHandle(tmp_workspace / "t.db")
    await handle.connect()
    try:
        await apply_migrations(handle)
        default = DefaultAuther(handle)
        identity = await default.register(display_name="A", passphrase="p")
        token_auther = TokenAuther(handle)
        token = await token_auther.issue(identity_id=identity.id)
        await token_auther.revoke(token)
        with pytest.raises(AuthError):
            await token_auther.authenticate({"token": token})
    finally:
        await handle.close()
