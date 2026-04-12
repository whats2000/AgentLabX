import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

vi.mock("../../src/api/client", () => ({
  api: {
    getSession: vi.fn(),
    startSession: vi.fn(),
    pauseSession: vi.fn(),
    resumeSession: vi.fn(),
    redirectSession: vi.fn(),
    updatePreferences: vi.fn(),
  },
  APIError: class extends Error {},
  isValidationError: () => false,
}));

import { ControlBar } from "../../src/components/session/ControlBar";
import { api } from "../../src/api/client";

const mocked = api as unknown as Record<string, ReturnType<typeof vi.fn>>;

function renderAt(status: string, preferences: Record<string, unknown> = {}) {
  mocked.getSession.mockResolvedValue({
    session_id: "sess-1",
    user_id: "u",
    research_topic: "t",
    status,
    preferences,
    config_overrides: {},
  });
  const qc = new QueryClient({
    defaultOptions: { queries: { retry: false, refetchInterval: false } },
  });
  return render(
    <QueryClientProvider client={qc}>
      <ControlBar sessionId="sess-1" />
    </QueryClientProvider>,
  );
}

describe("ControlBar", () => {
  beforeEach(() => {
    Object.values(mocked).forEach((m) => m.mockReset());
  });

  it("shows Start when session is created", async () => {
    renderAt("created");
    expect(
      await screen.findByRole("button", { name: /Start session/i }),
    ).toBeInTheDocument();
  });

  it("shows Pause when session is running", async () => {
    renderAt("running");
    // AntD icons contribute an aria-label ("pause-circle") to the
    // accessible name, so match on the "Pause" word anywhere.
    expect(
      await screen.findByRole("button", { name: /\bPause\b/ }),
    ).toBeInTheDocument();
  });

  it("shows Resume when session is paused", async () => {
    renderAt("paused");
    expect(
      await screen.findByRole("button", { name: /Resume/i }),
    ).toBeInTheDocument();
  });

  it("fires startSession when clicked", async () => {
    const user = userEvent.setup();
    mocked.startSession.mockResolvedValue({});
    renderAt("created");
    const start = await screen.findByRole("button", { name: /Start session/i });
    await user.click(start);
    await waitFor(() => {
      expect(mocked.startSession).toHaveBeenCalled();
    });
  });

  it("calls updatePreferences when Mode toggles to HITL", async () => {
    const user = userEvent.setup();
    mocked.updatePreferences.mockResolvedValue({});
    renderAt("created", { mode: "auto" });
    await screen.findByRole("button", { name: /Start session/i });
    const hitl = screen.getByText("HITL");
    await user.click(hitl);
    await waitFor(() => {
      expect(mocked.updatePreferences).toHaveBeenCalledWith("sess-1", {
        mode: "hitl",
      });
    });
  });
});
