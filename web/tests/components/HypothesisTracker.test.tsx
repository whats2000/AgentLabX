import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { HypothesisTracker } from "../../src/components/session/HypothesisTracker";

vi.mock("../../src/api/client", () => ({
  api: { getHypotheses: vi.fn() },
  APIError: class extends Error {},
  isValidationError: () => false,
}));

import { api } from "../../src/api/client";
const mocked = api as unknown as {
  getHypotheses: ReturnType<typeof vi.fn>;
};

function renderTracker() {
  const qc = new QueryClient({
    defaultOptions: { queries: { retry: false, refetchInterval: false } },
  });
  return render(
    <QueryClientProvider client={qc}>
      <HypothesisTracker sessionId="sess-1" />
    </QueryClientProvider>,
  );
}

describe("HypothesisTracker", () => {
  beforeEach(() => {
    mocked.getHypotheses.mockReset();
  });

  // Backend wraps the list in {hypotheses, total_records}; the hook flattens
  // it. Tests mock the raw envelope shape.
  it("renders empty state when the envelope has no hypotheses", async () => {
    mocked.getHypotheses.mockResolvedValue({
      hypotheses: [],
      total_records: 0,
    });
    renderTracker();
    expect(await screen.findByText(/No hypotheses yet/)).toBeInTheDocument();
  });

  it("renders hypothesis cards with status tag and statement", async () => {
    mocked.getHypotheses.mockResolvedValue({
      hypotheses: [
        {
          id: "H1",
          statement: "Pretraining scales with compute",
          status: "active",
          created_at_stage: "plan_formulation",
          evidence_for: [
            {
              experiment_result_index: 0,
              metric: "acc",
              value: 0.9,
              interpretation: "yes",
            },
          ],
          evidence_against: [],
        },
        {
          id: "H2",
          statement: "Dropout helps convergence",
          status: "refuted",
          created_at_stage: "plan_formulation",
        },
      ],
      total_records: 2,
    });
    renderTracker();
    expect(
      await screen.findByText("Pretraining scales with compute"),
    ).toBeInTheDocument();
    expect(screen.getByText("Dropout helps convergence")).toBeInTheDocument();
    expect(screen.getByText(/active/i)).toBeInTheDocument();
    expect(screen.getByText(/refuted/i)).toBeInTheDocument();
    expect(screen.getByText(/1 supporting · 0 against/)).toBeInTheDocument();
  });
});
