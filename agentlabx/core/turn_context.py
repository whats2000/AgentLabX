"""Per-turn context for correlating agent/LLM/tool events across async calls.

A TurnContext is created by ConfigAgent.inference() at the start of a turn and
pushed into a contextvar so downstream TracedLLMProvider / TracedTool wrappers
can correlate their emitted events with the active turn. Asyncio-safe: each
task has its own context copy, so concurrent inference calls don't interfere.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass


@dataclass
class TurnContext:
    turn_id: str
    agent: str
    stage: str
    is_mock: bool
    parent_turn_id: str | None = None
    system_prompt_hash: str | None = None
    session_id: str | None = None
    tokens_in: int = 0
    tokens_out: int = 0
    cost_usd: float = 0.0
    tool_call_count: int = 0


_current: ContextVar[TurnContext | None] = ContextVar("current_turn", default=None)


def current_turn() -> TurnContext | None:
    """Return the active TurnContext for this task, or None if no turn is active."""
    return _current.get()


@contextmanager
def push_turn(ctx: TurnContext) -> Iterator[TurnContext]:
    """Push a TurnContext onto the contextvar for the duration of the block."""
    token = _current.set(ctx)
    try:
        yield ctx
    finally:
        _current.reset(token)
