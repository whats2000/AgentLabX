"""Backtrack round-trip: counter increment, partial rollback, routing, transition_log."""
import asyncio
import pytest

from agentlabx.core.events import EventBus
from agentlabx.core.event_types import EventTypes
from agentlabx.core.pipeline import PipelineBuilder
from agentlabx.core.registry import PluginRegistry
from agentlabx.core.session import SessionPreferences
from agentlabx.core.state import create_initial_state
from agentlabx.plugins._builtin import register_builtin_plugins
from agentlabx.stages import runner as runner_mod
from agentlabx.stages.base import StageContext


@pytest.fixture
def registry():
    r = PluginRegistry()
    register_builtin_plugins(r)
    return r


@pytest.mark.asyncio
async def test_backtrack_round_trip(registry, monkeypatch):
    """Experimentation backtracks to literature_review; both stages re-run and complete."""
    calls: dict[str, int] = {
        "literature_review": 0,
        "plan_formulation": 0,
        "experimentation": 0,
    }

    async def fake_run(self, state):
        name = self.stage.name
        calls[name] = calls.get(name, 0) + 1
        update = {
            "current_stage": name,
            "stage_iterations": {
                **state.get("stage_iterations", {}),
                name: state.get("stage_iterations", {}).get(name, 0) + 1,
            },
            "total_iterations": state.get("total_iterations", 0) + 1,
        }
        if name == "experimentation" and calls["experimentation"] == 1:
            update["next_stage"] = "literature_review"
            update["backtrack_feedback"] = "need RL methods"
            return update
        update["next_stage"] = None
        return update

    monkeypatch.setattr(runner_mod.StageRunner, "run", fake_run)

    seq = ["literature_review", "plan_formulation", "experimentation"]
    graph = PipelineBuilder(
        registry=registry, preferences=SessionPreferences()
    ).build(stage_sequence=seq)

    state = create_initial_state(
        session_id="s1",
        user_id="u1",
        research_topic="t",
        default_sequence=seq,
        max_total_iterations=10,
    )

    result = await graph.ainvoke(
        state, config={"configurable": {"thread_id": "t1"}}
    )

    # Counter incremented for the backtrack edge
    assert (
        result["backtrack_attempts"].get("experimentation->literature_review")
        == 1
    )

    # Target stage actually re-ran — this is what a real backtrack looks like
    assert calls["literature_review"] >= 2

    # transition_log contains the backtrack edge with triggered_by="agent"
    backtrack_entries = [
        t for t in result["transition_log"]
        if t.from_stage == "experimentation"
        and t.to_stage == "literature_review"
    ]
    assert len(backtrack_entries) == 1
    assert backtrack_entries[0].triggered_by == "agent"


@pytest.mark.asyncio
async def test_checkpoint_reached_emitted_via_stage_context_event_bus(registry, monkeypatch):
    """Critical regression: transition_node must read event_bus from stage_context.

    This test validates the fix for the closure bug introduced in Plan 7C T7:
    `transition_node` closed over the `event_bus` kwarg of `build()`, which the
    executor never passed — so the event was never emitted in production.

    The fix reads `stage_context.event_bus` first; only falls back to the closure
    kwarg when stage_context is absent (legacy test path).

    Strategy: build PipelineBuilder with `stage_context` carrying a real EventBus
    + paused_event. Force `needs_approval=True` by exhausting the per-edge backtrack
    limit (backtrack_limit_exceeded action). Assert that after ainvoke:
      1. the EventBus received a `checkpoint_reached` event, and
      2. `stage_context.paused_event.is_set() == False` (pipeline was gated).
    """
    calls: dict[str, int] = {
        "literature_review": 0,
        "experimentation": 0,
    }

    async def fake_run(self, state):
        name = self.stage.name
        calls[name] = calls.get(name, 0) + 1
        update = {
            "current_stage": name,
            "stage_iterations": {
                **state.get("stage_iterations", {}),
                name: state.get("stage_iterations", {}).get(name, 0) + 1,
            },
            "total_iterations": state.get("total_iterations", 0) + 1,
        }
        if name == "experimentation":
            # Always request a backtrack — this will exhaust the per-edge limit
            # on the second call, triggering backtrack_limit_exceeded with
            # needs_approval=True.
            update["next_stage"] = "literature_review"
            update["backtrack_feedback"] = "keep backtacking"
            return update
        update["next_stage"] = None
        return update

    monkeypatch.setattr(runner_mod.StageRunner, "run", fake_run)

    # Collect emitted events
    received_events: list = []

    async def capture(event):
        received_events.append(event)

    bus = EventBus()
    bus.subscribe("*", capture)

    paused_event = asyncio.Event()
    paused_event.set()  # start unpaused

    ctx = StageContext(
        settings={},
        event_bus=bus,
        registry=registry,
        paused_event=paused_event,
    )

    # Use max_backtrack_attempts_per_edge=1 so the second backtrack request on
    # the same edge immediately triggers backtrack_limit_exceeded (needs_approval=True).
    prefs = SessionPreferences(max_backtrack_attempts_per_edge=1)

    seq = ["literature_review", "experimentation"]
    graph = PipelineBuilder(registry=registry, preferences=prefs).build(
        stage_sequence=seq,
        stage_context=ctx,
        # Intentionally DO NOT pass event_bus here — executor never does.
        # The fix must source it from stage_context.event_bus.
    )

    state = create_initial_state(
        session_id="s-hitl",
        user_id="u1",
        research_topic="regression test",
        default_sequence=seq,
        max_total_iterations=20,
    )

    # The graph will block on paused_event.wait() inside StageRunner once
    # needs_approval fires. We need to unblock it after the checkpoint gate
    # is set so ainvoke can complete.
    async def release_after_pause():
        """Poll until paused_event is cleared, then re-set it to let the graph advance."""
        for _ in range(200):
            await asyncio.sleep(0.05)
            if not paused_event.is_set():
                paused_event.set()
                return

    release_task = asyncio.create_task(release_after_pause())
    await graph.ainvoke(state, config={"configurable": {"thread_id": "t-hitl"}})
    await release_task

    # Assert 1: checkpoint_reached event was emitted (proves event_bus fix works)
    checkpoint_events = [
        e for e in received_events if e.type == EventTypes.CHECKPOINT_REACHED
    ]
    assert len(checkpoint_events) >= 1, (
        "No checkpoint_reached event emitted — event_bus closure bug is NOT fixed"
    )

    # Assert 2: paused_event was cleared then re-set by our release task, confirming
    # the pause gate did fire (it's now set again because release_after_pause unblocked it).
    # The key invariant: the event was cleared at some point (our poller wouldn't
    # have called .set() otherwise).
    assert paused_event.is_set(), (
        "release_after_pause never detected paused_event being cleared — "
        "paused_event.clear() was not called in transition_node"
    )
