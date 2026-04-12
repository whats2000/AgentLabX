import { describe, it, expect, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import AppShell from "../../src/components/AppShell";
import SessionListPage from "../../src/pages/SessionListPage";
import PluginBrowserPage from "../../src/pages/PluginBrowserPage";

// The session list page now issues a real API call on mount; mock the client
// so AppShell routing tests don't hit the network.
vi.mock("../../src/api/client", () => ({
  api: {
    listSessions: vi.fn().mockResolvedValue([]),
    deleteSession: vi.fn(),
  },
  APIError: class extends Error {},
  isValidationError: () => false,
}));

function renderAt(initialPath: string) {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false, refetchInterval: false } },
  });
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={[initialPath]}>
        <Routes>
          <Route element={<AppShell />}>
            <Route path="sessions" element={<SessionListPage />} />
            <Route path="plugins" element={<PluginBrowserPage />} />
          </Route>
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe("AppShell", () => {
  it("renders the sessions page under /sessions", () => {
    renderAt("/sessions");
    // The page-level title is "Sessions" (h3) + a description line.
    expect(
      screen.getByText(/Create, monitor, and manage research sessions/i),
    ).toBeInTheDocument();
  });

  it("renders the plugins stub under /plugins", () => {
    renderAt("/plugins");
    expect(screen.getByText(/Plugins \(stub\)/i)).toBeInTheDocument();
  });

  it("renders the AgentLabX header", () => {
    renderAt("/sessions");
    expect(screen.getAllByText(/AgentLabX/i).length).toBeGreaterThan(0);
  });
});
