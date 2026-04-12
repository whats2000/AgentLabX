"""ConnectionManager — tracks WebSocket clients per session."""

from __future__ import annotations

import logging
from typing import Any

from fastapi import WebSocket

logger = logging.getLogger(__name__)


class ConnectionManager:
    """Per-session WebSocket subscriber registry.

    The executor subscribes a single forwarder to each session.event_bus and
    that forwarder calls ConnectionManager.broadcast. This keeps fan-out
    linear in connected clients rather than O(events × clients) as it would
    be if each client subscribed independently.
    """

    def __init__(self) -> None:
        self._connections: dict[str, list[WebSocket]] = {}

    async def connect(self, session_id: str, websocket: WebSocket) -> None:
        """Accept a new WebSocket and register it under the session_id."""
        await websocket.accept()
        self._connections.setdefault(session_id, []).append(websocket)

    def disconnect(self, session_id: str, websocket: WebSocket) -> None:
        """Remove a WebSocket from the session's registry. Safe if already gone."""
        conns = self._connections.get(session_id)
        if not conns:
            return
        try:
            conns.remove(websocket)
        except ValueError:
            pass
        if not conns:
            del self._connections[session_id]

    async def broadcast(self, session_id: str, message: dict[str, Any]) -> None:
        """Send JSON to all active clients for this session. Drops dead ones."""
        dead: list[WebSocket] = []
        for ws in list(self._connections.get(session_id, [])):
            try:
                await ws.send_json(message)
            except Exception as e:
                logger.debug("Dead WS for %s: %s", session_id, e)
                dead.append(ws)
        for ws in dead:
            self.disconnect(session_id, ws)

    def connection_count(self, session_id: str) -> int:
        return len(self._connections.get(session_id, []))
