import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

vi.mock("../../src/api/client", () => ({
  api: { getCost: vi.fn(), getSession: vi.fn() },
  APIError: class extends Error {},
  isValidationError: () => false,
}));
vi.mock("../../src/components/session/CostGauge", () => ({
  CostGauge: () => <div data-testid="cost-gauge" />,
}));
vi.mock("../../src/components/session/CostLine", () => ({
  CostLine: () => <div data-testid="cost-line" />,
}));

import { CostTracker } from "../../src/components/session/CostTracker";
import { useWSStore } from "../../src/stores/wsStore";
import { api } from "../../src/api/client";

const mocked = api as unknown as {
  getCost: ReturnType<typeof vi.fn>;
  getSession: ReturnType<typeof vi.fn>;
};

function render_(compact = false) {
  const qc = new QueryClient({
    defaultOptions: { queries: { retry: false, refetchInterval: false } },
  });
  return render(
    <QueryClientProvider client={qc}>
      <CostTracker sessionId="sess-1" compact={compact} />
    </QueryClientProvider>,
  );
}

describe("CostTracker", () => {
  beforeEach(() => {
    useWSStore.setState({ events: {} });
    mocked.getCost.mockReset();
    mocked.getSession.mockReset();
    mocked.getSession.mockResolvedValue({
      session_id: "sess-1",
      user_id: "u",
      research_topic: "t",
      status: "running",
      preferences: {},
      config_overrides: {},
    });
  });

  it("renders the three statistic cards in full mode", async () => {
    mocked.getCost.mockResolvedValue({
      total_tokens_in: 12_000,
      total_tokens_out: 4_000,
      total_cost: 0.0512,
    });
    render_();
    expect(await screen.findByText("Tokens in")).toBeInTheDocument();
    expect(screen.getByText("Tokens out")).toBeInTheDocument();
    expect(screen.getByText("Total cost")).toBeInTheDocument();
  });

  it("shows 'No cost ceiling' when none configured", async () => {
    mocked.getCost.mockResolvedValue({
      total_tokens_in: 0,
      total_tokens_out: 0,
      total_cost: 0,
    });
    render_();
    expect(
      await screen.findByText(/No cost ceiling configured/i),
    ).toBeInTheDocument();
  });

  it("renders gauge when ceiling is set in config_overrides", async () => {
    mocked.getSession.mockResolvedValue({
      session_id: "sess-1",
      user_id: "u",
      research_topic: "t",
      status: "running",
      preferences: {},
      config_overrides: { llm: { cost_ceiling: 10.0 } },
    });
    mocked.getCost.mockResolvedValue({
      total_tokens_in: 0,
      total_tokens_out: 0,
      total_cost: 5.0,
    });
    render_();
    expect(await screen.findByTestId("cost-gauge")).toBeInTheDocument();
  });

  it("empty state on cost over time chart when no cost_update events", async () => {
    mocked.getCost.mockResolvedValue({
      total_tokens_in: 0,
      total_tokens_out: 0,
      total_cost: 0,
    });
    render_();
    expect(
      await screen.findByText(/Waiting for cost_update events/i),
    ).toBeInTheDocument();
  });

  it("renders line chart when cost_update events exist", async () => {
    useWSStore.setState({
      events: {
        "sess-1": [
          {
            type: "cost_update",
            data: { total_cost: 0.01 },
            timestamp: new Date().toISOString(),
          },
          {
            type: "cost_update",
            data: { total_cost: 0.03 },
            timestamp: new Date().toISOString(),
          },
        ],
      },
    });
    mocked.getCost.mockResolvedValue({
      total_tokens_in: 0,
      total_tokens_out: 0,
      total_cost: 0.03,
    });
    render_();
    expect(await screen.findByTestId("cost-line")).toBeInTheDocument();
  });

  it("compact mode shows total cost only", async () => {
    mocked.getCost.mockResolvedValue({
      total_tokens_in: 1000,
      total_tokens_out: 500,
      total_cost: 0.02,
    });
    render_(true);
    expect(await screen.findByText("$0.0200")).toBeInTheDocument();
    expect(screen.getByText(/Total cost/i)).toBeInTheDocument();
    expect(screen.getByText(/1,500 tokens total/)).toBeInTheDocument();
  });
});
