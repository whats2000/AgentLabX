from __future__ import annotations

from pathlib import Path

import pytest

from agentlabx.auth.default import DefaultAuther
from agentlabx.auth.protocol import AuthError
from agentlabx.auth.token import TokenAuther
from agentlabx.db.migrations import apply_migrations
from agentlabx.db.session import DatabaseHandle


@pytest.mark.asyncio
async def test_issue_then_authenticate(tmp_workspace: Path) -> None:
    handle = DatabaseHandle(tmp_workspace / "t.db")
    await handle.connect()
    try:
        await apply_migrations(handle)
        default = DefaultAuther(handle)
        ident = await default.register(display_name="A", email="a@x.com", passphrase="p1234567")
        ta = TokenAuther(handle)
        issued = await ta.issue(identity_id=ident.id, label="ci-key")
        assert issued.token.startswith("ax_")
        assert issued.label == "ci-key"
        authed = await ta.authenticate({"token": issued.token})
        assert authed.id == ident.id
    finally:
        await handle.close()


@pytest.mark.asyncio
async def test_list_and_revoke(tmp_workspace: Path) -> None:
    handle = DatabaseHandle(tmp_workspace / "t.db")
    await handle.connect()
    try:
        await apply_migrations(handle)
        default = DefaultAuther(handle)
        ident = await default.register(display_name="A", email="a@x.com", passphrase="p1234567")
        ta = TokenAuther(handle)
        a = await ta.issue(identity_id=ident.id, label="ci")
        b = await ta.issue(identity_id=ident.id, label="deploy")
        rows = await ta.list_for(identity_id=ident.id)
        assert len(rows) == 2
        assert {r.label for r in rows} == {"ci", "deploy"}
        await ta.delete(identity_id=ident.id, token_id=a.id)
        with pytest.raises(AuthError):
            await ta.authenticate({"token": a.token})
        # b still works
        authed = await ta.authenticate({"token": b.token})
        assert authed.id == ident.id
    finally:
        await handle.close()


@pytest.mark.asyncio
async def test_authenticate_updates_last_used_at(tmp_workspace: Path) -> None:
    handle = DatabaseHandle(tmp_workspace / "t.db")
    await handle.connect()
    try:
        await apply_migrations(handle)
        default = DefaultAuther(handle)
        ident = await default.register(display_name="A", email="a@x.com", passphrase="p1234567")
        ta = TokenAuther(handle)
        issued = await ta.issue(identity_id=ident.id, label="ci")
        before = await ta.list_for(identity_id=ident.id)
        assert before[0].last_used_at is None
        await ta.authenticate({"token": issued.token})
        after = await ta.list_for(identity_id=ident.id)
        assert after[0].last_used_at is not None
    finally:
        await handle.close()
