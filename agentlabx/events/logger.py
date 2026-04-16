from __future__ import annotations

import json
from pathlib import Path

from agentlabx.events.bus import Event, EventBus


class JsonlEventSink:
    """Subscribes to the bus and appends every event to <workspace>/events/audit.jsonl."""

    def __init__(self, *, path: Path) -> None:
        self._path = path

    def install(self, bus: EventBus) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)

        async def _handler(event: Event) -> None:
            line = (
                json.dumps(
                    {
                        "kind": event.kind,
                        "at": event.at.isoformat(),
                        "payload": event.payload,
                    }
                )
                + "\n"
            )
            # Synchronous append is fine for A1 (single writer, low-throughput).
            with self._path.open("a", encoding="utf-8") as f:
                f.write(line)

        bus.subscribe("*", _handler)
