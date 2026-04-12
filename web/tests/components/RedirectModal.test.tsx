import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

vi.mock("../../src/api/client", () => ({
  api: { redirectSession: vi.fn() },
  APIError: class extends Error {},
  isValidationError: () => false,
}));

import { RedirectModal } from "../../src/components/session/RedirectModal";
import { api } from "../../src/api/client";

const mocked = api as unknown as {
  redirectSession: ReturnType<typeof vi.fn>;
};

function renderIt(open = true) {
  const qc = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  const onClose = vi.fn();
  const view = render(
    <QueryClientProvider client={qc}>
      <RedirectModal sessionId="sess-1" open={open} onClose={onClose} />
    </QueryClientProvider>,
  );
  return { ...view, onClose };
}

describe("RedirectModal", () => {
  beforeEach(() => {
    mocked.redirectSession.mockReset();
  });

  it("sends a redirect on OK when form is valid", async () => {
    const user = userEvent.setup();
    mocked.redirectSession.mockResolvedValue({});
    const { onClose } = renderIt();
    await user.click(screen.getByRole("combobox"));
    await user.click(await screen.findByText(/Plan Formulation/));
    await user.click(screen.getByRole("button", { name: /Send redirect/i }));
    await waitFor(() => {
      expect(mocked.redirectSession).toHaveBeenCalledWith("sess-1", {
        target_stage: "plan_formulation",
        reason: "",
      });
    });
    expect(onClose).toHaveBeenCalled();
  });

  it("blocks submit when no stage is picked", async () => {
    const user = userEvent.setup();
    mocked.redirectSession.mockResolvedValue({});
    renderIt();
    await user.click(screen.getByRole("button", { name: /Send redirect/i }));
    expect(mocked.redirectSession).not.toHaveBeenCalled();
    expect(await screen.findByText(/Pick a stage/i)).toBeInTheDocument();
  });
});
