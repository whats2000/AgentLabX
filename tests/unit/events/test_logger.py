from __future__ import annotations

import json
from pathlib import Path

import pytest

from agentlabx.events.bus import Event, EventBus
from agentlabx.events.logger import JsonlEventSink


@pytest.mark.asyncio
async def test_jsonl_sink_writes_events(tmp_path: Path) -> None:
    log_path = tmp_path / "events" / "audit.jsonl"
    bus = EventBus()
    sink = JsonlEventSink(path=log_path)
    sink.install(bus)

    await bus.emit(
        Event(
            kind="auth.registered",
            payload={"actor_id": "u1", "actor_email": "a@x.com", "display_name": "Alice"},
        )
    )
    await bus.emit(
        Event(
            kind="auth.login_success",
            payload={"actor_id": "u1", "actor_email": "a@x.com"},
        )
    )

    assert log_path.exists(), "JSONL file should be created"
    lines = log_path.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 2, f"Expected 2 lines, got {len(lines)}"

    first = json.loads(lines[0])
    assert first["kind"] == "auth.registered"
    assert first["payload"]["actor_email"] == "a@x.com"
    assert first["payload"]["display_name"] == "Alice"
    assert "at" in first

    second = json.loads(lines[1])
    assert second["kind"] == "auth.login_success"
    assert second["payload"]["actor_id"] == "u1"
