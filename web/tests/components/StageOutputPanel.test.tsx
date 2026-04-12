import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { StageOutputPanel } from "../../src/components/session/StageOutputPanel";

vi.mock("../../src/api/client", () => ({
  api: { getArtifacts: vi.fn() },
  APIError: class extends Error {},
  isValidationError: () => false,
}));

import { api } from "../../src/api/client";
const mocked = api as unknown as { getArtifacts: ReturnType<typeof vi.fn> };

function renderPanel(opts: { compact?: boolean } = {}) {
  const qc = new QueryClient({
    defaultOptions: { queries: { retry: false, refetchInterval: false } },
  });
  return render(
    <QueryClientProvider client={qc}>
      <StageOutputPanel sessionId="sess-1" compact={opts.compact} />
    </QueryClientProvider>,
  );
}

describe("StageOutputPanel", () => {
  beforeEach(() => {
    mocked.getArtifacts.mockReset();
  });

  it("renders all 8 tabs", async () => {
    mocked.getArtifacts.mockResolvedValue({
      literature_review: [],
      plan: [],
      data_exploration: [],
      dataset_code: [],
      experiment_results: [],
      interpretation: [],
      report: [],
      review: [],
    });
    renderPanel();
    await waitFor(() => {
      expect(
        screen.getByRole("tab", { name: /Literature/i }),
      ).toBeInTheDocument();
    });
    expect(screen.getByRole("tab", { name: /Plan/i })).toBeInTheDocument();
    expect(
      screen.getByRole("tab", { name: /Experiments/i }),
    ).toBeInTheDocument();
  });

  it("shows paper titles from a literature review", async () => {
    mocked.getArtifacts.mockResolvedValue({
      literature_review: [
        {
          papers: [{ title: "Attention Is All You Need", year: 2017 }],
          summary: "Transformer overview",
        },
      ],
      plan: [],
      data_exploration: [],
      dataset_code: [],
      experiment_results: [],
      interpretation: [],
      report: [],
      review: [],
    });
    renderPanel();
    expect(
      await screen.findByText("Attention Is All You Need"),
    ).toBeInTheDocument();
    expect(screen.getByText(/Transformer overview/)).toBeInTheDocument();
  });

  it("compact mode renders 'Latest' marker pointing at the populated section", async () => {
    mocked.getArtifacts.mockResolvedValue({
      literature_review: [{ papers: [], summary: "x" }],
      plan: [{ goals: [], methodology: "m", hypotheses: [], full_text: "" }],
      data_exploration: [],
      dataset_code: [],
      experiment_results: [],
      interpretation: [],
      report: [],
      review: [],
    });
    renderPanel({ compact: true });
    expect(await screen.findByText(/Latest:/i)).toBeInTheDocument();
    expect(screen.getByText(/Plan/)).toBeInTheDocument();
  });

  it("compact mode empty state", async () => {
    mocked.getArtifacts.mockResolvedValue({
      literature_review: [],
      plan: [],
      data_exploration: [],
      dataset_code: [],
      experiment_results: [],
      interpretation: [],
      report: [],
      review: [],
    });
    renderPanel({ compact: true });
    expect(await screen.findByText(/No outputs yet/i)).toBeInTheDocument();
  });
});
