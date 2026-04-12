import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor, fireEvent } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import SessionListPage from "../../src/pages/SessionListPage";
import { useUIStore } from "../../src/stores/uiStore";

vi.mock("../../src/api/client", () => ({
  api: {
    listSessions: vi.fn(),
    deleteSession: vi.fn(),
  },
  APIError: class extends Error {},
  isValidationError: () => false,
}));

import { api } from "../../src/api/client";
const mockedApi = api as unknown as {
  listSessions: ReturnType<typeof vi.fn>;
  deleteSession: ReturnType<typeof vi.fn>;
};

function renderPage() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false, refetchInterval: false } },
  });
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter>
        <SessionListPage />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe("SessionListPage", () => {
  beforeEach(() => {
    mockedApi.listSessions.mockReset();
    mockedApi.deleteSession.mockReset();
    useUIStore.setState({ sessionListFilter: "" });
  });

  it("renders session rows from the API", async () => {
    mockedApi.listSessions.mockResolvedValue([
      {
        session_id: "sess-1",
        user_id: "alice",
        research_topic: "Neural scaling laws",
        status: "running",
      },
      {
        session_id: "sess-2",
        user_id: "bob",
        research_topic: "Transformer ablations",
        status: "completed",
      },
    ]);
    renderPage();
    expect(await screen.findByText("Neural scaling laws")).toBeInTheDocument();
    expect(screen.getByText("Transformer ablations")).toBeInTheDocument();
  });

  it("shows empty state with CTA when no sessions", async () => {
    mockedApi.listSessions.mockResolvedValue([]);
    renderPage();
    expect(
      await screen.findByText(/No sessions yet/i),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: /Start new session/i }),
    ).toBeInTheDocument();
  });

  it("filters by topic/id/user", async () => {
    mockedApi.listSessions.mockResolvedValue([
      {
        session_id: "sess-1",
        user_id: "alice",
        research_topic: "Neural scaling laws",
        status: "running",
      },
      {
        session_id: "sess-2",
        user_id: "bob",
        research_topic: "Transformer ablations",
        status: "completed",
      },
    ]);
    renderPage();
    await screen.findByText("Neural scaling laws");

    const input = screen.getByPlaceholderText(/Search by topic, user, or id/i);
    fireEvent.change(input, { target: { value: "scaling" } });

    expect(screen.queryByText("Transformer ablations")).not.toBeInTheDocument();
    expect(screen.getByText("Neural scaling laws")).toBeInTheDocument();
  });

  it("deletes a session with Popconfirm (Fix A)", async () => {
    const user = userEvent.setup();
    mockedApi.listSessions.mockResolvedValue([
      {
        session_id: "sess-del",
        user_id: "alice",
        research_topic: "Will be deleted",
        status: "created",
      },
    ]);
    mockedApi.deleteSession.mockResolvedValue(undefined);
    renderPage();
    await screen.findByText("Will be deleted");

    // Open popconfirm — row button's accessible name is "delete Delete"
    // (icon aria-label + visible text).
    const rowDelete = screen.getByRole("button", { name: /delete Delete/i });
    await user.click(rowDelete);

    // Confirm popover's OK button — after opening there are two "Delete"
    // buttons. The popover's OK has accessible name just "Delete" (no icon).
    const deleteBtns = await screen.findAllByRole("button", { name: /Delete/i });
    // The last one is the popover OK (appended to body after trigger click).
    await user.click(deleteBtns[deleteBtns.length - 1]);

    await waitFor(() => {
      expect(mockedApi.deleteSession).toHaveBeenCalledWith("sess-del");
    });
  });

  it("surfaces an API error message", async () => {
    mockedApi.listSessions.mockRejectedValue(new Error("backend down"));
    renderPage();
    expect(
      await screen.findByText(/Failed to load sessions/i),
    ).toBeInTheDocument();
    expect(screen.getByText(/backend down/)).toBeInTheDocument();
  });
});
