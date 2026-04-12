"""Async event bus for inter-plugin communication."""

from __future__ import annotations

import asyncio
from collections import defaultdict
from collections.abc import Callable, Coroutine
from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel, Field


class Event(BaseModel):
    type: str
    data: dict[str, Any]
    source: str | None = None
    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))


EventHandler = Callable[[Event], Coroutine[Any, Any, None]]


class EventBus:
    def __init__(self) -> None:
        self._handlers: dict[str, list[EventHandler]] = defaultdict(list)

    def subscribe(self, event_type: str, handler: EventHandler) -> None:
        self._handlers[event_type].append(handler)

    def unsubscribe(self, event_type: str, handler: EventHandler) -> None:
        handlers = self._handlers.get(event_type, [])
        if handler in handlers:
            handlers.remove(handler)

    async def emit(self, event: Event) -> None:
        handlers: list[EventHandler] = []
        handlers.extend(self._handlers.get(event.type, []))
        if event.type != "*":
            handlers.extend(self._handlers.get("*", []))
        if handlers:
            await asyncio.gather(*(h(event) for h in handlers))
