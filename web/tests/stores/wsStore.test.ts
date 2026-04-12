import { beforeEach, describe, expect, it } from "vitest";
import type { PipelineEvent } from "../../src/types/events";
import { MAX_EVENTS, useWSStore } from "../../src/stores/wsStore";

function mkEvent(i: number): PipelineEvent {
  return {
    type: "stage_started",
    data: { stage: `s${i}`, session_id: "sess-1" },
  };
}

describe("wsStore", () => {
  beforeEach(() => {
    useWSStore.setState({ events: {} });
  });

  it("appends events for a session", () => {
    const { appendEvent } = useWSStore.getState();
    appendEvent("sess-1", mkEvent(1));
    appendEvent("sess-1", mkEvent(2));
    expect(useWSStore.getState().getEvents("sess-1")).toHaveLength(2);
  });

  it("getEvents returns empty array for unknown session", () => {
    expect(useWSStore.getState().getEvents("unknown")).toEqual([]);
  });

  it("keeps events scoped per session", () => {
    const { appendEvent, getEvents } = useWSStore.getState();
    appendEvent("a", mkEvent(1));
    appendEvent("b", mkEvent(2));
    expect(getEvents("a")).toHaveLength(1);
    expect(getEvents("b")).toHaveLength(1);
    expect(getEvents("a")[0].data).toEqual({ stage: "s1", session_id: "sess-1" });
  });

  it("caps buffer at MAX_EVENTS, dropping oldest", () => {
    const { appendEvent, getEvents } = useWSStore.getState();
    for (let i = 0; i < MAX_EVENTS + 10; i += 1) {
      appendEvent("sess-1", mkEvent(i));
    }
    const events = getEvents("sess-1");
    expect(events).toHaveLength(MAX_EVENTS);
    // Oldest 10 should have dropped; first remaining event is index 10
    expect(events[0].data).toEqual({ stage: "s10", session_id: "sess-1" });
    expect(events[MAX_EVENTS - 1].data).toEqual({
      stage: `s${MAX_EVENTS + 9}`,
      session_id: "sess-1",
    });
  });

  it("clearEvents removes the session entry", () => {
    const { appendEvent, clearEvents, getEvents } = useWSStore.getState();
    appendEvent("sess-1", mkEvent(1));
    clearEvents("sess-1");
    expect(getEvents("sess-1")).toEqual([]);
  });

  it("clearEvents on unknown session is a no-op", () => {
    const before = useWSStore.getState().events;
    useWSStore.getState().clearEvents("unknown");
    expect(useWSStore.getState().events).toBe(before);
  });
});
