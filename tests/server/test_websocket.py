"""Tests for the WebSocket endpoint and ConnectionManager."""

from __future__ import annotations

import os

import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from agentlabx.server.app import create_app
from agentlabx.server.ws.connection import ConnectionManager


@pytest.fixture()
def client(tmp_path):
    os.environ["AGENTLABX_STORAGE__DATABASE_URL"] = f"sqlite+aiosqlite:///{tmp_path / 'test.db'}"
    os.environ["AGENTLABX_STORAGE__ARTIFACTS_PATH"] = str(tmp_path / "artifacts")
    app = create_app(use_mock_llm=True)
    with TestClient(app) as c:
        yield c
    os.environ.pop("AGENTLABX_STORAGE__DATABASE_URL", None)
    os.environ.pop("AGENTLABX_STORAGE__ARTIFACTS_PATH", None)


class TestConnectionManager:
    async def test_connection_count(self):
        """Unit test without network — test bookkeeping logic."""
        from unittest.mock import AsyncMock, MagicMock

        manager = ConnectionManager()
        ws = MagicMock()
        ws.accept = AsyncMock()
        await manager.connect("s1", ws)
        assert manager.connection_count("s1") == 1
        manager.disconnect("s1", ws)
        assert manager.connection_count("s1") == 0

    async def test_broadcast_sends_to_all(self):
        from unittest.mock import AsyncMock, MagicMock

        manager = ConnectionManager()
        ws_a = MagicMock()
        ws_a.accept = AsyncMock()
        ws_a.send_json = AsyncMock()
        ws_b = MagicMock()
        ws_b.accept = AsyncMock()
        ws_b.send_json = AsyncMock()
        await manager.connect("s1", ws_a)
        await manager.connect("s1", ws_b)
        await manager.broadcast("s1", {"type": "test", "data": {}})
        ws_a.send_json.assert_called_once_with({"type": "test", "data": {}})
        ws_b.send_json.assert_called_once_with({"type": "test", "data": {}})

    async def test_broadcast_drops_dead_connections(self):
        from unittest.mock import AsyncMock, MagicMock

        manager = ConnectionManager()
        ws_good = MagicMock()
        ws_good.accept = AsyncMock()
        ws_good.send_json = AsyncMock()
        ws_dead = MagicMock()
        ws_dead.accept = AsyncMock()
        ws_dead.send_json = AsyncMock(side_effect=RuntimeError("dead"))
        await manager.connect("s1", ws_good)
        await manager.connect("s1", ws_dead)
        await manager.broadcast("s1", {"type": "x"})
        assert manager.connection_count("s1") == 1

    async def test_broadcast_to_unknown_session_noop(self):
        manager = ConnectionManager()
        # No connections registered — should not raise
        await manager.broadcast("nonexistent", {"type": "x"})


class TestSessionWebSocket:
    def _create_session(self, client, topic="test"):
        return client.post("/api/sessions", json={"topic": topic}).json()["session_id"]

    def test_connect_to_existing_session(self, client):
        sid = self._create_session(client)
        with client.websocket_connect(f"/ws/sessions/{sid}"):
            # If the context manager enters, connection was accepted
            pass

    def test_connect_to_missing_session_closes(self, client):
        with pytest.raises(WebSocketDisconnect) as exc_info:
            with client.websocket_connect("/ws/sessions/nonexistent") as ws:
                ws.receive_json()  # forces the close to surface
        # Starlette exposes the close code on the disconnect exception
        assert exc_info.value.code == 4404

    def test_update_preferences_via_ws(self, client):
        sid = self._create_session(client)
        with client.websocket_connect(f"/ws/sessions/{sid}") as ws:
            ws.send_json(
                {
                    "action": "update_preferences",
                    "mode": "hitl",
                    "stage_controls": {"experimentation": "approve"},
                }
            )
            # Give the server a moment to apply. TestClient runs synchronously
            # so the next HTTP call will see the update.
        r = client.get(f"/api/sessions/{sid}")
        prefs = r.json()["preferences"]
        assert prefs["mode"] == "hitl"
        assert prefs["stage_controls"]["experimentation"] == "approve"

    def test_unknown_action_ignored(self, client):
        sid = self._create_session(client)
        with client.websocket_connect(f"/ws/sessions/{sid}") as ws:
            ws.send_json({"action": "noop_action"})  # Should not close the WS
            # Send another known message to verify WS is still alive
            ws.send_json({"action": "update_preferences", "mode": "hitl"})
        r = client.get(f"/api/sessions/{sid}")
        assert r.json()["preferences"]["mode"] == "hitl"

    def test_disconnect_cleans_up(self, client):
        """Connection count should return to 0 after disconnect."""
        from agentlabx.server.ws.handlers import manager

        sid = self._create_session(client)
        # Reset any state from prior tests
        manager._connections.clear()
        with client.websocket_connect(f"/ws/sessions/{sid}"):
            assert manager.connection_count(sid) == 1
        # After exit, cleanup should have happened
        assert manager.connection_count(sid) == 0

    def test_redirect_action_without_running_noop(self, client):
        """Redirect sent via WS when executor has no running entry — no error."""
        sid = self._create_session(client)
        with client.websocket_connect(f"/ws/sessions/{sid}") as ws:
            # Session is CREATED not RUNNING; executor.redirect_session raises KeyError
            # which the handler catches.
            ws.send_json(
                {
                    "action": "redirect",
                    "target_stage": "plan_formulation",
                }
            )
            ws.send_json({"action": "update_preferences", "mode": "hitl"})
        # WS should still be usable; preferences should have updated
        r = client.get(f"/api/sessions/{sid}")
        assert r.json()["preferences"]["mode"] == "hitl"
