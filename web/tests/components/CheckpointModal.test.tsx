import { describe, it, expect, vi, beforeEach } from "vitest";
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
  beforeEach(() => {
    useWSStore.setState({ events: {} });
    sendMock.mockReset();
    getPIHistoryMock.mockReset();
    getPIHistoryMock.mockResolvedValue([]);
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

  it("approve sends action and closes", async () => {
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
    expect(sendMock).toHaveBeenCalledWith({ action: "approve" });
    await waitFor(() => {
      expect(screen.queryByText(/Checkpoint:/)).not.toBeInTheDocument();
    });
  });

  it("edit reveals textarea and Save sends edit action", async () => {
    const user = userEvent.setup();
    useWSStore.setState({
      events: {
        "sess-1": [
          {
            type: "checkpoint_reached",
            data: { stage: "experimentation", output: "original" },
            timestamp: "t2",
          },
        ],
      },
    });
    renderModal();
    // Two visible buttons match /Edit/: "Edit" and "Edit" inside icon aria.
    // Match the exact visible label by finding the span text.
    const editBtns = screen.getAllByRole("button", { name: /Edit/ });
    // Approve/Redirect buttons don't include "Edit"; the Edit button is the
    // one whose accessible name matches exactly "Edit" (case-insensitive)
    // once the "edit " aria-label prefix is stripped. We look for the button
    // whose text content is exactly "Edit".
    const editBtn =
      editBtns.find((b) => b.textContent?.trim() === "Edit") ?? editBtns[0];
    await user.click(editBtn);
    const ta = screen.getByRole("textbox");
    await user.clear(ta);
    await user.type(ta, "edited");
    await user.click(screen.getByRole("button", { name: /Save/ }));
    expect(sendMock).toHaveBeenCalledWith({
      action: "edit",
      content: "edited",
    });
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
