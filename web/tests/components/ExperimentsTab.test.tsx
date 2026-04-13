import { render, screen } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { vi, describe, it, expect } from "vitest";
import { ExperimentsTab } from "../../src/components/session/ExperimentsTab";

vi.mock("../../src/api/client", () => ({
  api: {
    getExperiments: vi.fn().mockResolvedValue({
      runs: [{
        index: 0,
        tag: "baseline",
        metrics: {acc: 0.62},
        description: "base cot",
        reproducibility: {random_seed: 42, run_command: "python base.py"},
        stdout: "epoch 1/10\naccuracy: 0.62",
        stderr: "",
        exit_code: 0,
      }],
      log: [{
        attempt_id: "a1",
        outcome: "failure",
        failure_reason: "timeout",
        learnings: [],
        approach_summary: "tried 20-shot CoT",
        linked_hypothesis_id: null,
        ts: "2026-04-13T00:00:00",
      }],
    }),
  },
}));

describe("ExperimentsTab", () => {
  it("lists each run and shows prior failures ribbon", async () => {
    const qc = new QueryClient({defaultOptions: {queries: {retry: false}}});
    render(
      <QueryClientProvider client={qc}>
        <ExperimentsTab sessionId="s1" />
      </QueryClientProvider>
    );
    expect(await screen.findByText(/baseline/i)).toBeInTheDocument();
    expect(screen.getByText(/0\.62/)).toBeInTheDocument();
    expect(screen.getByText(/prior attempts/i)).toBeInTheDocument();
    expect(screen.getByText(/timeout/)).toBeInTheDocument();
  });

  it("shows empty state when no experiments", async () => {
    const api = await import("../../src/api/client");
    (api.api.getExperiments as any).mockResolvedValueOnce({runs: [], log: []});
    const qc = new QueryClient({defaultOptions: {queries: {retry: false}}});
    render(
      <QueryClientProvider client={qc}>
        <ExperimentsTab sessionId="s1" />
      </QueryClientProvider>
    );
    expect(await screen.findByText(/no experiments yet/i)).toBeInTheDocument();
  });
});
