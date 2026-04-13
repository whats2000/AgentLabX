import { render, screen } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { vi, describe, it, expect, beforeEach } from "vitest";
import { GraphTopology } from "../../src/components/session/GraphTopology";

vi.mock("../../src/api/client", () => ({
  api: {
    getGraph: vi.fn().mockResolvedValue({
      nodes: [
        {id: "literature_review", type: "stage", label: "Literature Review",
         zone: "discovery", status: "complete", iteration_count: 1, skipped: false},
        {id: "plan_formulation", type: "stage", label: "Plan Formulation",
         zone: "discovery", status: "active", iteration_count: 2, skipped: false},
        {id: "peer_review", type: "stage", label: "Peer Review",
         zone: "synthesis", status: "skipped", iteration_count: 0, skipped: true},
      ],
      edges: [
        {from: "literature_review", to: "plan_formulation", kind: "sequential", reason: null},
      ],
      cursor: {node_id: "plan_formulation", agent: "postdoc", started_at: null},
      subgraphs: [],
    }),
  },
}));

function renderIt() {
  const qc = new QueryClient({defaultOptions: {queries: {retry: false}}});
  return render(
    <QueryClientProvider client={qc}>
      <GraphTopology sessionId="s1" />
    </QueryClientProvider>
  );
}

describe("GraphTopology", () => {
  beforeEach(() => {
    // React Flow needs a non-zero viewport — jsdom provides zero by default.
    globalThis.ResizeObserver = class {
      observe() {}
      unobserve() {}
      disconnect() {}
    } as any;

    // React Flow also needs getBoundingClientRect to return non-zero dimensions.
    globalThis.HTMLElement.prototype.getBoundingClientRect = vi.fn(() => ({
      width: 400, height: 400, x: 0, y: 0, top: 0, left: 0, bottom: 400, right: 400, toJSON: () => ({}),
    }));
  });

  it("renders one node per topology node", async () => {
    renderIt();
    expect(await screen.findByText("Plan Formulation")).toBeInTheDocument();
    expect(screen.getByText("Literature Review")).toBeInTheDocument();
    expect(screen.getByText("Peer Review")).toBeInTheDocument();
  });

  it("marks skipped nodes with data-status attribute", async () => {
    renderIt();
    const node = await screen.findByTestId("stage-node-peer_review");
    expect(node.getAttribute("data-status")).toBe("skipped");
  });

  it("shows iteration count on active node", async () => {
    renderIt();
    expect(await screen.findByText(/iter 2/i)).toBeInTheDocument();
  });
});
