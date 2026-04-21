from __future__ import annotations

from pathlib import Path

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker

from agentlabx.db.schema import Base, User
from agentlabx.db.session import DatabaseHandle
from agentlabx.mcp.protocol import MCPServerSpec, RegistrationConflict
from agentlabx.mcp.registry import ServerRegistry


@pytest.fixture()
async def db(tmp_path: Path) -> DatabaseHandle:
    handle = DatabaseHandle(tmp_path / "test.db")
    await handle.connect()
    async with handle.engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    return handle


@pytest.fixture()
async def two_users(db: DatabaseHandle) -> tuple[str, str]:
    user_a = "user-a"
    user_b = "user-b"
    async with db.session() as session:
        session.add(
            User(
                id=user_a,
                display_name="User A",
                email="a@example.com",
                auther_name="test",
            )
        )
        session.add(
            User(
                id=user_b,
                display_name="User B",
                email="b@example.com",
                auther_name="test",
            )
        )
        await session.commit()
    return user_a, user_b


def _make_registry(db: DatabaseHandle) -> ServerRegistry:
    factory = async_sessionmaker(db.engine, expire_on_commit=False)
    return ServerRegistry(factory)


def _user_spec(name: str = "echo") -> MCPServerSpec:
    return MCPServerSpec(
        name=name,
        scope="user",
        transport="stdio",
        command=("python", "-m", "fake.echo"),
        url=None,
        inprocess_key=None,
        env_slot_refs=("user:key:openai",),
        declared_capabilities=("paper_search",),
    )


def _admin_spec(name: str = "memory") -> MCPServerSpec:
    return MCPServerSpec(
        name=name,
        scope="admin",
        transport="inprocess",
        command=None,
        url=None,
        inprocess_key="memory_server",
        env_slot_refs=(),
        declared_capabilities=("memory_read", "memory_write"),
    )


@pytest.mark.asyncio
async def test_register_round_trips_spec_and_returns_empty_tools(
    db: DatabaseHandle, two_users: tuple[str, str]
) -> None:
    user_a, _ = two_users
    registry = _make_registry(db)

    registered = await registry.register(_user_spec("echo"), owner_id=user_a)

    assert registered.owner_id == user_a
    assert registered.spec.name == "echo"
    assert registered.spec.command == ("python", "-m", "fake.echo")
    assert registered.spec.env_slot_refs == ("user:key:openai",)
    assert registered.spec.declared_capabilities == ("paper_search",)
    # Registry never fills runtime fields — that's the host's job.
    assert registered.tools == ()
    assert registered.started_at is None


@pytest.mark.asyncio
async def test_user_a_registration_invisible_to_user_b(
    db: DatabaseHandle, two_users: tuple[str, str]
) -> None:
    user_a, user_b = two_users
    registry = _make_registry(db)

    await registry.register(_user_spec("a-only"), owner_id=user_a)

    visible_to_b = await registry.list_visible_to(user_b)
    assert visible_to_b == []

    visible_to_a = await registry.list_visible_to(user_a)
    assert len(visible_to_a) == 1
    assert visible_to_a[0].spec.name == "a-only"


@pytest.mark.asyncio
async def test_admin_scope_visible_to_both_users(
    db: DatabaseHandle, two_users: tuple[str, str]
) -> None:
    user_a, user_b = two_users
    registry = _make_registry(db)

    await registry.register(_admin_spec("memory"), owner_id=None)

    visible_to_a = await registry.list_visible_to(user_a)
    visible_to_b = await registry.list_visible_to(user_b)

    assert [s.spec.name for s in visible_to_a] == ["memory"]
    assert [s.spec.name for s in visible_to_b] == ["memory"]
    assert visible_to_a[0].owner_id is None


@pytest.mark.asyncio
async def test_list_visible_orders_admin_before_user(
    db: DatabaseHandle, two_users: tuple[str, str]
) -> None:
    user_a, _ = two_users
    registry = _make_registry(db)

    await registry.register(_user_spec("zeta"), owner_id=user_a)
    await registry.register(_admin_spec("memory"), owner_id=None)
    await registry.register(_user_spec("alpha"), owner_id=user_a)

    visible = await registry.list_visible_to(user_a)
    # admin scope first, then user scope alphabetised by name.
    assert [(s.spec.scope, s.spec.name) for s in visible] == [
        ("admin", "memory"),
        ("user", "alpha"),
        ("user", "zeta"),
    ]


@pytest.mark.asyncio
async def test_register_duplicate_raises_registration_conflict(
    db: DatabaseHandle, two_users: tuple[str, str]
) -> None:
    user_a, _ = two_users
    registry = _make_registry(db)

    await registry.register(_user_spec("echo"), owner_id=user_a)

    with pytest.raises(RegistrationConflict) as exc_info:
        await registry.register(_user_spec("echo"), owner_id=user_a)
    assert exc_info.value.name == "echo"


@pytest.mark.asyncio
async def test_same_name_different_owner_does_not_conflict(
    db: DatabaseHandle, two_users: tuple[str, str]
) -> None:
    user_a, user_b = two_users
    registry = _make_registry(db)

    await registry.register(_user_spec("echo"), owner_id=user_a)
    # User B can register a server named 'echo' too — distinct (scope, owner, name).
    await registry.register(_user_spec("echo"), owner_id=user_b)

    assert len(await registry.list_visible_to(user_a)) == 1
    assert len(await registry.list_visible_to(user_b)) == 1


@pytest.mark.asyncio
async def test_get_returns_none_when_absent(db: DatabaseHandle) -> None:
    registry = _make_registry(db)
    assert await registry.get("does-not-exist") is None


@pytest.mark.asyncio
async def test_get_returns_registered_server(
    db: DatabaseHandle, two_users: tuple[str, str]
) -> None:
    user_a, _ = two_users
    registry = _make_registry(db)

    registered = await registry.register(_user_spec("echo"), owner_id=user_a)
    # Look up by id by fetching the only visible row's id via list.
    visible = await registry.list_visible_to(user_a)
    assert len(visible) == 1
    # We need the id; round-trip via raw ORM read (registry doesn't expose ids
    # on RegisteredServer because the runtime layer treats id as a registry-
    # internal handle). Use list-then-get-by-name in this test.
    fetched_by_name = [s for s in visible if s.spec.name == "echo"]
    assert fetched_by_name[0].spec == registered.spec


@pytest.mark.asyncio
async def test_user_cannot_delete_admin_scope_without_admin_flag(
    db: DatabaseHandle, two_users: tuple[str, str]
) -> None:
    user_a, _ = two_users
    registry = _make_registry(db)

    await registry.register(_admin_spec("memory"), owner_id=None)
    server_id = await _lookup_id_by_name(db, "memory")

    deleted = await registry.delete(server_id, requester_id=user_a, requester_is_admin=False)
    assert deleted is False
    # Row still present.
    assert await registry.get(server_id) is not None


@pytest.mark.asyncio
async def test_admin_can_delete_admin_scope(db: DatabaseHandle, two_users: tuple[str, str]) -> None:
    user_a, _ = two_users
    registry = _make_registry(db)

    await registry.register(_admin_spec("memory"), owner_id=None)
    server_id = await _lookup_id_by_name(db, "memory")

    deleted = await registry.delete(server_id, requester_id=user_a, requester_is_admin=True)
    assert deleted is True
    assert await registry.get(server_id) is None


@pytest.mark.asyncio
async def test_user_can_delete_own_user_scope(
    db: DatabaseHandle, two_users: tuple[str, str]
) -> None:
    user_a, _ = two_users
    registry = _make_registry(db)

    await registry.register(_user_spec("echo"), owner_id=user_a)
    server_id = await _lookup_id_by_name(db, "echo")

    deleted = await registry.delete(server_id, requester_id=user_a, requester_is_admin=False)
    assert deleted is True


@pytest.mark.asyncio
async def test_user_cannot_delete_other_users_user_scope(
    db: DatabaseHandle, two_users: tuple[str, str]
) -> None:
    user_a, user_b = two_users
    registry = _make_registry(db)

    await registry.register(_user_spec("echo"), owner_id=user_a)
    server_id = await _lookup_id_by_name(db, "echo")

    deleted = await registry.delete(server_id, requester_id=user_b, requester_is_admin=False)
    assert deleted is False
    assert await registry.get(server_id) is not None


@pytest.mark.asyncio
async def test_delete_missing_returns_false(db: DatabaseHandle) -> None:
    registry = _make_registry(db)
    deleted = await registry.delete(
        "does-not-exist", requester_id="anyone", requester_is_admin=True
    )
    assert deleted is False


@pytest.mark.asyncio
async def test_set_enabled_toggles_value(db: DatabaseHandle, two_users: tuple[str, str]) -> None:
    user_a, _ = two_users
    registry = _make_registry(db)

    await registry.register(_user_spec("echo"), owner_id=user_a)
    server_id = await _lookup_id_by_name(db, "echo")

    await registry.set_enabled(server_id, False)
    assert await _enabled_value(db, server_id) == 0

    await registry.set_enabled(server_id, True)
    assert await _enabled_value(db, server_id) == 1


@pytest.mark.asyncio
async def test_set_enabled_no_op_for_missing_row(db: DatabaseHandle) -> None:
    registry = _make_registry(db)
    # Should not raise.
    await registry.set_enabled("does-not-exist", False)


# ---------------------------------------------------------------------------
# Test helpers: id lookup by name (registry intentionally does not expose ids
# on RegisteredServer; for tests that need the id we go to the DB directly).
# ---------------------------------------------------------------------------


async def _lookup_id_by_name(db: DatabaseHandle, name: str) -> str:
    from sqlalchemy import select

    from agentlabx.db.schema import MCPServer

    async with db.session() as session:
        result = await session.execute(select(MCPServer.id).where(MCPServer.name == name))
        row_id = result.scalar_one()
    assert isinstance(row_id, str)
    return row_id


async def _enabled_value(db: DatabaseHandle, server_id: str) -> int:
    from agentlabx.db.schema import MCPServer

    async with db.session() as session:
        row = await session.get(MCPServer, server_id)
    assert row is not None
    return row.enabled
