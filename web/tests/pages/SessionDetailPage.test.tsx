import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import SessionDetailPage from "../../src/pages/SessionDetailPage";

vi.mock("../../src/api/client", () => ({
  api: {
    getSession: vi.fn(),
    getCost: vi.fn().mockResolvedValue({
      total_tokens_in: 0,
      total_tokens_out: 0,
      total_cost: 0,
    }),
    getArtifacts: vi.fn().mockResolvedValue([]),
    getTransitions: vi.fn().mockResolvedValue([]),
    getHypotheses: vi.fn().mockResolvedValue([]),
    getGraph: vi.fn().mockResolvedValue({ nodes: [], edges: [], cursor: null, subgraphs: [] }),
    listAgents: vi.fn().mockResolvedValue([]),
    getPIHistory: vi.fn().mockResolvedValue([]),
    getExperiments: vi.fn().mockResolvedValue({ runs: [], log: [] }),
    getRequests: vi.fn().mockResolvedValue([]),
    getAgentContext: vi.fn().mockResolvedValue(null),
    getAgentMemory: vi.fn().mockResolvedValue(null),
    getAgentHistory: vi.fn().mockResolvedValue([]),
  },
  APIError: class extends Error {},
  isValidationError: () => false,
}));
vi.mock("../../src/api/wsRegistry", () => ({
  wsRegistry: {
    acquire: vi.fn(() => ({ onEvent: vi.fn(() => () => undefined) })),
    release: vi.fn(),
    getSocket: vi.fn(() => null),
  },
}));

// Heavy canvas/layout components that don't work in jsdom
vi.mock("../../src/components/session/GraphTopology", () => ({
  GraphTopology: () => <div data-testid="graph-topology" />,
}));
vi.mock("../../src/components/session/AgentMonitor", () => ({
  AgentMonitor: () => <div data-testid="agent-monitor" />,
}));
vi.mock("../../src/components/session/PIDecisionLog", () => ({
  PIDecisionLog: () => <div data-testid="pi-decision-log" />,
}));
vi.mock("../../src/components/session/ChatView", () => ({
  ChatView: () => <div data-testid="chat-view" />,
}));
vi.mock("../../src/components/session/ExperimentsTab", () => ({
  ExperimentsTab: () => <div data-testid="experiments-tab" />,
}));

vi.mock("../../src/components/session/CostGauge", () => ({
  CostGauge: () => <div data-testid="cost-gauge" />,
}));
vi.mock("../../src/components/session/CostLine", () => ({
  CostLine: () => <div data-testid="cost-line" />,
}));

import { api } from "../../src/api/client";
const mockedApi = api as unknown as { getSession: ReturnType<typeof vi.fn> };

function renderAt(sessionId: string) {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false, refetchInterval: false } },
  });
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={[`/sessions/${sessionId}`]}>
        <Routes>
          <Route path="/sessions/:sessionId" element={<SessionDetailPage />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe("SessionDetailPage", () => {
  beforeEach(() => {
    mockedApi.getSession.mockReset();
  });

  it("renders topic, status, and all panel stubs", async () => {
    mockedApi.getSession.mockResolvedValue({
      session_id: "sess-x",
      user_id: "alice",
      research_topic: "My research",
      status: "running",
      preferences: {},
      config_overrides: {},
    });
    renderAt("sess-x");
    expect(await screen.findByText("My research")).toBeInTheDocument();
    expect(screen.getAllByText(/sess-x/).length).toBeGreaterThan(0);
    // Status appears both in topbar (Running) and ControlBar status row
    expect(screen.getAllByText(/Running/i).length).toBeGreaterThan(0);
    // Graph canvas stub is always rendered above the tabs
    expect(screen.getByTestId("graph-topology")).toBeInTheDocument();
    // Cost sider renders "Total cost" label
    expect(screen.getAllByText(/Total cost/i).length).toBeGreaterThan(0);
  });

  it("shows the conversations tab by default", async () => {
    mockedApi.getSession.mockResolvedValue({
      session_id: "sess-x",
      user_id: "alice",
      research_topic: "T",
      status: "running",
      preferences: {},
      config_overrides: {},
    });
    renderAt("sess-x");
    await screen.findByText("T");
    // The Conversations tab header is always rendered
    expect(
      screen.getByRole("tab", { name: /Conversations/i }),
    ).toBeInTheDocument();
  });

  it("shows an error alert when the session fetch fails", async () => {
    mockedApi.getSession.mockRejectedValue(new Error("no such session"));
    renderAt("sess-missing");
    await waitFor(() => {
      expect(screen.getByText(/Failed to load session/i)).toBeInTheDocument();
    });
    expect(screen.getByText(/no such session/)).toBeInTheDocument();
  });
});
