import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor, fireEvent } from "@testing-library/react";
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
    getGraph: vi.fn().mockResolvedValue({
      nodes: [],
      edges: [],
      cursor: null,
      subgraphs: [],
    }),
    listAgents: vi.fn().mockResolvedValue([]),
    getPIHistory: vi.fn().mockResolvedValue([]),
    getExperiments: vi.fn().mockResolvedValue({ runs: [], log: [] }),
    getRequests: vi.fn().mockResolvedValue({ pending: [], completed: [] }),
    getAgentContext: vi.fn().mockResolvedValue(null),
    getAgentMemory: vi.fn().mockResolvedValue(null),
    getAgentHistory: vi.fn().mockResolvedValue({ turns: [], next_cursor: null }),
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
  GraphTopology: ({ onStageClick }: { onStageClick?: (id: string) => void }) => (
    <div
      data-testid="graph-topology"
      onClick={() => onStageClick?.("literature_review")}
    />
  ),
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
vi.mock("../../src/components/session/StageSubgraphDrawer", () => ({
  StageSubgraphDrawer: () => (
    <div data-testid="stage-subgraph-drawer" />
  ),
}));
vi.mock("../../src/components/session/LabMeetingOverlay", () => ({
  LabMeetingOverlay: () => (
    <div data-testid="lab-meeting-overlay" />
  ),
}));
vi.mock("../../src/components/session/FeedbackInput", () => ({
  FeedbackInput: () => <div data-testid="feedback-input" />,
}));
vi.mock("../../src/components/session/CheckpointModal", () => ({
  CheckpointModal: () => <div data-testid="checkpoint-modal" />,
}));
vi.mock("../../src/components/session/StagePlanCard", () => ({
  StagePlanCard: () => <div data-testid="stage-plan-card" />,
}));
vi.mock("../../src/components/session/HypothesisTracker", () => ({
  HypothesisTracker: () => <div data-testid="hypothesis-tracker" />,
}));

import { api } from "../../src/api/client";
import { useUIStore } from "../../src/stores/uiStore";
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

const SESSION = {
  session_id: "sess-x",
  user_id: "alice",
  research_topic: "My research topic",
  status: "running",
  preferences: {},
  config_overrides: {},
};

describe("SessionDetailPage", () => {
  beforeEach(() => {
    mockedApi.getSession.mockReset();
    // Reset uiStore panel state before each test
    useUIStore.setState({
      innerPanelOpen: false,
      meetingPanelOpen: false,
      drawerOpen: false,
      drawerTab: "monitor",
    });
  });

  it("renders session topic and session id in header", async () => {
    mockedApi.getSession.mockResolvedValue(SESSION);
    renderAt("sess-x");
    expect(await screen.findByText("My research topic")).toBeInTheDocument();
    expect(screen.getAllByText(/sess-x/).length).toBeGreaterThan(0);
  });

  it("always renders GraphTopology", async () => {
    mockedApi.getSession.mockResolvedValue(SESSION);
    renderAt("sess-x");
    await screen.findByText("My research topic");
    expect(screen.getByTestId("graph-topology")).toBeInTheDocument();
  });

  it("renders ChatView in main content area", async () => {
    mockedApi.getSession.mockResolvedValue(SESSION);
    renderAt("sess-x");
    await screen.findByText("My research topic");
    expect(screen.getByTestId("chat-view")).toBeInTheDocument();
  });

  it("renders FeedbackInput at bottom", async () => {
    mockedApi.getSession.mockResolvedValue(SESSION);
    renderAt("sess-x");
    await screen.findByText("My research topic");
    expect(screen.getByTestId("feedback-input")).toBeInTheDocument();
  });

  it("does NOT render StageSubgraphDrawer when innerPanelOpen is false", async () => {
    mockedApi.getSession.mockResolvedValue(SESSION);
    renderAt("sess-x");
    await screen.findByText("My research topic");
    expect(screen.queryByTestId("stage-subgraph-drawer")).toBeNull();
  });

  it("renders StageSubgraphDrawer when innerPanelOpen is true", async () => {
    mockedApi.getSession.mockResolvedValue(SESSION);
    // Pre-open inner panel
    useUIStore.setState({ innerPanelOpen: true });
    renderAt("sess-x");
    await screen.findByText("My research topic");
    expect(screen.getByTestId("stage-subgraph-drawer")).toBeInTheDocument();
  });

  it("does NOT render LabMeetingOverlay when only innerPanelOpen is true (meetingPanelOpen false)", async () => {
    mockedApi.getSession.mockResolvedValue(SESSION);
    useUIStore.setState({ innerPanelOpen: true, meetingPanelOpen: false });
    renderAt("sess-x");
    await screen.findByText("My research topic");
    expect(screen.queryByTestId("lab-meeting-overlay")).toBeNull();
  });

  it("shows 'Details' button that opens drawer on click", async () => {
    mockedApi.getSession.mockResolvedValue(SESSION);
    renderAt("sess-x");
    await screen.findByText("My research topic");
    const btn = screen.getByTestId("drawer-toggle");
    expect(btn).toBeInTheDocument();
    fireEvent.click(btn);
    // After click, drawerOpen should be toggled via store
    expect(useUIStore.getState().drawerOpen).toBe(true);
  });

  it("renders Monitor tab label inside drawer when drawer is open", async () => {
    mockedApi.getSession.mockResolvedValue(SESSION);
    useUIStore.setState({ drawerOpen: true, drawerTab: "monitor" });
    renderAt("sess-x");
    await screen.findByText("My research topic");
    expect(screen.getByTestId("agent-monitor")).toBeInTheDocument();
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
