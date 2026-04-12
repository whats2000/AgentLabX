import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

vi.mock("../../src/api/client", () => ({
  api: { getSession: vi.fn() },
  APIError: class extends Error {},
  isValidationError: () => false,
}));

import { PipelineTracker } from "../../src/components/session/PipelineTracker";
import { api } from "../../src/api/client";

const mockedApi = api as unknown as { getSession: ReturnType<typeof vi.fn> };

function renderTracker() {
  const qc = new QueryClient({
    defaultOptions: { queries: { retry: false, refetchInterval: false } },
  });
  return render(
    <QueryClientProvider client={qc}>
      <PipelineTracker sessionId="sess-1" />
    </QueryClientProvider>,
  );
}

describe("PipelineTracker", () => {
  beforeEach(() => {
    mockedApi.getSession.mockReset();
  });

  it("renders all 8 stages", async () => {
    mockedApi.getSession.mockResolvedValue({
      session_id: "sess-1",
      user_id: "u",
      research_topic: "t",
      status: "created",
      current_stage: "",
      completed_stages: [],
      preferences: {},
      config_overrides: {},
    });
    renderTracker();
    expect(await screen.findByText("Literature Review")).toBeInTheDocument();
    expect(screen.getByText("Peer Review")).toBeInTheDocument();
  });

  it("marks current stage with process status", async () => {
    mockedApi.getSession.mockResolvedValue({
      session_id: "sess-1",
      user_id: "u",
      research_topic: "t",
      status: "running",
      current_stage: "experimentation",
      completed_stages: [
        "literature_review",
        "plan_formulation",
        "data_exploration",
        "data_preparation",
      ],
      preferences: {},
      config_overrides: {},
    });
    const { container } = renderTracker();
    await screen.findByText("Experimentation");
    // Wait for the session query to resolve and the component to re-render
    // with per-stage statuses. The current step carries the
    // ant-steps-item-process class; the first step (completed) carries
    // ant-steps-item-finish.
    await waitFor(() => {
      const items = Array.from(container.querySelectorAll(".ant-steps-item"));
      const expItem = items.find((el) =>
        el.textContent?.includes("Experimentation"),
      );
      expect(expItem?.className).toContain("ant-steps-item-process");
      const litItem = items.find((el) =>
        el.textContent?.includes("Literature Review"),
      );
      expect(litItem?.className).toContain("ant-steps-item-finish");
    });
  });
});
