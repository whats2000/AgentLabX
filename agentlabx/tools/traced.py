"""Tracing wrapper around BaseTool — emits agent_tool_call / agent_tool_result
events and writes agent_turns rows when a TurnContext is active. Transparent
passthrough when no turn is active.
"""

from __future__ import annotations

import json

from agentlabx.core.event_types import EventTypes
from agentlabx.core.events import Event
from agentlabx.core.turn_context import current_turn
from agentlabx.providers.storage.base import AgentTurnRecord


class TracedTool:
    """Wraps any BaseTool; emits agent_tool_call / agent_tool_result
    and writes agent_turns when a TurnContext is active."""

    def __init__(self, inner, event_bus, storage):
        self._inner = inner
        self._bus = event_bus
        self._storage = storage

    def __getattr__(self, item):
        # Delegate any attribute not explicitly overridden (name, description,
        # get_schema, etc.) to the inner tool. __getattr__ is only called when
        # normal lookup fails, so self._inner / self._bus / self._storage are
        # unaffected.
        return getattr(self._inner, item)

    async def execute(self, **kwargs):
        ctx = current_turn()
        if ctx is None:
            return await self._inner.execute(**kwargs)

        ctx.tool_call_count += 1
        call_payload = {
            "turn_id": ctx.turn_id,
            "parent_turn_id": ctx.parent_turn_id,
            "tool": self._inner.name,
            "args": _safe_preview(kwargs),
        }
        await self._bus.emit(
            Event(
                type=EventTypes.AGENT_TOOL_CALL,
                data=call_payload,
                source=ctx.agent,
            )
        )
        if ctx.session_id:
            await self._storage.append_agent_turn(
                AgentTurnRecord(
                    session_id=ctx.session_id,
                    turn_id=ctx.turn_id,
                    parent_turn_id=ctx.parent_turn_id,
                    agent=ctx.agent,
                    stage=ctx.stage,
                    kind="tool_call",
                    payload=call_payload,
                    is_mock=ctx.is_mock,
                )
            )

        result = await self._inner.execute(**kwargs)
        success = bool(getattr(result, "success", True))
        preview = _safe_preview(getattr(result, "data", None))
        err = getattr(result, "error", None)

        res_payload = {
            "turn_id": ctx.turn_id,
            "tool": self._inner.name,
            "success": success,
            "result_preview": preview,
            "error": err,
        }
        await self._bus.emit(
            Event(
                type=EventTypes.AGENT_TOOL_RESULT,
                data=res_payload,
                source=ctx.agent,
            )
        )
        if ctx.session_id:
            await self._storage.append_agent_turn(
                AgentTurnRecord(
                    session_id=ctx.session_id,
                    turn_id=ctx.turn_id,
                    parent_turn_id=ctx.parent_turn_id,
                    agent=ctx.agent,
                    stage=ctx.stage,
                    kind="tool_result",
                    payload=res_payload,
                    is_mock=ctx.is_mock,
                )
            )
        return result


def _safe_preview(obj, limit: int = 8000) -> str:
    """JSON-stringify with fallback to repr; truncate to limit chars."""
    try:
        s = json.dumps(obj, default=str)
    except Exception:
        s = str(obj)
    return s if len(s) <= limit else s[:limit] + "\u2026"
