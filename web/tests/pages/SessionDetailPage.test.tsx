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
    // Status appears both in topbar (Running) — we only assert its presence
    expect(screen.getAllByText(/Running/i).length).toBeGreaterThan(0);
    // Cost sider renders "Total cost" label — sanity check that the panels
    // mount (Task 13 replaced the stub with real content).
    expect(screen.getAllByText(/Total cost/i).length).toBeGreaterThan(0);
  });

  it("shows the activity tab by default", async () => {
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
    // The Activity tab header is always rendered
    expect(screen.getByRole("tab", { name: /Activity/i })).toBeInTheDocument();
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
