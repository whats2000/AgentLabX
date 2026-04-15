"""Per-turn context for correlating agent/LLM/tool events across async calls.

A TurnContext is created by ConfigAgent.inference() at the start of a turn and
pushed into a contextvar so downstream TracedLLMProvider / TracedTool wrappers
can correlate their emitted events with the active turn. Asyncio-safe: each
task has its own context copy, so concurrent inference calls don't interfere.

A separate stage-level ContextVar (``_current_stage``) is pushed by the subgraph
work node for the duration of a stage's execute_plan call. This lets TracedTool
emit events with the correct stage name even when no TurnContext is active (i.e.
for stage-level tool calls made before agent inference).
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
_current_stage: ContextVar[str | None] = ContextVar("current_stage", default=None)


def current_turn() -> TurnContext | None:
    """Return the active TurnContext for this task, or None if no turn is active."""
    return _current.get()


def current_stage_name() -> str | None:
    """Return the active stage name for this task, or None if outside a stage work call.

    Populated by the subgraph work_node for the duration of execute_plan so that
    stage-level tool calls (no TurnContext) can still be attributed to a stage.
    """
    return _current_stage.get()


@contextmanager
def push_turn(ctx: TurnContext) -> Iterator[TurnContext]:
    """Push a TurnContext onto the contextvar for the duration of the block."""
    token = _current.set(ctx)
    try:
        yield ctx
    finally:
        _current.reset(token)


@contextmanager
def push_stage(stage_name: str) -> Iterator[str]:
    """Push a stage name onto the stage ContextVar for the duration of the block.

    Called by subgraph work_node so that TracedTool (and other observers) can
    attribute stage-level calls to the correct stage even when no TurnContext
    is active.
    """
    token = _current_stage.set(stage_name)
    try:
        yield stage_name
    finally:
        _current_stage.reset(token)
