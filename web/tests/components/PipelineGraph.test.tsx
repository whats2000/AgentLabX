import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

// Mock api.client before importing the component.
vi.mock("../../src/api/client", () => ({
  api: {
    getSession: vi.fn(),
    getTransitions: vi.fn(),
  },
  APIError: class extends Error {},
  isValidationError: () => false,
}));

// React Flow needs ResizeObserver and DOMMatrix in jsdom.
class ResizeObserverStub {
  observe() {}
  unobserve() {}
  disconnect() {}
}
(
  globalThis as typeof globalThis & { ResizeObserver: typeof ResizeObserverStub }
).ResizeObserver = ResizeObserverStub;

if (typeof (globalThis as unknown as { DOMMatrixReadOnly?: unknown }).DOMMatrixReadOnly === "undefined") {
  class DOMMatrixStub {
    m22 = 1;
  }
  (globalThis as unknown as { DOMMatrixReadOnly: unknown }).DOMMatrixReadOnly =
    DOMMatrixStub;
}

import { PipelineGraph } from "../../src/components/session/PipelineGraph";
import { api } from "../../src/api/client";

const mockedApi = api as unknown as {
  getSession: ReturnType<typeof vi.fn>;
  getTransitions: ReturnType<typeof vi.fn>;
};

function renderGraph() {
  const qc = new QueryClient({
    defaultOptions: { queries: { retry: false, refetchInterval: false } },
  });
  return render(
    <QueryClientProvider client={qc}>
      <PipelineGraph sessionId="sess-1" />
    </QueryClientProvider>,
  );
}

describe("PipelineGraph", () => {
  beforeEach(() => {
    mockedApi.getSession.mockReset();
    mockedApi.getTransitions.mockReset();
  });

  it("renders zone headers", async () => {
    mockedApi.getSession.mockResolvedValue({
      session_id: "sess-1",
      user_id: "u",
      research_topic: "t",
      status: "running",
      current_stage: "plan_formulation",
      completed_stages: ["literature_review"],
      preferences: {},
      config_overrides: {},
    });
    mockedApi.getTransitions.mockResolvedValue({ transitions: [] });
    renderGraph();
    expect(await screen.findByText(/DISCOVERY/)).toBeInTheDocument();
    expect(screen.getByText(/IMPLEMENTATION/)).toBeInTheDocument();
    expect(screen.getByText(/SYNTHESIS/)).toBeInTheDocument();
  });

  it("renders all 8 stage node labels", async () => {
    mockedApi.getSession.mockResolvedValue({
      session_id: "sess-1",
      user_id: "u",
      research_topic: "t",
      status: "created",
      current_stage: "",
      completed_stages: [],
      preferences: {},
      config_overrides: {},
    });
    mockedApi.getTransitions.mockResolvedValue({ transitions: [] });
    renderGraph();
    expect(await screen.findByText("Literature Review")).toBeInTheDocument();
    expect(screen.getByText("Plan Formulation")).toBeInTheDocument();
    expect(screen.getByText("Peer Review")).toBeInTheDocument();
  });

  it("shows the 'Show all backtracks' toggle only when > 3 backtracks", async () => {
    mockedApi.getSession.mockResolvedValue({
      session_id: "sess-1",
      user_id: "u",
      research_topic: "t",
      status: "running",
      current_stage: "experimentation",
      completed_stages: [],
      preferences: {},
      config_overrides: {},
    });
    // 4 backtracks — toggle should appear
    mockedApi.getTransitions.mockResolvedValue({
      transitions: Array.from({ length: 4 }).map((_, i) => ({
        from_stage: "experimentation",
        to_stage: "data_preparation",
        reason: `r${i}`,
        triggered_by: "agent",
        timestamp: new Date().toISOString(),
      })),
    });
    renderGraph();
    expect(
      await screen.findByText(/Show all backtracks \(4\)/),
    ).toBeInTheDocument();
  });

  it("hides the toggle when backtracks <= 3", async () => {
    mockedApi.getSession.mockResolvedValue({
      session_id: "sess-1",
      user_id: "u",
      research_topic: "t",
      status: "running",
      current_stage: "experimentation",
      completed_stages: [],
      preferences: {},
      config_overrides: {},
    });
    mockedApi.getTransitions.mockResolvedValue({
      transitions: [
        {
          from_stage: "experimentation",
          to_stage: "data_preparation",
          reason: "r0",
          triggered_by: "agent",
          timestamp: new Date().toISOString(),
        },
      ],
    });
    renderGraph();
    await screen.findByText("Literature Review");
    expect(screen.queryByText(/Show all backtracks/)).not.toBeInTheDocument();
  });
});
