from __future__ import annotations

from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient

from agentlabx.config.settings import AppSettings
from agentlabx.server.app import create_app


@pytest.mark.asyncio
@pytest.mark.integration
async def test_audit_log_records_auth_and_admin_events(
    tmp_workspace: Path, ephemeral_keyring: dict[tuple[str, str], str]
) -> None:
    settings = AppSettings(workspace=tmp_workspace)
    app = await create_app(settings)
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            # Register admin (first user auto-gets admin)
            r = await c.post(
                "/api/auth/register",
                json={
                    "display_name": "Admin",
                    "email": "admin@example.com",
                    "passphrase": "admin12345",
                },
            )
            assert r.status_code == 201

            # Login as admin
            r = await c.post(
                "/api/auth/login",
                json={"email": "admin@example.com", "passphrase": "admin12345"},
            )
            assert r.status_code == 200

            # Fetch audit log — should contain auth.registered and auth.login_success
            r = await c.get("/api/settings/admin/events")
            assert r.status_code == 200
            events = r.json()
            kinds = [e["kind"] for e in events]
            assert "auth.registered" in kinds

            # Admin creates second user
            r = await c.post(
                "/api/settings/admin/users",
                json={
                    "display_name": "Bob",
                    "email": "bob@example.com",
                    "passphrase": "bob1234567",
                },
            )
            assert r.status_code == 201
            bob_id = r.json()["id"]

            # Grant admin to Bob
            r = await c.post(
                f"/api/settings/admin/users/{bob_id}/capabilities",
                json={"capability": "admin"},
            )
            assert r.status_code == 204

            # Revoke admin from Bob
            r = await c.delete(
                f"/api/settings/admin/users/{bob_id}/capabilities/admin"
            )
            assert r.status_code == 204

            # Delete Bob
            r = await c.delete(f"/api/settings/admin/users/{bob_id}")
            assert r.status_code == 204

            # Fetch final audit log
            r = await c.get("/api/settings/admin/events")
            assert r.status_code == 200
            events = r.json()
            kinds = [e["kind"] for e in events]

            # Events must be present
            assert "auth.registered" in kinds
            assert "admin.user_created" in kinds
            assert "admin.capability_granted" in kinds
            assert "admin.capability_revoked" in kinds
            assert "admin.user_deleted" in kinds

            # Events must be newest-first:
            # admin.user_deleted should appear before admin.user_created
            idx_deleted = kinds.index("admin.user_deleted")
            idx_created = kinds.index("admin.user_created")
            assert idx_deleted < idx_created, (
                f"Expected admin.user_deleted (idx {idx_deleted}) before "
                f"admin.user_created (idx {idx_created}) in newest-first order"
            )

            # Verify payload shape for admin.user_created
            created_event = next(e for e in events if e["kind"] == "admin.user_created")
            assert created_event["payload"]["target_email"] == "bob@example.com"
            assert created_event["payload"]["actor_email"] == "admin@example.com"

            # Verify payload shape for admin.capability_granted
            granted_event = next(e for e in events if e["kind"] == "admin.capability_granted")
            assert granted_event["payload"]["capability"] == "admin"
            assert granted_event["payload"]["target_email"] == "bob@example.com"

            # Verify payload shape for admin.capability_revoked
            revoked_event = next(e for e in events if e["kind"] == "admin.capability_revoked")
            assert revoked_event["payload"]["capability"] == "admin"

            # Verify payload shape for admin.user_deleted
            deleted_event = next(e for e in events if e["kind"] == "admin.user_deleted")
            assert deleted_event["payload"]["target_email"] == "bob@example.com"
    finally:
        await app.state.db.close()


@pytest.mark.asyncio
@pytest.mark.integration
async def test_admin_can_clear_audit_log(
    tmp_workspace: Path, ephemeral_keyring: dict[tuple[str, str], str]
) -> None:
    settings = AppSettings(workspace=tmp_workspace)
    app = await create_app(settings)
    try:
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as c:
            # register + login; this generates a few audit events
            await c.post(
                "/api/auth/register",
                json={"display_name": "A", "email": "a@x.com", "passphrase": "p1234567"},
            )
            await c.post(
                "/api/auth/login",
                json={"email": "a@x.com", "passphrase": "p1234567"},
            )
            r = await c.get("/api/settings/admin/events")
            assert r.status_code == 200
            assert len(r.json()) >= 2  # at least registered + login_success

            # clear
            r = await c.delete("/api/settings/admin/events")
            assert r.status_code == 204

            # after clear, log contains exactly one entry: the clear event itself
            r = await c.get("/api/settings/admin/events")
            assert r.status_code == 200
            events = r.json()
            assert len(events) == 1
            assert events[0]["kind"] == "admin.audit_log_cleared"
            assert events[0]["payload"]["actor_email"] == "a@x.com"
    finally:
        await app.state.db.close()
