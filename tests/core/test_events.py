from __future__ import annotations

import pytest

from agentlabx.core.events import Event, EventBus


class TestEvent:
    def test_create_event(self):
        event = Event(type="stage_started", data={"stage": "lit_review"})
        assert event.type == "stage_started"
        assert event.data["stage"] == "lit_review"

    def test_event_with_source(self):
        event = Event(type="agent_thinking", data={}, source="phd_student")
        assert event.source == "phd_student"


class TestEventBus:
    @pytest.fixture()
    def bus(self) -> EventBus:
        return EventBus()

    async def test_subscribe_and_emit(self, bus: EventBus):
        received: list[Event] = []

        async def handler(event: Event) -> None:
            received.append(event)

        bus.subscribe("test_event", handler)
        await bus.emit(Event(type="test_event", data={"key": "value"}))

        assert len(received) == 1
        assert received[0].data["key"] == "value"

    async def test_multiple_subscribers(self, bus: EventBus):
        count = {"a": 0, "b": 0}

        async def handler_a(event: Event) -> None:
            count["a"] += 1

        async def handler_b(event: Event) -> None:
            count["b"] += 1

        bus.subscribe("ping", handler_a)
        bus.subscribe("ping", handler_b)
        await bus.emit(Event(type="ping", data={}))

        assert count["a"] == 1
        assert count["b"] == 1

    async def test_wildcard_subscriber(self, bus: EventBus):
        received: list[Event] = []

        async def handler(event: Event) -> None:
            received.append(event)

        bus.subscribe("*", handler)
        await bus.emit(Event(type="any_event", data={}))
        await bus.emit(Event(type="other_event", data={}))

        assert len(received) == 2

    async def test_unsubscribe(self, bus: EventBus):
        received: list[Event] = []

        async def handler(event: Event) -> None:
            received.append(event)

        bus.subscribe("test", handler)
        await bus.emit(Event(type="test", data={}))
        assert len(received) == 1

        bus.unsubscribe("test", handler)
        await bus.emit(Event(type="test", data={}))
        assert len(received) == 1

    async def test_emit_no_subscribers(self, bus: EventBus):
        await bus.emit(Event(type="no_listeners", data={}))
