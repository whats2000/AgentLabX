from __future__ import annotations

import asyncio

import pytest

from agentlabx.events.bus import Event, EventBus


@pytest.mark.asyncio
async def test_single_subscriber_receives_event() -> None:
    bus = EventBus()
    received: list[Event] = []

    async def handler(event: Event) -> None:
        received.append(event)

    bus.subscribe("demo", handler)
    await bus.emit(Event(kind="demo", payload={"n": 1}))
    await asyncio.sleep(0)  # allow handler to run
    assert len(received) == 1
    assert received[0].payload == {"n": 1}


@pytest.mark.asyncio
async def test_multiple_subscribers_all_receive() -> None:
    bus = EventBus()
    received_a: list[Event] = []
    received_b: list[Event] = []

    async def ha(e: Event) -> None:
        received_a.append(e)

    async def hb(e: Event) -> None:
        received_b.append(e)

    bus.subscribe("x", ha)
    bus.subscribe("x", hb)
    await bus.emit(Event(kind="x", payload={}))
    await asyncio.sleep(0)
    assert len(received_a) == 1
    assert len(received_b) == 1


@pytest.mark.asyncio
async def test_wildcard_subscriber_receives_all_kinds() -> None:
    bus = EventBus()
    received: list[Event] = []

    async def handler(event: Event) -> None:
        received.append(event)

    bus.subscribe("*", handler)
    await bus.emit(Event(kind="a", payload={}))
    await bus.emit(Event(kind="b", payload={}))
    await asyncio.sleep(0)
    assert [e.kind for e in received] == ["a", "b"]
