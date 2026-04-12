"""WebSocket endpoint for per-session event streaming and client actions."""

from __future__ import annotations

import logging

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from agentlabx.server.ws.connection import ConnectionManager

logger = logging.getLogger(__name__)

# Module-level manager shared across connections and the executor forwarder.
manager = ConnectionManager()

router = APIRouter()


@router.websocket("/ws/sessions/{session_id}")
async def session_websocket(websocket: WebSocket, session_id: str):
    """Per-session WebSocket endpoint.

    Subscribes nothing to the event bus directly (Fix G) — the executor
    subscribes a single forwarder that calls `manager.broadcast`. This handler
    only accepts connections, receives client actions, and cleans up on disconnect.
    """
    app = websocket.app
    context = app.state.context

    # Validate session exists (Fix B: does not require session to be running)
    try:
        context.session_manager.get_session(session_id)
    except KeyError:
        await websocket.close(code=4404, reason="Session not found")
        return

    await manager.connect(session_id, websocket)
    try:
        while True:
            msg = await websocket.receive_json()
            await _handle_client_message(msg, session_id, context)
    except WebSocketDisconnect:
        pass
    except Exception:
        logger.exception("WebSocket error for session %s", session_id)
    finally:
        manager.disconnect(session_id, websocket)


async def _handle_client_message(
    msg: dict,
    session_id: str,
    context,
) -> None:
    """Dispatch client → server actions per spec §7.2."""
    action = msg.get("action")
    if not action:
        return

    if action == "update_preferences":
        session = context.session_manager.get_session(session_id)
        updates = {
            k: v for k, v in msg.items() if k in {"mode", "stage_controls", "backtrack_control"}
        }
        if updates:
            session.update_preferences(**updates)

    elif action == "redirect":
        target = msg.get("target_stage")
        reason = msg.get("reason", "")
        if target and context.executor is not None:
            try:
                await context.executor.redirect_session(session_id, target, reason)
            except KeyError:
                # Session not currently running — ignore (client will see next
                # status update via broadcast)
                pass

    elif action == "inject_feedback":
        # Append feedback to messages via state update. Plan 4 deferred: real
        # HITL interrupt flow for approve/edit lands in a later plan.
        logger.info(
            "Feedback from WS for %s: %s",
            session_id,
            msg.get("content", "")[:200],
        )

    elif action == "approve" or action == "edit":
        # HITL interrupt-driven actions — documented as deferred in Plan 4.
        logger.info("HITL action '%s' received for %s (deferred)", action, session_id)
