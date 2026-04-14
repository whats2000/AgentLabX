import { renderHook, act } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { describe, it, expect, vi, beforeEach } from "vitest";
import React from "react";

// ---- Minimal mock for wsRegistry ----------------------------------------

type EventHandler = (event: { type: string; data: unknown }) => void;

let capturedHandlers: EventHandler[] = [];

vi.mock("../../src/api/wsRegistry", () => ({
  wsRegistry: {
    acquire: vi.fn(() => ({
      onEvent: vi.fn((handler: EventHandler) => {
        capturedHandlers.push(handler);
        return () => {
          capturedHandlers = capturedHandlers.filter((h) => h !== handler);
        };
      }),
    })),
    release: vi.fn(),
  },
}));

// ---- Minimal mock for wsStore -------------------------------------------

vi.mock("../../src/stores/wsStore", () => ({
  useWSStore: vi.fn(() => vi.fn()),
}));

// ---- Helpers --------------------------------------------------------------

function makeWrapper(qc: QueryClient) {
  return function Wrapper({ children }: { children: React.ReactNode }) {
    return <QueryClientProvider client={qc}>{children}</QueryClientProvider>;
  };
}

function emit(type: string, data: unknown = {}) {
  capturedHandlers.forEach((h) => h({ type, data }));
}

// --------------------------------------------------------------------------

describe("useWebSocket invalidation map (C10)", () => {
  let qc: QueryClient;

  beforeEach(() => {
    capturedHandlers = [];
    qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    vi.clearAllMocks();
  });

  async function setup(sessionId = "s1") {
    const { useWebSocket } = await import("../../src/hooks/useWebSocket");
    const invalidate = vi.spyOn(qc, "invalidateQueries");
    renderHook(() => useWebSocket(sessionId), {
      wrapper: makeWrapper(qc),
    });
    return { invalidate };
  }

  it("agent_turn_completed invalidates agent-history, agent-memory, agent-context, and agents", async () => {
    const { invalidate } = await setup("s1");

    act(() => {
      emit("agent_turn_completed", {
        agent: "phd_student",
        turn_id: "turn-abc",
      });
    });

    const keys = invalidate.mock.calls.map((c) => (c[0] as { queryKey: unknown[] }).queryKey);
    expect(keys).toContainEqual(["agent-history", "s1", "phd_student"]);
    expect(keys).toContainEqual(["agent-memory", "s1", "phd_student"]);
    expect(keys).toContainEqual(["agent-context", "s1", "phd_student"]);
    expect(keys).toContainEqual(["agents", "s1"]);
  });

  it("agent_turn_started populates turn→agent map; agent_llm_request resolves agent from map", async () => {
    const { invalidate } = await setup("s1");

    act(() => {
      emit("agent_turn_started", { agent: "prof_agent", turn_id: "turn-xyz" });
    });

    invalidate.mockClear();

    act(() => {
      emit("agent_llm_request", { turn_id: "turn-xyz" }); // no agent field
    });

    const keys = invalidate.mock.calls.map((c) => (c[0] as { queryKey: unknown[] }).queryKey);
    expect(keys).toContainEqual(["agent-history", "s1", "prof_agent"]);
  });

  it("agent_llm_request with no mapping gracefully skips invalidation", async () => {
    const { invalidate } = await setup("s1");

    act(() => {
      emit("agent_llm_request", { turn_id: "unknown-turn" });
    });

    expect(invalidate).not.toHaveBeenCalled();
  });

  it("cost_update invalidates cost key", async () => {
    const { invalidate } = await setup("s1");

    act(() => {
      emit("cost_update", { session_id: "s1", cost_usd: 0.01 });
    });

    const keys = invalidate.mock.calls.map((c) => (c[0] as { queryKey: unknown[] }).queryKey);
    expect(keys).toContainEqual(["cost", "s1"]);
  });

  it("stage_completed invalidates graph and experiments", async () => {
    const { invalidate } = await setup("s1");

    act(() => {
      emit("stage_completed", { stage: "literature_review" });
    });

    const keys = invalidate.mock.calls.map((c) => (c[0] as { queryKey: unknown[] }).queryKey);
    expect(keys).toContainEqual(["graph", "s1"]);
    expect(keys).toContainEqual(["experiments", "s1"]);
  });

  it("pi_decision invalidates pi-history", async () => {
    const { invalidate } = await setup("s1");

    act(() => {
      emit("pi_decision", {});
    });

    const keys = invalidate.mock.calls.map((c) => (c[0] as { queryKey: unknown[] }).queryKey);
    expect(keys).toContainEqual(["pi-history", "s1"]);
  });

  it("hypothesis_update invalidates hypotheses", async () => {
    const { invalidate } = await setup("s1");

    act(() => {
      emit("hypothesis_update", {});
    });

    const keys = invalidate.mock.calls.map((c) => (c[0] as { queryKey: unknown[] }).queryKey);
    expect(keys).toContainEqual(["hypotheses", "s1"]);
  });

  it("stage_started invalidates stage-plans", async () => {
    const { invalidate } = await setup("s1");

    act(() => {
      emit("stage_started", { stage: "literature_review" });
    });

    const keys = invalidate.mock.calls.map((c) => (c[0] as { queryKey: unknown[] }).queryKey);
    expect(keys).toContainEqual(["stage-plans", "s1"]);
  });

  it("stage_completed invalidates stage-plans", async () => {
    const { invalidate } = await setup("s1");

    act(() => {
      emit("stage_completed", { stage: "literature_review" });
    });

    const keys = invalidate.mock.calls.map((c) => (c[0] as { queryKey: unknown[] }).queryKey);
    expect(keys).toContainEqual(["stage-plans", "s1"]);
  });
});
