import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import type { ReactNode } from "react";

const { sendMock, getPIHistoryMock } = vi.hoisted(() => ({
  sendMock: vi.fn(),
  getPIHistoryMock: vi.fn().mockResolvedValue([]),
}));

vi.mock("../../src/api/wsRegistry", () => ({
  wsRegistry: {
    getSocket: () => ({ send: sendMock }),
  },
}));

vi.mock("../../src/api/client", () => ({
  api: { redirectSession: vi.fn(), getPIHistory: getPIHistoryMock },
  APIError: class extends Error {},
  isValidationError: () => false,
}));

import { CheckpointModal } from "../../src/components/session/CheckpointModal";
import { useWSStore } from "../../src/stores/wsStore";

function makeQC() {
  return new QueryClient({ defaultOptions: { queries: { retry: false } } });
}

function renderModal(qc = makeQC()) {
  return render(
    <QueryClientProvider client={qc}>
      <CheckpointModal sessionId="sess-1" />
    </QueryClientProvider>,
  );
}

function wrapper(qc = makeQC()) {
  return ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={qc}>{children}</QueryClientProvider>
  );
}

describe("CheckpointModal", () => {
  let fetchSpy: ReturnType<typeof vi.spyOn>;

  beforeEach(() => {
    useWSStore.setState({ events: {} });
    sendMock.mockReset();
    getPIHistoryMock.mockReset();
    getPIHistoryMock.mockResolvedValue([]);
    // Mock global fetch for checkpoint/approve calls
    fetchSpy = vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response(JSON.stringify({ status: "resumed", action: "approve" }), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      }),
    );
  });

  afterEach(() => {
    fetchSpy.mockRestore();
  });

  it("is closed when no checkpoint_reached event", () => {
    renderModal();
    expect(screen.queryByText(/Checkpoint:/)).not.toBeInTheDocument();
  });

  it("opens on checkpoint_reached and renders PI recommendation + output", () => {
    useWSStore.setState({
      events: {
        "sess-1": [
          {
            type: "checkpoint_reached",
            data: {
              stage: "experimentation",
              pi_recommendation: "Looks good",
              output: "results...",
            },
            timestamp: new Date().toISOString(),
          },
        ],
      },
    });
    renderModal();
    expect(screen.getByText("Checkpoint: experimentation")).toBeInTheDocument();
    expect(screen.getByText("Looks good")).toBeInTheDocument();
    expect(screen.getByText("results...")).toBeInTheDocument();
  });

  it("approve calls /checkpoint/approve endpoint and closes", async () => {
    const user = userEvent.setup();
    useWSStore.setState({
      events: {
        "sess-1": [
          {
            type: "checkpoint_reached",
            data: { stage: "experimentation" },
            timestamp: "t1",
          },
        ],
      },
    });
    renderModal();
    await user.click(screen.getByRole("button", { name: /Approve/ }));
    await waitFor(() => {
      expect(fetchSpy).toHaveBeenCalledWith(
        "/api/sessions/sess-1/checkpoint/approve",
        expect.objectContaining({
          method: "POST",
          body: expect.stringContaining('"action":"approve"'),
        }),
      );
    });
    await waitFor(() => {
      expect(screen.queryByText(/Checkpoint:/)).not.toBeInTheDocument();
    });
  });

  it("hides the Edit button when control_mode is 'approve'", async () => {
    useWSStore.setState({
      events: {
        "sess-1": [
          {
            type: "checkpoint_reached",
            data: { stage: "experimentation", output: "original", control_mode: "approve" },
            timestamp: "t2",
          },
        ],
      },
    });
    renderModal();
    // control_mode="approve" is binary approve/reject — no Edit button.
    expect(screen.queryByRole("button", { name: /Edit/i })).not.toBeInTheDocument();
    // Core action buttons are still present.
    expect(screen.getByRole("button", { name: /Approve/i })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Reject/i })).toBeInTheDocument();
  });

  it("hides the Edit button when control_mode is absent (default approve UX)", async () => {
    useWSStore.setState({
      events: {
        "sess-1": [
          {
            type: "checkpoint_reached",
            data: { stage: "experimentation", output: "original" },
            timestamp: "t2b",
          },
        ],
      },
    });
    renderModal();
    // No control_mode set → default approve/reject only, no Edit.
    expect(screen.queryByRole("button", { name: /Edit/i })).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Approve/i })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Reject/i })).toBeInTheDocument();
  });

  it("shows the Edit button when control_mode is 'edit'", async () => {
    const user = userEvent.setup();
    useWSStore.setState({
      events: {
        "sess-1": [
          {
            type: "checkpoint_reached",
            data: { stage: "experimentation", output: "original", control_mode: "edit" },
            timestamp: "t3",
          },
        ],
      },
    });
    renderModal();
    // control_mode="edit" → Edit button is present.
    const editBtn = screen.getByRole("button", { name: /Edit/i });
    expect(editBtn).toBeInTheDocument();
    // Clicking it shows a "not yet implemented" info message (no crash).
    await user.click(editBtn);
    // Core action buttons remain.
    expect(screen.getByRole("button", { name: /Approve/i })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Reject/i })).toBeInTheDocument();
  });
});

describe("CheckpointModal PI advice surfacing", () => {
  beforeEach(() => {
    useWSStore.setState({
      events: {
        "sess-1": [
          {
            type: "checkpoint_reached",
            data: { stage: "experimentation" },
            timestamp: "t-pi",
          },
        ],
      },
    });
    sendMock.mockReset();
    getPIHistoryMock.mockReset();
  });

  it("shows PI advice when latest decision is confident and not a fallback", async () => {
    getPIHistoryMock.mockResolvedValue([
      {
        decision_id: "d1",
        action: "advance",
        checkpoint: "backtrack_limit",
        next_stage: "plan_formulation",
        reasoning: "Pivot the hypothesis after repeated experiment failures",
        confidence: 0.85,
        used_fallback: false,
        ts: "2026-04-14T10:00:00Z",
      },
    ]);

    render(<CheckpointModal sessionId="sess-1" />, { wrapper: wrapper() });

    expect(await screen.findByText(/PI advisor/i)).toBeInTheDocument();
    expect(await screen.findByText(/plan_formulation/i)).toBeInTheDocument();
    expect(await screen.findByText(/85%/)).toBeInTheDocument();
    expect(
      await screen.findByText(/Pivot the hypothesis/i),
    ).toBeInTheDocument();
  });

  it("does NOT show PI advice banner when latest decision used_fallback=true", async () => {
    getPIHistoryMock.mockResolvedValue([
      {
        decision_id: "d2",
        action: "advance",
        checkpoint: "backtrack_limit",
        next_stage: "peer_review",
        reasoning: "defer to rule fallback",
        confidence: 0.3,
        used_fallback: true,
        ts: "2026-04-14T10:00:00Z",
      },
    ]);

    render(<CheckpointModal sessionId="sess-1" />, { wrapper: wrapper() });

    // Wait for query to resolve before asserting absence
    await waitFor(() => expect(getPIHistoryMock).toHaveBeenCalled());
    expect(screen.queryByText(/PI advisor recommends/i)).toBeNull();
  });

  it("does NOT show PI advice banner when pi_decisions is empty", async () => {
    getPIHistoryMock.mockResolvedValue([]);

    render(<CheckpointModal sessionId="sess-1" />, { wrapper: wrapper() });

    await waitFor(() => expect(getPIHistoryMock).toHaveBeenCalled());
    expect(screen.queryByText(/PI advisor recommends/i)).toBeNull();
  });
});
