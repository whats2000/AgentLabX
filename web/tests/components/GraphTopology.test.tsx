import { render, screen, waitFor, fireEvent } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { vi, describe, it, expect, beforeEach } from "vitest";
import type { ReactNode } from "react";

// ---------------------------------------------------------------------------
// Mock @xyflow/react so edges/nodes are rendered as real DOM elements.
// React Flow relies on browser layout; jsdom cannot provide it.
// ---------------------------------------------------------------------------
vi.mock("@xyflow/react", async () => {
  const { useState, useCallback } = await import("react");

  type RfNode = { id: string; type?: string; data?: unknown; position?: unknown };
  type RfEdge = { id: string; source: string; target: string; label?: ReactNode };

  return {
    ReactFlow: ({
      nodes = [] as RfNode[],
      edges = [] as RfEdge[],
      nodeTypes = {} as Record<string, (p: { data: unknown }) => ReactNode>,
    }: {
      nodes?: RfNode[];
      edges?: RfEdge[];
      nodeTypes?: Record<string, (p: { data: unknown }) => ReactNode>;
    }) => (
      <div data-testid="rf__wrapper">
        <div className="react-flow__nodes">
          {nodes.map((n) => {
            const Comp = nodeTypes[n.type ?? ""];
            return Comp ? (
              <Comp key={n.id} data={n.data} />
            ) : (
              <div key={n.id} data-node-id={n.id} />
            );
          })}
        </div>
        <div className="react-flow__edges">
          {edges.map((e) => (
            <div
              key={e.id}
              className="react-flow__edge"
              data-source={e.source}
              data-target={e.target}
            >
              {e.label != null && <span>{e.label}</span>}
            </div>
          ))}
        </div>
      </div>
    ),
    Background: () => null,
    Controls: () => null,
    useNodesState: <T,>(initial: T[]) => {
      const [nodes, setNodes] = useState<T[]>(initial ?? []);
      const onNodesChange = useCallback(() => {}, []);
      return [nodes, setNodes, onNodesChange] as const;
    },
    useEdgesState: <T,>(initial: T[]) => {
      const [edges, setEdges] = useState<T[]>(initial ?? []);
      const onEdgesChange = useCallback(() => {}, []);
      return [edges, setEdges, onEdgesChange] as const;
    },
    Handle: ({ type, position }: { type: string; position: string }) => (
      <div data-handle-type={type} data-handle-position={position} />
    ),
    Position: { Left: "left", Right: "right", Top: "top", Bottom: "bottom" },
  };
});

// ---------------------------------------------------------------------------
// Mock elkjs so layout resolves immediately with deterministic positions.
// ---------------------------------------------------------------------------
vi.mock("elkjs/lib/elk.bundled.js", () => ({
  default: class MockELK {
    layout(graph: {
      children?: Array<{ id: string; children?: Array<{ id: string }> }>;
    }) {
      return Promise.resolve({
        ...graph,
        x: 0,
        y: 0,
        width: 800,
        height: 600,
        children: (graph.children ?? []).map((c, ci) => ({
          ...c,
          x: ci * 260,
          y: 0,
          width: 240,
          height: 120,
          children: (c.children ?? []).map((ch, chi) => ({
            ...ch,
            x: 16,
            y: 28 + chi * 90,
            width: 200,
            height: 70,
          })),
        })),
      });
    }
  },
}));

// ---------------------------------------------------------------------------
// Mock the API client for the hook-driven tests.
// ---------------------------------------------------------------------------
vi.mock("../../src/api/client", () => ({
  api: {
    getGraph: vi.fn().mockResolvedValue({
      nodes: [
        { id: "literature_review", type: "stage", label: "Literature Review",
          zone: "discovery", status: "complete", iteration_count: 1, skipped: false },
        { id: "plan_formulation", type: "stage", label: "Plan Formulation",
          zone: "discovery", status: "active", iteration_count: 2, skipped: false },
        { id: "peer_review", type: "stage", label: "Peer Review",
          zone: "synthesis", status: "skipped", iteration_count: 0, skipped: true },
      ],
      edges: [
        { from: "literature_review", to: "plan_formulation", kind: "sequential", reason: null },
      ],
      cursor: { node_id: "plan_formulation", agent: "postdoc", started_at: null },
      subgraphs: [],
    }),
    getSession: vi.fn().mockResolvedValue({
      session_id: "s1",
      preferences: { stage_controls: {} },
    }),
  },
}));

// ---------------------------------------------------------------------------
// Import component AFTER mocks are declared (vi.mock is hoisted, so this is safe).
// ---------------------------------------------------------------------------
import { GraphTopology } from "../../src/components/session/GraphTopology";
import type { GraphTopology as TopoType } from "../../src/types/domain";

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------
function makeQc() {
  return new QueryClient({ defaultOptions: { queries: { retry: false } } });
}

function renderIt() {
  return render(
    <QueryClientProvider client={makeQc()}>
      <GraphTopology sessionId="s1" />
    </QueryClientProvider>,
  );
}

function renderWithTopo(
  topology: TopoType,
  extra?: Partial<React.ComponentProps<typeof GraphTopology>>,
) {
  return render(
    <QueryClientProvider client={makeQc()}>
      <GraphTopology sessionId="s1" topology={topology} {...extra} />
    </QueryClientProvider>,
  );
}

// ---------------------------------------------------------------------------
// Shared beforeEach — jsdom shims
// ---------------------------------------------------------------------------
beforeEach(() => {
  globalThis.ResizeObserver = class {
    observe() {}
    unobserve() {}
    disconnect() {}
  } as unknown as typeof ResizeObserver;

  globalThis.HTMLElement.prototype.getBoundingClientRect = vi.fn(() => ({
    width: 400, height: 400, x: 0, y: 0, top: 0, left: 0,
    bottom: 400, right: 400, toJSON: () => ({}),
  }));
});

// ---------------------------------------------------------------------------
// Original suite (hook-driven, QueryClientProvider)
// ---------------------------------------------------------------------------
describe("GraphTopology", () => {
  it("renders stage node labels for all topology nodes", async () => {
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

  it("renders zone group labels for present zones", async () => {
    renderIt();
    expect(await screen.findByText("discovery")).toBeInTheDocument();
    expect(screen.getByText("synthesis")).toBeInTheDocument();
  });
});

// ---------------------------------------------------------------------------
// Backtrack edge rendering
// ---------------------------------------------------------------------------
describe("GraphTopology backtrack rendering", () => {
  it("renders forward edges solid and backtrack edges dashed with attempt-count labels", async () => {
    const topology: TopoType = {
      nodes: [
        { id: "lit", type: "stage", label: "Literature Review", zone: "discovery",
          status: "complete", iteration_count: 1, skipped: false },
        { id: "exp", type: "stage", label: "Experimentation", zone: "implementation",
          status: "active", iteration_count: 1, skipped: false },
      ],
      edges: [
        { from: "lit", to: "exp", kind: "sequential" },
        { from: "exp", to: "lit", kind: "backtrack", attempts: 2 },
      ],
      cursor: { node_id: "exp", internal_node: null, meeting_node: null, agent: null, started_at: null },
      subgraphs: [],
    };
    const { container, findByText } = renderWithTopo(topology);
    // Backtrack label visible at low density
    expect(await findByText("↩ 2")).toBeInTheDocument();
    // Both edges rendered via mock ReactFlow stub
    await waitFor(() => {
      const edges = container.querySelectorAll(".react-flow__edge");
      expect(edges.length).toBe(2);
    });
  });

  it("demotes backtrack labels to tooltips when count exceeds 8", async () => {
    const backtracks = Array.from({ length: 9 }, (_, i) => ({
      from: "exp",
      to: "lit",
      kind: "backtrack" as const,
      attempts: i + 1,
    }));
    const topology: TopoType = {
      nodes: [
        { id: "lit", type: "stage", label: "Lit", zone: "discovery",
          status: "complete", iteration_count: 1, skipped: false },
        { id: "exp", type: "stage", label: "Exp", zone: "implementation",
          status: "active", iteration_count: 1, skipped: false },
      ],
      edges: [{ from: "lit", to: "exp", kind: "sequential" }, ...backtracks],
      cursor: { node_id: "exp", internal_node: null, meeting_node: null, agent: null, started_at: null },
      subgraphs: [],
    };
    const { container, queryByText } = renderWithTopo(topology);
    // All 10 edges still rendered
    await waitFor(() => {
      const edges = container.querySelectorAll(".react-flow__edge");
      expect(edges.length).toBe(10);
    });
    // Label demoted — no visible "↩ 9" text
    expect(queryByText("↩ 9")).not.toBeInTheDocument();
  });
});

// ---------------------------------------------------------------------------
// Reverse-sweep animation on backward cursor jump
// ---------------------------------------------------------------------------
describe("GraphTopology cursor-reverse-sweep", () => {
  it("applies cursor-reverse-sweep class to intermediate stages on backward cursor jump", async () => {
    const baseNodes: TopoType["nodes"] = [
      { id: "lit", type: "stage", label: "Lit", zone: "discovery",
        status: "complete", iteration_count: 1, skipped: false },
      { id: "plan", type: "stage", label: "Plan", zone: "discovery",
        status: "complete", iteration_count: 1, skipped: false },
      { id: "exp", type: "stage", label: "Exp", zone: "implementation",
        status: "active", iteration_count: 1, skipped: false },
    ];
    const baseEdges: TopoType["edges"] = [
      { from: "lit", to: "plan", kind: "sequential" },
      { from: "plan", to: "exp", kind: "sequential" },
    ];

    const topology1: TopoType = {
      nodes: baseNodes,
      edges: baseEdges,
      cursor: { node_id: "exp", internal_node: null, meeting_node: null, agent: null, started_at: null },
      subgraphs: [],
    };

    const { container, rerender } = render(
      <QueryClientProvider client={makeQc()}>
        <GraphTopology sessionId="s1" topology={topology1} />
      </QueryClientProvider>,
    );

    // Wait for initial render with cursor at "exp"
    await waitFor(() => {
      expect(container.querySelector("[data-testid='stage-node-exp']")).not.toBeNull();
    });

    // Cursor jumps back to "lit" (backtrack: exp → lit)
    const topology2: TopoType = {
      ...topology1,
      cursor: { ...topology1.cursor, node_id: "lit" },
    };
    rerender(
      <QueryClientProvider client={makeQc()}>
        <GraphTopology sessionId="s1" topology={topology2} />
      </QueryClientProvider>,
    );

    // Intermediate nodes (plan, exp) should have the sweep class
    await waitFor(() => {
      const sweeping = container.querySelectorAll(".cursor-reverse-sweep");
      expect(sweeping.length).toBeGreaterThan(0);
      // "plan" and "exp" are between "lit" (new pos) and "exp" (old pos)
      const ids = Array.from(sweeping).map((el) => el.getAttribute("data-testid"));
      expect(ids).toContain("stage-node-plan");
      expect(ids).toContain("stage-node-exp");
    });

    // "lit" itself should NOT be sweeping (it's the new cursor position)
    const litNode = container.querySelector("[data-testid='stage-node-lit']");
    expect(litNode?.classList.contains("cursor-reverse-sweep")).toBe(false);
  });
});

// ---------------------------------------------------------------------------
// Active-stage click affordance
// ---------------------------------------------------------------------------
describe("GraphTopology active-stage click", () => {
  it("clicking the active stage fires onStageClick", async () => {
    const onStageClick = vi.fn();
    const topology: TopoType = {
      nodes: [
        { id: "exp", type: "stage", label: "Experimentation", zone: "implementation",
          status: "active", iteration_count: 1, skipped: false },
      ],
      edges: [],
      cursor: { node_id: "exp", internal_node: "work", meeting_node: null, agent: null, started_at: null },
      subgraphs: [],
    };
    const { findByTestId } = renderWithTopo(topology, { onStageClick });
    const node = await findByTestId("stage-node-exp");
    fireEvent.click(node);
    expect(onStageClick).toHaveBeenCalledWith("exp");
  });

  it("non-active stages are not clickable (onStageClick not called)", async () => {
    const onStageClick = vi.fn();
    const topology: TopoType = {
      nodes: [
        { id: "lit", type: "stage", label: "Literature Review", zone: "discovery",
          status: "complete", iteration_count: 1, skipped: false },
        { id: "exp", type: "stage", label: "Experimentation", zone: "implementation",
          status: "active", iteration_count: 1, skipped: false },
      ],
      edges: [{ from: "lit", to: "exp", kind: "sequential" }],
      cursor: { node_id: "exp", internal_node: "work", meeting_node: null, agent: null, started_at: null },
      subgraphs: [],
    };
    const { findByTestId } = renderWithTopo(topology, { onStageClick });
    const litNode = await findByTestId("stage-node-lit");
    fireEvent.click(litNode);
    expect(onStageClick).not.toHaveBeenCalled();
  });
});
