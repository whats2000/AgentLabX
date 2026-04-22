from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import datetime, timezone

from agentlabx.core.json_types import JSONValue

Handler = Callable[["Event"], Awaitable[None]]


@dataclass(frozen=True)
class Event:
    kind: str
    payload: dict[str, JSONValue]
    at: datetime = field(default_factory=lambda: datetime.now(tz=timezone.utc))


class EventBus:
    """Fire-and-forget async pub/sub. Wildcard `*` matches any kind."""

    def __init__(self) -> None:
        self._subs: dict[str, list[Handler]] = {}

    def subscribe(self, kind: str, handler: Handler) -> None:
        self._subs.setdefault(kind, []).append(handler)

    async def emit(self, event: Event) -> None:
        targets: list[Handler] = []
        targets.extend(self._subs.get(event.kind, []))
        targets.extend(self._subs.get("*", []))
        if not targets:
            return
        await asyncio.gather(*(h(event) for h in targets))
