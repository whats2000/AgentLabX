import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

const sendMock = vi.fn();
vi.mock("../../src/api/wsRegistry", () => ({
  wsRegistry: {
    getSocket: () => ({ send: sendMock }),
  },
}));
vi.mock("../../src/api/client", () => ({
  api: { redirectSession: vi.fn() },
  APIError: class extends Error {},
  isValidationError: () => false,
}));

import { CheckpointModal } from "../../src/components/session/CheckpointModal";
import { useWSStore } from "../../src/stores/wsStore";

function renderModal() {
  const qc = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return render(
    <QueryClientProvider client={qc}>
      <CheckpointModal sessionId="sess-1" />
    </QueryClientProvider>,
  );
}

describe("CheckpointModal", () => {
  beforeEach(() => {
    useWSStore.setState({ events: {} });
    sendMock.mockReset();
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
