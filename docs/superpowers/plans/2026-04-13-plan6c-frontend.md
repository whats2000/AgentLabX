# Plan 6C: Frontend Observability UI Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Rebuild the session detail frontend around the Plan 6B observability contracts. Stacked layout with always-visible graph canvas, chat-style conversation view, agent monitor right sider, experiments tab with prior-attempts ribbon, PI decision log. Drop the hardcoded `PipelineGraph`, duplicate compact panels, and stage-level event-list `AgentActivityFeed`.

**Architecture:** Top band is an always-on `GraphTopology` canvas (@xyflow/react + elkjs auto-layout) showing rich `StageNode` cards with status, iteration, current agent, per-stage control dropdown, cost. Below that: left sider (Pause/Resume/Cancel only), center tabs (`Conversations` default, `Artifacts`, `Experiments`, `Cost`), right sider (`AgentMonitor` with per-agent Scope/Context/Memory/History subcards, then `HypothesisTracker`, `PIDecisionLog`, compact `CostTracker`). Chat view groups `agent_turns` by stage then by `turn_id`, rendering LLM request/response and inline tool calls; `mode` prop reserves space for a future pixel-art `lab_scene` renderer. WebSocket events invalidate matching TanStack Query keys for live updates.

**Tech Stack:** React 19, TypeScript 5.5, Vite 6, @xyflow/react 12, elkjs, TanStack Query 5, Ant Design 5, Zustand 5, Vitest + @testing-library/react, pnpm.

**Companion spec:** `docs/superpowers/specs/2026-04-13-plan6-observability-design.md` §4.
**Depends on:** Plan 6B complete (all 8 observability endpoints returning real data; WS emitting turn-grained events).
**Unblocks:** none — Plan 6C is the final phase of the observability rollout.

---

## File Structure Map

**Created:**
```
web/src/components/session/GraphTopology.tsx
web/src/components/session/StageNode.tsx
web/src/components/session/ChatView.tsx
web/src/components/session/StageGroup.tsx
web/src/components/session/AgentTurn.tsx
web/src/components/session/ToolCallInline.tsx
web/src/components/session/AgentMonitor.tsx
web/src/components/session/AgentScopeCard.tsx
web/src/components/session/AgentContextPreview.tsx
web/src/components/session/AgentMemoryCard.tsx
web/src/components/session/AgentHistoryCard.tsx
web/src/components/session/PIDecisionLog.tsx
web/src/components/session/ExperimentsTab.tsx
web/src/components/session/ExperimentDetail.tsx
web/src/components/session/ExperimentDiffView.tsx
web/src/hooks/useGraph.ts
web/src/hooks/useAgents.ts
web/src/hooks/useAgentContext.ts
web/src/hooks/useAgentHistory.ts
web/src/hooks/useAgentMemory.ts
web/src/hooks/usePIHistory.ts
web/src/hooks/useCrossStageRequests.ts
web/src/hooks/useExperiments.ts
web/tests/components/GraphTopology.test.tsx
web/tests/components/ChatView.test.tsx
web/tests/components/AgentMonitor.test.tsx
web/tests/components/ExperimentsTab.test.tsx
web/tests/hooks/useAgentHistory.test.tsx
```

**Modified:**
```
web/src/pages/SessionDetailPage.tsx          # stacked layout
web/src/components/session/ControlBar.tsx    # reduce to global actions
web/src/hooks/useWebSocket.ts                # invalidation map for new events
web/src/api/client.ts                        # 8 new API methods
web/src/types/api.ts                         # regenerated from OpenAPI
web/src/types/domain.ts                      # GraphTopology, AgentTurnRow, etc.
web/src/stores/uiStore.ts                    # detailTab union update
web/package.json                             # +elkjs dependency
```

**Deleted:**
```
web/src/components/session/PipelineGraph.tsx
web/src/components/session/PipelineTracker.tsx
web/src/components/session/AgentActivityFeed.tsx
web/tests/components/PipelineGraph.test.tsx
web/tests/components/PipelineTracker.test.tsx
web/tests/components/AgentActivityFeed.test.tsx
```

---

### Task C1: Regenerate OpenAPI types and add API client methods

**Files:**
- Modify: `web/src/types/api.ts` (generated)
- Modify: `web/src/api/client.ts`
- Modify: `web/src/types/domain.ts`

- [ ] **Step 1: Regenerate types.**

```bash
cd d:/GitHub/AgentLabX
uv run agentlabx serve --mock-llm &
sleep 3
cd web && pnpm exec openapi-typescript http://localhost:8000/openapi.json -o src/types/api.ts
```

- [ ] **Step 2: Add API methods in `web/src/api/client.ts`:**

```typescript
export const api = {
  // ...existing...
  getGraph: (sessionId: string) =>
    request<components["schemas"]["GraphTopology"]>(`GET /api/sessions/${sessionId}/graph`),
  listAgents: (sessionId: string) =>
    request<Array<{name: string; role: string; turn_count: number; last_active_stage: string | null}>>(
      `GET /api/sessions/${sessionId}/agents`),
  getAgentContext: (sessionId: string, agent: string) =>
    request(`GET /api/sessions/${sessionId}/agents/${agent}/context`),
  getAgentHistory: (sessionId: string, agent: string, params?: {limit?: number; after_ts?: string}) =>
    request(`GET /api/sessions/${sessionId}/agents/${agent}/history`, {params}),
  getAgentMemory: (sessionId: string, agent: string) =>
    request(`GET /api/sessions/${sessionId}/agents/${agent}/memory`),
  getPIHistory: (sessionId: string) =>
    request<any[]>(`GET /api/sessions/${sessionId}/pi/history`),
  getRequests: (sessionId: string) =>
    request<{pending: any[]; completed: any[]}>(`GET /api/sessions/${sessionId}/requests`),
  getExperiments: (sessionId: string) =>
    request<{runs: any[]; log: any[]}>(`GET /api/sessions/${sessionId}/experiments`),
};
```

- [ ] **Step 3: Domain types.** Add to `web/src/types/domain.ts`:

```typescript
export interface GraphNode {
  id: string;
  type: "stage" | "transition" | "subgraph";
  label: string;
  zone: "discovery" | "implementation" | "synthesis" | null;
  status: "pending" | "active" | "complete" | "failed" | "skipped" | "meta";
  iteration_count: number;
  skipped: boolean;
}
export interface GraphEdge {
  from: string; to: string;
  kind: "sequential" | "backtrack" | "conditional";
  reason?: string | null;
}
export interface GraphTopology {
  nodes: GraphNode[];
  edges: GraphEdge[];
  cursor: {node_id: string; agent: string | null; started_at: string | null} | null;
  subgraphs: Array<{id: string; nodes: GraphNode[]; edges: GraphEdge[]}>;
}

export interface AgentTurnRow {
  turn_id: string;
  parent_turn_id: string | null;
  agent: string;
  stage: string;
  kind: "llm_request" | "llm_response" | "tool_call" | "tool_result" | "dialogue";
  payload: Record<string, unknown>;
  tokens_in: number | null;
  tokens_out: number | null;
  cost_usd: number | null;
  is_mock: boolean;
  ts: string;
}

export interface AgentMemoryRecord {
  working_memory: Record<string, unknown>;
  notes: string[];
  last_active_stage: string;
  turn_count: number;
}

export interface PIDecisionRecord {
  decision_id: string;
  action: string;
  confidence: number;
  next_stage: string | null;
  reasoning: string;
  used_fallback: boolean;
  ts: string;
}
```

- [ ] **Step 4: Commit.**

```bash
cd d:/GitHub/AgentLabX
git add web/src/types/ web/src/api/client.ts
git commit -m "feat(web): regenerate OpenAPI types; add observability API methods + domain types"
```

### Task C2: Observability hooks

**Files:**
- Create: `web/src/hooks/useGraph.ts`, `useAgents.ts`, `useAgentContext.ts`, `useAgentHistory.ts`, `useAgentMemory.ts`, `usePIHistory.ts`, `useCrossStageRequests.ts`, `useExperiments.ts`
- Test: `web/tests/hooks/useAgentHistory.test.tsx`

- [ ] **Step 1: Write each hook.** Pattern is identical — minimal TanStack Query wrapper:

```typescript
// web/src/hooks/useGraph.ts
import { useQuery } from "@tanstack/react-query";
import { api } from "../api/client";
import type { GraphTopology } from "../types/domain";

export function useGraph(sessionId: string) {
  return useQuery<GraphTopology>({
    queryKey: ["graph", sessionId],
    queryFn: () => api.getGraph(sessionId),
    enabled: !!sessionId,
  });
}
```

Replicate for the other seven hooks, using keys `["agents", sessionId]`, `["agent-context", sessionId, name]`, `["agent-history", sessionId, name]`, `["agent-memory", sessionId, name]`, `["pi-history", sessionId]`, `["requests", sessionId]`, `["experiments", sessionId]`.

- [ ] **Step 2: Test one representative hook.**

```tsx
// web/tests/hooks/useAgentHistory.test.tsx
import { renderHook, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { vi } from "vitest";
import { useAgentHistory } from "../../src/hooks/useAgentHistory";

vi.mock("../../src/api/client", () => ({
  api: { getAgentHistory: vi.fn().mockResolvedValue({turns: [{turn_id: "t1"}], next_cursor: null}) },
}));

it("returns turns array", async () => {
  const qc = new QueryClient({defaultOptions: {queries: {retry: false}}});
  const wrap = ({children}: any) => <QueryClientProvider client={qc}>{children}</QueryClientProvider>;
  const {result} = renderHook(() => useAgentHistory("s1", "phd_student"), {wrapper: wrap});
  await waitFor(() => expect(result.current.data).toBeDefined());
  expect(result.current.data.turns[0].turn_id).toBe("t1");
});
```

- [ ] **Step 3: Run.**

```bash
cd web && pnpm test
```

- [ ] **Step 4: Commit.**

```bash
git add web/src/hooks/ web/tests/hooks/
git commit -m "feat(web): add 8 observability hooks (graph, agents, agent context/history/memory, pi history, requests, experiments)"
```

### Task C3: GraphTopology + StageNode component

**Files:**
- Create: `web/src/components/session/GraphTopology.tsx`
- Create: `web/src/components/session/StageNode.tsx`
- Install: `pnpm add elkjs`
- Test: `web/tests/components/GraphTopology.test.tsx`

- [ ] **Step 1: Install elkjs.**

```bash
cd web && pnpm add elkjs
```

- [ ] **Step 2: Write failing test.**

```tsx
// web/tests/components/GraphTopology.test.tsx
import { render, screen } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { vi } from "vitest";
import { GraphTopology } from "../../src/components/session/GraphTopology";

vi.mock("../../src/api/client", () => ({
  api: {
    getGraph: vi.fn().mockResolvedValue({
      nodes: [
        {id: "literature_review", type: "stage", label: "Literature Review", zone: "discovery",
         status: "complete", iteration_count: 1, skipped: false},
        {id: "plan_formulation", type: "stage", label: "Plan Formulation", zone: "discovery",
         status: "active", iteration_count: 2, skipped: false},
        {id: "peer_review", type: "stage", label: "Peer Review", zone: "synthesis",
         status: "skipped", iteration_count: 0, skipped: true},
      ],
      edges: [
        {from: "literature_review", to: "plan_formulation", kind: "sequential"},
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
    </QueryClientProvider>,
  );
}

it("renders one node per topology node", async () => {
  renderIt();
  expect(await screen.findByText("Plan Formulation")).toBeInTheDocument();
  expect(screen.getByText("Literature Review")).toBeInTheDocument();
  expect(screen.getByText("Peer Review")).toBeInTheDocument();
});

it("marks skipped nodes with skipped styling", async () => {
  renderIt();
  const node = await screen.findByTestId("stage-node-peer_review");
  expect(node).toHaveAttribute("data-status", "skipped");
});

it("shows iteration count on active node", async () => {
  renderIt();
  expect(await screen.findByText(/iter 2/)).toBeInTheDocument();
});
```

- [ ] **Step 3: Run; verify fail.**

- [ ] **Step 4: Implement `StageNode.tsx`:**

```tsx
// web/src/components/session/StageNode.tsx
import { Tag } from "antd";
import type { GraphNode } from "../../types/domain";

const STATUS_COLOR: Record<GraphNode["status"], string> = {
  pending: "default", active: "processing", complete: "success",
  failed: "error", skipped: "default", meta: "default",
};

interface Props {
  node: GraphNode;
  onOpen?: (id: string) => void;
}

export function StageNode({ node, onOpen }: Props) {
  const opacity = node.skipped ? 0.4 : 1.0;
  return (
    <div
      data-testid={`stage-node-${node.id}`}
      data-status={node.status}
      onClick={() => onOpen?.(node.id)}
      style={{
        padding: 10, borderRadius: 8, background: "#fff",
        border: "1px solid #e0e0e0", minWidth: 180, opacity, cursor: "pointer",
      }}
    >
      <div style={{ fontSize: 12, fontWeight: 600 }}>{node.label}</div>
      <div style={{ fontSize: 11, color: "#6b7280", marginTop: 4 }}>
        <Tag color={STATUS_COLOR[node.status]} bordered={false}>{node.status}</Tag>
        {node.iteration_count > 0 && <span>· iter {node.iteration_count}</span>}
      </div>
    </div>
  );
}
```

- [ ] **Step 5: Implement `GraphTopology.tsx` with elk + xyflow:**

```tsx
// web/src/components/session/GraphTopology.tsx
import { useMemo } from "react";
import { ReactFlow, Background, Controls, useNodesState, useEdgesState } from "@xyflow/react";
import "@xyflow/react/dist/style.css";
import ELK from "elkjs/lib/elk.bundled.js";
import { Skeleton, Empty } from "antd";
import { useGraph } from "../../hooks/useGraph";
import { StageNode } from "./StageNode";
import type { GraphTopology as Topo } from "../../types/domain";

const elk = new ELK();

const nodeTypes = { stage: (p: any) => <StageNode node={p.data.node} /> };

async function layout(topo: Topo) {
  const res = await elk.layout({
    id: "root",
    layoutOptions: {"elk.algorithm": "layered", "elk.direction": "RIGHT",
                    "elk.spacing.nodeNode": "40", "elk.layered.spacing.nodeNodeBetweenLayers": "80"},
    children: topo.nodes.map(n => ({id: n.id, width: 200, height: 70})),
    edges: topo.edges.map((e, i) => ({id: `e${i}`, sources: [e.from], targets: [e.to]})),
  });
  return res;
}

interface Props { sessionId: string; }

export function GraphTopology({ sessionId }: Props) {
  const { data: topo, isLoading } = useGraph(sessionId);
  const [nodes, setNodes, onNodesChange] = useNodesState([]);
  const [edges, setEdges, onEdgesChange] = useEdgesState([]);

  useMemo(() => {
    if (!topo) return;
    layout(topo).then(laid => {
      setNodes(topo.nodes.map((n, i) => {
        const pos = laid.children?.find(c => c.id === n.id);
        return {
          id: n.id, type: "stage",
          position: { x: pos?.x ?? i * 220, y: pos?.y ?? 0 },
          data: { node: n },
        };
      }));
      setEdges(topo.edges.map((e, i) => ({
        id: `e${i}`, source: e.from, target: e.to,
        animated: e.kind === "backtrack",
        style: e.kind === "backtrack" ? {stroke: "#faad14"} : undefined,
      })));
    });
  }, [topo, setNodes, setEdges]);

  if (isLoading) return <Skeleton active />;
  if (!topo) return <Empty description="No topology" />;
  return (
    <div style={{ height: 320, border: "1px solid #efefef", borderRadius: 8 }}>
      <ReactFlow nodes={nodes} edges={edges} nodeTypes={nodeTypes}
                 onNodesChange={onNodesChange} onEdgesChange={onEdgesChange}
                 fitView>
        <Background /><Controls />
      </ReactFlow>
    </div>
  );
}
```

- [ ] **Step 6: Run tests.**

```bash
cd web && pnpm test GraphTopology
```

- [ ] **Step 7: Commit.**

```bash
git add web/src/components/session/GraphTopology.tsx web/src/components/session/StageNode.tsx web/tests/components/GraphTopology.test.tsx web/package.json web/pnpm-lock.yaml
git commit -m "feat(web): GraphTopology with elkjs auto-layout + rich StageNode cards"
```

### Task C4: ChatView + StageGroup + AgentTurn + ToolCallInline

**Files:**
- Create: `web/src/components/session/ChatView.tsx`, `StageGroup.tsx`, `AgentTurn.tsx`, `ToolCallInline.tsx`
- Test: `web/tests/components/ChatView.test.tsx`

- [ ] **Step 1: Write failing test.**

```tsx
// web/tests/components/ChatView.test.tsx
import { render, screen } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { vi } from "vitest";
import { ChatView } from "../../src/components/session/ChatView";

vi.mock("../../src/api/client", () => ({
  api: {
    listAgents: vi.fn().mockResolvedValue([
      {name: "postdoc", role: "postdoc", turn_count: 2, last_active_stage: "plan_formulation"},
    ]),
    getAgentHistory: vi.fn().mockImplementation((_sid, agent) => Promise.resolve({
      turns: agent === "postdoc" ? [
        {turn_id: "T1", agent: "postdoc", stage: "plan_formulation",
         kind: "llm_request", payload: {prompt: "go", system_prompt: "sp"}, is_mock: true,
         tokens_in: null, tokens_out: null, cost_usd: null, ts: "2026-04-13T00:00:00"},
        {turn_id: "T1", agent: "postdoc", stage: "plan_formulation",
         kind: "llm_response", payload: {content: "Proposed plan"}, is_mock: true,
         tokens_in: 5, tokens_out: 8, cost_usd: 0.01, ts: "2026-04-13T00:00:01"},
      ] : [],
      next_cursor: null,
    })),
  },
}));

it("groups by stage; shows asst response inline under request", async () => {
  const qc = new QueryClient({defaultOptions: {queries: {retry: false}}});
  render(<QueryClientProvider client={qc}><ChatView sessionId="s1" /></QueryClientProvider>);
  expect(await screen.findByText("Plan Formulation")).toBeInTheDocument();
  expect(screen.getByText(/Proposed plan/)).toBeInTheDocument();
  expect(screen.getByText(/mock/i)).toBeInTheDocument();
});
```

- [ ] **Step 2: Run; verify fail.**

- [ ] **Step 3: Implement `ChatView.tsx`:**

```tsx
// web/src/components/session/ChatView.tsx
import { Skeleton, Empty } from "antd";
import { useAgents } from "../../hooks/useAgents";
import { useAgentHistory } from "../../hooks/useAgentHistory";
import { StageGroup } from "./StageGroup";
import type { AgentTurnRow } from "../../types/domain";

interface Props { sessionId: string; mode?: "clean" | "lab_scene"; }

export function ChatView({ sessionId, mode = "clean" }: Props) {
  const { data: agents, isLoading } = useAgents(sessionId);
  if (isLoading) return <Skeleton active />;
  if (!agents || agents.length === 0) return <Empty description="No agent turns yet" />;
  return (
    <div>
      <GroupedByStage sessionId={sessionId} agentNames={agents.map(a => a.name)} mode={mode} />
    </div>
  );
}

function GroupedByStage({ sessionId, agentNames, mode }:
  {sessionId: string; agentNames: string[]; mode: "clean" | "lab_scene"}) {
  // Naive aggregation: fetch each agent's history, then group by stage client-side.
  const histories = agentNames.map(n => ({
    name: n, query: useAgentHistory(sessionId, n),
  }));
  const all: AgentTurnRow[] = histories.flatMap(h => h.query.data?.turns ?? []);
  const byStage = groupByStage(all);
  return (
    <div>
      {Object.entries(byStage).map(([stage, turns]) => (
        <StageGroup key={stage} stage={stage} turns={turns} mode={mode} />
      ))}
    </div>
  );
}

function groupByStage(turns: AgentTurnRow[]): Record<string, AgentTurnRow[]> {
  return turns.reduce((acc, t) => {
    (acc[t.stage] ??= []).push(t); return acc;
  }, {} as Record<string, AgentTurnRow[]>);
}
```

- [ ] **Step 4: Implement `StageGroup.tsx`:**

```tsx
// web/src/components/session/StageGroup.tsx
import { Card, Typography } from "antd";
import { AgentTurn } from "./AgentTurn";
import type { AgentTurnRow } from "../../types/domain";

const { Text } = Typography;

function prettyStage(s: string) {
  return s.split("_").map(w => w[0].toUpperCase() + w.slice(1)).join(" ");
}

export function StageGroup({ stage, turns, mode }:
  {stage: string; turns: AgentTurnRow[]; mode: "clean" | "lab_scene"}) {
  const byTurn: Record<string, AgentTurnRow[]> = {};
  for (const t of turns) (byTurn[t.turn_id] ??= []).push(t);

  return (
    <Card size="small" style={{ marginBottom: 12 }}>
      <Text strong>{prettyStage(stage)}</Text>
      <Text type="secondary" style={{ marginLeft: 8, fontSize: 11 }}>
        {Object.keys(byTurn).length} turns
      </Text>
      <div style={{ marginTop: 8 }}>
        {Object.entries(byTurn).map(([turnId, rows]) => (
          <AgentTurn key={turnId} turnId={turnId} rows={rows} mode={mode} />
        ))}
      </div>
    </Card>
  );
}
```

- [ ] **Step 5: Implement `AgentTurn.tsx`:**

```tsx
// web/src/components/session/AgentTurn.tsx
import { Collapse, Tag, Typography } from "antd";
import { ToolCallInline } from "./ToolCallInline";
import type { AgentTurnRow } from "../../types/domain";

const { Text, Paragraph } = Typography;

export function AgentTurn({ turnId, rows, mode }:
  {turnId: string; rows: AgentTurnRow[]; mode: "clean" | "lab_scene"}) {
  const first = rows[0];
  const req = rows.find(r => r.kind === "llm_request");
  const resp = rows.find(r => r.kind === "llm_response");
  const toolPairs = collectToolPairs(rows);

  return (
    <div style={{ padding: "8px 0", borderBottom: "1px solid #f0f0f0" }}>
      <Text strong>{first.agent}</Text>
      {first.is_mock && <Tag style={{ marginLeft: 8 }} color="cyan">mock</Tag>}
      {resp?.cost_usd != null && (
        <Text type="secondary" style={{ marginLeft: 8, fontSize: 11 }}>
          ${resp.cost_usd.toFixed(4)}
        </Text>
      )}
      {req && (
        <Collapse ghost items={[{
          key: "sp", label: "system prompt",
          children: <Paragraph style={{fontSize:12, margin:0}}>{String(req.payload.system_prompt ?? "")}</Paragraph>,
        }]} />
      )}
      {req && (
        <Paragraph style={{ fontSize: 13, background: "#fafafa", padding: 8, borderRadius: 4, margin: "4px 0" }}>
          <Text type="secondary">user:</Text> {String(req.payload.prompt ?? "")}
        </Paragraph>
      )}
      {resp && (
        <Paragraph style={{ fontSize: 13, margin: "4px 0" }}>
          <Text type="secondary">asst:</Text> {String(resp.payload.content ?? "")}
        </Paragraph>
      )}
      {toolPairs.map(([call, result]) => (
        <ToolCallInline key={call.turn_id + String(call.payload.tool)} call={call} result={result} />
      ))}
    </div>
  );
}

function collectToolPairs(rows: AgentTurnRow[]) {
  const calls = rows.filter(r => r.kind === "tool_call");
  const results = rows.filter(r => r.kind === "tool_result");
  return calls.map((c, i) => [c, results[i]] as const);
}
```

- [ ] **Step 6: Implement `ToolCallInline.tsx`:**

```tsx
// web/src/components/session/ToolCallInline.tsx
import { Collapse, Tag, Typography } from "antd";
import type { AgentTurnRow } from "../../types/domain";

const { Text } = Typography;

export function ToolCallInline({ call, result }:
  {call: AgentTurnRow; result: AgentTurnRow | undefined}) {
  const success = result ? (result.payload.success as boolean) : false;
  return (
    <Collapse ghost items={[{
      key: "t",
      label: (
        <span>
          <Tag color={success ? "green" : result ? "red" : "default"}>tool</Tag>
          <Text strong style={{ fontSize: 12 }}>{String(call.payload.tool)}</Text>
        </span>
      ),
      children: (
        <pre style={{ fontSize: 11, background: "#fafafa", padding: 8, borderRadius: 4 }}>
{JSON.stringify({args: call.payload.args, result: result?.payload?.result_preview}, null, 2)}
        </pre>
      ),
    }]} />
  );
}
```

- [ ] **Step 7: Run tests.**

```bash
cd web && pnpm test ChatView
```

- [ ] **Step 8: Commit.**

```bash
git add web/src/components/session/ChatView.tsx web/src/components/session/StageGroup.tsx web/src/components/session/AgentTurn.tsx web/src/components/session/ToolCallInline.tsx web/tests/components/ChatView.test.tsx
git commit -m "feat(web): ChatView with stage-grouped turns, inline tool calls, [mock] tags"
```

### Task C5: AgentMonitor + sub-cards

**Files:**
- Create: `web/src/components/session/AgentMonitor.tsx`, `AgentScopeCard.tsx`, `AgentContextPreview.tsx`, `AgentMemoryCard.tsx`, `AgentHistoryCard.tsx`
- Test: `web/tests/components/AgentMonitor.test.tsx`

- [ ] **Step 1: Write failing test.**

```tsx
// web/tests/components/AgentMonitor.test.tsx
import { render, screen } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { vi } from "vitest";
import { AgentMonitor } from "../../src/components/session/AgentMonitor";

vi.mock("../../src/api/client", () => ({
  api: {
    listAgents: vi.fn().mockResolvedValue([
      {name: "postdoc", role: "postdoc", turn_count: 4, last_active_stage: "plan_formulation"},
      {name: "phd_student", role: "phd", turn_count: 2, last_active_stage: "literature_review"},
    ]),
    getAgentContext: vi.fn().mockResolvedValue({keys: ["plan","hypotheses"], preview: {}, scope: {read:["plan"],summarize:{},write:["plan"]}}),
    getAgentMemory: vi.fn().mockResolvedValue({working_memory:{},notes:[],last_active_stage:"",turn_count:0}),
    getAgentHistory: vi.fn().mockResolvedValue({turns:[], next_cursor:null}),
  },
}));

it("renders a tab per agent", async () => {
  const qc = new QueryClient({defaultOptions: {queries: {retry: false}}});
  render(<QueryClientProvider client={qc}><AgentMonitor sessionId="s1" /></QueryClientProvider>);
  expect(await screen.findByText("postdoc")).toBeInTheDocument();
  expect(screen.getByText("phd_student")).toBeInTheDocument();
});
```

- [ ] **Step 2: Run; verify fail.**

- [ ] **Step 3: Implement `AgentMonitor.tsx`:**

```tsx
// web/src/components/session/AgentMonitor.tsx
import { useState } from "react";
import { Tabs, Skeleton, Empty, Collapse } from "antd";
import { useAgents } from "../../hooks/useAgents";
import { AgentScopeCard } from "./AgentScopeCard";
import { AgentContextPreview } from "./AgentContextPreview";
import { AgentMemoryCard } from "./AgentMemoryCard";
import { AgentHistoryCard } from "./AgentHistoryCard";

interface Props { sessionId: string; }

export function AgentMonitor({ sessionId }: Props) {
  const { data: agents, isLoading } = useAgents(sessionId);
  const [active, setActive] = useState<string | undefined>();
  if (isLoading) return <Skeleton active />;
  if (!agents || agents.length === 0) return <Empty description="No agents yet" />;

  const key = active ?? agents[0].name;
  return (
    <div style={{ padding: "8px 12px" }}>
      <Tabs
        size="small"
        activeKey={key}
        onChange={setActive}
        items={agents.map(a => ({
          key: a.name, label: a.name,
          children: (
            <Collapse defaultActiveKey={["scope","context","memory","history"]} ghost
              items={[
                { key: "scope", label: "Scope", children: <AgentScopeCard sessionId={sessionId} agent={a.name} /> },
                { key: "context", label: "Context", children: <AgentContextPreview sessionId={sessionId} agent={a.name} /> },
                { key: "memory", label: "Memory", children: <AgentMemoryCard sessionId={sessionId} agent={a.name} /> },
                { key: "history", label: `History (${a.turn_count} turns)`, children: <AgentHistoryCard sessionId={sessionId} agent={a.name} /> },
              ]} />
          ),
        }))}
      />
    </div>
  );
}
```

- [ ] **Step 4: Implement sub-cards.**

```tsx
// web/src/components/session/AgentScopeCard.tsx
import { Tag, Typography } from "antd";
import { useAgentContext } from "../../hooks/useAgentContext";

const { Text } = Typography;

export function AgentScopeCard({ sessionId, agent }: {sessionId: string; agent: string}) {
  const { data } = useAgentContext(sessionId, agent);
  if (!data) return null;
  const scope = data.scope;
  return (
    <div style={{ fontSize: 12 }}>
      <div><Text type="secondary">read:</Text> {scope.read.map((k: string) => <Tag key={k} bordered={false}>{k}</Tag>)}</div>
      <div><Text type="secondary">summarize:</Text> {Object.keys(scope.summarize).map(k => <Tag key={k} bordered={false}>{k}→{scope.summarize[k]}</Tag>)}</div>
      <div><Text type="secondary">write:</Text> {scope.write.map((k: string) => <Tag key={k} color="blue" bordered={false}>{k}</Tag>)}</div>
    </div>
  );
}
```

```tsx
// web/src/components/session/AgentContextPreview.tsx
import { useAgentContext } from "../../hooks/useAgentContext";

export function AgentContextPreview({ sessionId, agent }: {sessionId: string; agent: string}) {
  const { data } = useAgentContext(sessionId, agent);
  if (!data) return null;
  return (
    <pre style={{ fontSize: 11, maxHeight: 200, overflow: "auto", background: "#fafafa", padding: 8, borderRadius: 4 }}>
{JSON.stringify(data.preview, null, 2)}
    </pre>
  );
}
```

```tsx
// web/src/components/session/AgentMemoryCard.tsx
import { Empty, Typography } from "antd";
import { useAgentMemory } from "../../hooks/useAgentMemory";

const { Text } = Typography;

export function AgentMemoryCard({ sessionId, agent }: {sessionId: string; agent: string}) {
  const { data } = useAgentMemory(sessionId, agent);
  if (!data) return null;
  if (data.notes.length === 0 && Object.keys(data.working_memory).length === 0)
    return <Empty description="Empty scratchpad" image={Empty.PRESENTED_IMAGE_SIMPLE} />;
  return (
    <div style={{ fontSize: 12 }}>
      {data.notes.length > 0 && (
        <div>
          <Text type="secondary">notes:</Text>
          <ul style={{ margin: "4px 0 0 0", paddingLeft: 16 }}>
            {data.notes.map((n: string, i: number) => <li key={i}>{n}</li>)}
          </ul>
        </div>
      )}
      {Object.keys(data.working_memory).length > 0 && (
        <pre style={{ fontSize: 11, marginTop: 8 }}>{JSON.stringify(data.working_memory, null, 2)}</pre>
      )}
    </div>
  );
}
```

```tsx
// web/src/components/session/AgentHistoryCard.tsx
import { List, Tag, Typography } from "antd";
import { useAgentHistory } from "../../hooks/useAgentHistory";

const { Text } = Typography;

export function AgentHistoryCard({ sessionId, agent }: {sessionId: string; agent: string}) {
  const { data } = useAgentHistory(sessionId, agent, { limit: 50 });
  const turns = data?.turns ?? [];
  if (turns.length === 0) return <Text type="secondary">no turns yet</Text>;
  return (
    <List size="small"
      dataSource={turns}
      renderItem={t => (
        <List.Item style={{ fontSize: 11 }}>
          <Tag>{t.kind}</Tag>
          <span>{t.stage}</span>
          <span style={{ marginLeft: 8, color: "#999" }}>{t.ts.slice(11,19)}</span>
        </List.Item>
      )} />
  );
}
```

- [ ] **Step 5: Run tests.**

- [ ] **Step 6: Commit.**

```bash
git add web/src/components/session/AgentMonitor.tsx web/src/components/session/AgentScopeCard.tsx web/src/components/session/AgentContextPreview.tsx web/src/components/session/AgentMemoryCard.tsx web/src/components/session/AgentHistoryCard.tsx web/tests/components/AgentMonitor.test.tsx
git commit -m "feat(web): AgentMonitor with Scope/Context/Memory/History cards per agent"
```

### Task C6: PIDecisionLog

**Files:**
- Create: `web/src/components/session/PIDecisionLog.tsx`

- [ ] **Step 1: Write the component:**

```tsx
// web/src/components/session/PIDecisionLog.tsx
import { List, Tag, Typography, Empty } from "antd";
import { usePIHistory } from "../../hooks/usePIHistory";
import type { PIDecisionRecord } from "../../types/domain";

const { Text } = Typography;

export function PIDecisionLog({ sessionId, limit = 3 }: {sessionId: string; limit?: number}) {
  const { data } = usePIHistory(sessionId);
  const recent = (data as PIDecisionRecord[] | undefined)?.slice(-limit).reverse() ?? [];
  if (recent.length === 0)
    return <Empty description="No PI decisions yet" image={Empty.PRESENTED_IMAGE_SIMPLE} />;
  return (
    <List size="small" dataSource={recent} renderItem={d => (
      <List.Item>
        <div style={{ width: "100%" }}>
          <div>
            <Tag color={d.used_fallback ? "warning" : "success"}>{d.action}</Tag>
            <Text type="secondary" style={{ fontSize: 11 }}>
              {d.confidence.toFixed(2)}{d.next_stage ? ` → ${d.next_stage}` : ""}
            </Text>
          </div>
          <Text type="secondary" style={{ fontSize: 11 }}>{d.reasoning}</Text>
        </div>
      </List.Item>
    )} />
  );
}
```

- [ ] **Step 2: Commit.**

```bash
git add web/src/components/session/PIDecisionLog.tsx
git commit -m "feat(web): PIDecisionLog shows recent PI decisions with confidence and fallback tags"
```

### Task C7: ExperimentsTab + ExperimentDetail + ExperimentDiffView

**Files:**
- Create: `web/src/components/session/ExperimentsTab.tsx`, `ExperimentDetail.tsx`, `ExperimentDiffView.tsx`
- Test: `web/tests/components/ExperimentsTab.test.tsx`

- [ ] **Step 1: Write failing test.**

```tsx
// web/tests/components/ExperimentsTab.test.tsx
import { render, screen } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { vi } from "vitest";
import { ExperimentsTab } from "../../src/components/session/ExperimentsTab";

vi.mock("../../src/api/client", () => ({
  api: {
    getExperiments: vi.fn().mockResolvedValue({
      runs: [{index: 0, tag: "baseline", metrics: {acc: 0.62}, description: "base cot",
              reproducibility: {random_seed: 42, run_command: "python base.py"}}],
      log: [{attempt_id:"a1",outcome:"failure",failure_reason:"timeout",learnings:[]}],
    }),
  },
}));

it("lists each run and shows prior failures ribbon", async () => {
  const qc = new QueryClient({defaultOptions: {queries: {retry: false}}});
  render(<QueryClientProvider client={qc}><ExperimentsTab sessionId="s1" /></QueryClientProvider>);
  expect(await screen.findByText(/baseline/i)).toBeInTheDocument();
  expect(screen.getByText(/0\.62/)).toBeInTheDocument();
  expect(screen.getByText(/prior attempts/i)).toBeInTheDocument();
  expect(screen.getByText(/timeout/)).toBeInTheDocument();
});
```

- [ ] **Step 2: Run; verify fail.**

- [ ] **Step 3: Implement `ExperimentsTab.tsx`:**

```tsx
// web/src/components/session/ExperimentsTab.tsx
import { Alert, Empty, Skeleton, Typography, Tag } from "antd";
import { useExperiments } from "../../hooks/useExperiments";
import { ExperimentDetail } from "./ExperimentDetail";

const { Title, Text } = Typography;

export function ExperimentsTab({ sessionId }: {sessionId: string}) {
  const { data, isLoading } = useExperiments(sessionId);
  if (isLoading) return <Skeleton active />;
  if (!data || (data.runs.length === 0 && data.log.length === 0))
    return <Empty description="No experiments yet" />;

  const failures = data.log.filter((a: any) => a.outcome === "failure");
  return (
    <div>
      {failures.length > 0 && (
        <Alert type="warning" showIcon
          message={<Title level={5} style={{ margin: 0 }}>Prior attempts — {failures.length} failed</Title>}
          description={
            <ul style={{ margin: 0, paddingLeft: 20 }}>
              {failures.slice(-5).map((f: any) => (
                <li key={f.attempt_id}>
                  <Text>{f.approach_summary || "(no summary)"}</Text>
                  <Tag color="red" style={{ marginLeft: 8 }}>{f.failure_reason}</Tag>
                </li>
              ))}
            </ul>
          }
          style={{ marginBottom: 16 }} />
      )}
      {data.runs.map((run: any) => (
        <ExperimentDetail key={run.index} run={run} />
      ))}
    </div>
  );
}
```

- [ ] **Step 4: Implement `ExperimentDetail.tsx`:**

```tsx
// web/src/components/session/ExperimentDetail.tsx
import { Card, Collapse, Descriptions, Tag } from "antd";

export function ExperimentDetail({ run }: {run: any}) {
  const repro = run.reproducibility ?? {};
  return (
    <Card size="small" style={{ marginBottom: 12 }}
      title={
        <span>
          <Tag color="blue">{run.tag}</Tag>
          #{run.index} {run.hypothesis_id && <Tag>H:{run.hypothesis_id}</Tag>}
        </span>
      }>
      <Descriptions size="small" column={2}>
        {Object.entries(run.metrics ?? {}).map(([k, v]) => (
          <Descriptions.Item key={k} label={k}>{String(v)}</Descriptions.Item>
        ))}
      </Descriptions>
      <Collapse ghost
        items={[
          { key: "repro", label: "Reproducibility",
            children: (
              <Descriptions size="small" column={1}>
                <Descriptions.Item label="seed">{repro.random_seed}</Descriptions.Item>
                <Descriptions.Item label="run">{repro.run_command}</Descriptions.Item>
                <Descriptions.Item label="git">{repro.git_ref}</Descriptions.Item>
                <Descriptions.Item label="env hash">{repro.environment_hash}</Descriptions.Item>
              </Descriptions>
            ),
          },
          { key: "stdout", label: "stdout",
            children: <pre style={{ fontSize: 11, background: "#fafafa", padding: 8 }}>{run.stdout ?? "(none)"}</pre> },
          { key: "stderr", label: "stderr",
            children: <pre style={{ fontSize: 11, background: "#fff1f0", padding: 8 }}>{run.stderr ?? "(none)"}</pre> },
        ]} />
    </Card>
  );
}
```

- [ ] **Step 5: Implement `ExperimentDiffView.tsx`:**

```tsx
// web/src/components/session/ExperimentDiffView.tsx
import { Row, Col } from "antd";
import { ExperimentDetail } from "./ExperimentDetail";

export function ExperimentDiffView({ a, b }: {a: any; b: any}) {
  return (
    <Row gutter={16}>
      <Col span={12}><ExperimentDetail run={a} /></Col>
      <Col span={12}><ExperimentDetail run={b} /></Col>
    </Row>
  );
}
```

- [ ] **Step 6: Run tests.**

- [ ] **Step 7: Commit.**

```bash
git add web/src/components/session/ExperimentsTab.tsx web/src/components/session/ExperimentDetail.tsx web/src/components/session/ExperimentDiffView.tsx web/tests/components/ExperimentsTab.test.tsx
git commit -m "feat(web): ExperimentsTab with per-run detail, prior-attempts ribbon, diff view scaffold"
```

### Task C8: Rework SessionDetailPage layout

**Files:**
- Modify: `web/src/pages/SessionDetailPage.tsx`
- Modify: `web/src/components/session/ControlBar.tsx`
- Modify: `web/src/stores/uiStore.ts`

- [ ] **Step 1: Rewrite `SessionDetailPage.tsx` to the stacked layout.** Full replacement:

```tsx
// web/src/pages/SessionDetailPage.tsx
import { Layout, Tabs, Typography, Alert, Skeleton, Card } from "antd";
import { useParams, Link } from "react-router-dom";
import { useSession } from "../hooks/useSession";
import { useWebSocket } from "../hooks/useWebSocket";
import { useUIStore } from "../stores/uiStore";
import { StatusBadge } from "../components/common/StatusBadge";
import { ControlBar } from "../components/session/ControlBar";
import { GraphTopology } from "../components/session/GraphTopology";
import { ChatView } from "../components/session/ChatView";
import { StageOutputPanel } from "../components/session/StageOutputPanel";
import { ExperimentsTab } from "../components/session/ExperimentsTab";
import { CostTracker } from "../components/session/CostTracker";
import { AgentMonitor } from "../components/session/AgentMonitor";
import { HypothesisTracker } from "../components/session/HypothesisTracker";
import { PIDecisionLog } from "../components/session/PIDecisionLog";
import { CheckpointModal } from "../components/session/CheckpointModal";
import { FeedbackInput } from "../components/session/FeedbackInput";

const { Sider, Content } = Layout;
const { Title, Text } = Typography;

function SectionHeader({ children }: { children: React.ReactNode }) {
  return (
    <div style={{ padding: "12px 16px 8px", color: "#6b7280",
                  fontSize: 11, fontWeight: 600, textTransform: "uppercase",
                  letterSpacing: "0.05em" }}>
      {children}
    </div>
  );
}

export default function SessionDetailPage() {
  const { sessionId = "" } = useParams();
  const { data: session, isLoading, error } = useSession(sessionId);
  const detailTab = useUIStore((s) => s.detailTab);
  const setDetailTab = useUIStore((s) => s.setDetailTab);
  useWebSocket(sessionId);

  if (error) return <Alert type="error" showIcon message="Failed to load session"
    description={<>{String((error as Error).message)} <Link to="/sessions">Back</Link></>} />;
  if (isLoading || !session) return <Card variant="borderless"><Skeleton active paragraph={{rows:4}} /></Card>;

  return (
    <div style={{ display: "flex", flexDirection: "column",
                  minHeight: "calc(100vh - 56px - 64px)" }}>
      <div style={{ marginBottom: 16, display: "flex", justifyContent: "space-between" }}>
        <div>
          <Title level={3} style={{ margin: 0, fontWeight: 600 }}>{session.research_topic}</Title>
          <Text type="secondary" style={{ fontSize: 12 }}>
            {session.session_id} · {session.user_id}
          </Text>
        </div>
        <StatusBadge status={session.status} />
      </div>

      <div style={{ marginBottom: 16 }}>
        <Card variant="borderless" styles={{ body: { padding: 8 } }}>
          <GraphTopology sessionId={sessionId} />
        </Card>
      </div>

      <Card variant="borderless" styles={{ body: { padding: 0 } }} style={{ flex: 1, display: "flex" }}>
        <Layout style={{ background: "transparent", flex: 1 }}>
          <Sider width={200} theme="light" style={{ background: "#fff", borderRight: "1px solid #efefef" }}>
            <SectionHeader>Controls</SectionHeader>
            <ControlBar sessionId={sessionId} />
          </Sider>
          <Content style={{ background: "#fff", padding: "12px 24px" }}>
            <Tabs activeKey={detailTab}
              onChange={(k) => setDetailTab(k as typeof detailTab)}
              type="line"
              items={[
                { key: "conversations", label: "Conversations", children: <ChatView sessionId={sessionId} /> },
                { key: "artifacts", label: "Artifacts", children: <StageOutputPanel sessionId={sessionId} /> },
                { key: "experiments", label: "Experiments", children: <ExperimentsTab sessionId={sessionId} /> },
                { key: "cost", label: "Cost", children: <CostTracker sessionId={sessionId} /> },
              ]} />
          </Content>
          <Sider width={320} theme="light" style={{ background: "#fff", borderLeft: "1px solid #efefef" }}>
            <SectionHeader>Agent Monitor</SectionHeader>
            <AgentMonitor sessionId={sessionId} />
            <div style={{ borderTop: "1px solid #efefef" }} />
            <SectionHeader>Hypotheses</SectionHeader>
            <HypothesisTracker sessionId={sessionId} />
            <div style={{ borderTop: "1px solid #efefef" }} />
            <SectionHeader>PI decisions</SectionHeader>
            <div style={{ padding: "0 12px 12px" }}><PIDecisionLog sessionId={sessionId} /></div>
            <div style={{ borderTop: "1px solid #efefef" }} />
            <SectionHeader>Cost</SectionHeader>
            <CostTracker sessionId={sessionId} compact />
          </Sider>
        </Layout>
      </Card>

      <div style={{ position: "sticky", bottom: 0, marginTop: 16, background: "#fff",
                    border: "1px solid #efefef", borderRadius: 12, padding: 12 }}>
        <FeedbackInput sessionId={sessionId} />
      </div>
      <CheckpointModal sessionId={sessionId} />
    </div>
  );
}
```

- [ ] **Step 2: Update `uiStore.ts` `detailTab` union** to `"conversations" | "artifacts" | "experiments" | "cost"` (drop `"activity"` and `"graph"`).

- [ ] **Step 3: Reduce `ControlBar.tsx` to global actions only.** Remove the per-stage control radio list. Keep Pause, Resume, Cancel, and Redirect buttons.

- [ ] **Step 4: Run existing tests; fix broken references.**

```bash
cd web && pnpm test
```

- [ ] **Step 5: Commit.**

```bash
git add web/src/pages/SessionDetailPage.tsx web/src/components/session/ControlBar.tsx web/src/stores/uiStore.ts
git commit -m "feat(web): stacked layout — graph canvas on top, tabs below, AgentMonitor right sider"
```

### Task C9: Delete legacy components

**Files:**
- Delete: `web/src/components/session/PipelineGraph.tsx`
- Delete: `web/src/components/session/PipelineTracker.tsx`
- Delete: `web/src/components/session/AgentActivityFeed.tsx`
- Delete: `web/tests/components/PipelineGraph.test.tsx`
- Delete: `web/tests/components/PipelineTracker.test.tsx`
- Delete: `web/tests/components/AgentActivityFeed.test.tsx`

- [ ] **Step 1: Remove files.**

```bash
cd web
rm src/components/session/PipelineGraph.tsx
rm src/components/session/PipelineTracker.tsx
rm src/components/session/AgentActivityFeed.tsx
rm tests/components/PipelineGraph.test.tsx
rm tests/components/PipelineTracker.test.tsx
rm tests/components/AgentActivityFeed.test.tsx
```

- [ ] **Step 2: Grep for any remaining imports and clean up.**

```bash
cd web && grep -r "PipelineGraph\|PipelineTracker\|AgentActivityFeed" src/ tests/
```
Expected: no matches. If any match remains, remove the import/usage.

- [ ] **Step 3: Run full tests.**

```bash
cd web && pnpm test
```

- [ ] **Step 4: Commit.**

```bash
git add -A
git commit -m "chore(web): delete PipelineGraph, PipelineTracker, AgentActivityFeed — superseded by GraphTopology/ChatView/AgentMonitor"
```

### Task C10: WebSocket event invalidation wiring

**Files:**
- Modify: `web/src/hooks/useWebSocket.ts`

- [ ] **Step 1: Map event types to query-key invalidations.** In the WS message handler, when an event arrives, invalidate the matching queries:

```typescript
const INVALIDATE: Record<string, (sid: string, data: any) => string[][]> = {
  agent_turn_started: (sid, d) => [["agent-history", sid, d.agent], ["agents", sid]],
  agent_turn_completed: (sid, d) => [
    ["agent-history", sid, d.agent],
    ["agent-memory", sid, d.agent],
    ["agent-context", sid, d.agent],
    ["agents", sid],
  ],
  pi_decision: (sid) => [["pi-history", sid]],
  hypothesis_update: (sid) => [["hypotheses", sid]],
  stage_started: (sid) => [["graph", sid]],
  stage_completed: (sid) => [["graph", sid], ["experiments", sid]],
  cost_update: (sid) => [["cost", sid]],
};

// inside onMessage handler:
const keys = INVALIDATE[ev.type]?.(sessionId, ev.data) ?? [];
for (const k of keys) queryClient.invalidateQueries({ queryKey: k });
```

Events where `agent` is missing from the payload (e.g., `agent_llm_response`) should inherit it from the most recent `agent_turn_started` with the same `turn_id`. Cache this mapping in a `Map<string, string>` keyed by `turn_id`, populated when `agent_turn_started` arrives and read when `agent_llm_response` / `agent_tool_result` arrive.

- [ ] **Step 2: Commit.**

```bash
git add web/src/hooks/useWebSocket.ts
git commit -m "feat(web): WS event → TanStack Query invalidation map for observability streams"
```

### Task C11: Plan 6C checkpoint

- [ ] **Step 1: Run full frontend suite.**

```bash
cd web && pnpm test && pnpm build
```
Expected: all tests pass, build succeeds.

- [ ] **Step 2: Run backend suite once more (ensure nothing regressed).**

```bash
cd d:/GitHub/AgentLabX
uv run pytest -v && uv run ruff check agentlabx/
```

- [ ] **Step 3: End-to-end `--mock-llm` walkthrough.**

```bash
uv run agentlabx serve --mock-llm
# Open http://localhost:8000
# Create a session with topic "observability smoke test"
# Watch the graph canvas: stages light up as they start; cursor follows active stage
# Click Conversations tab: see agent turns grouped by stage, [mock] tags visible,
#   system prompt collapsible, inline tool calls
# Click Experiments tab: see runs with stdout/stderr, prior-attempts ribbon if any failed
# Right sider: switch agents, inspect scope/context/memory/history
# PI decisions panel shows last 3 with confidence
```

- [ ] **Step 4: Tag Plan 6C and Plan 6 complete.**

```bash
git tag plan6c-complete
git tag plan6-complete
```

---

## Summary

Plan 6C complete when:
- 8 observability hooks exist (useGraph, useAgents, useAgentContext, useAgentHistory, useAgentMemory, usePIHistory, useCrossStageRequests, useExperiments)
- `GraphTopology` renders real topology with elkjs auto-layout; `StageNode` shows status/iter; skipped nodes at 0.4 opacity
- `ChatView` groups `agent_turns` by stage then by `turn_id`; inline tool calls; `[mock]` tags
- `AgentMonitor` per-agent tabs with Scope/Context/Memory/History subcards
- `ExperimentsTab` shows per-run detail (stdout/stderr/repro) and prior-attempts ribbon
- `PIDecisionLog` surfaces last 3 PI decisions with confidence
- `SessionDetailPage` uses stacked layout — graph always on, tabs below, AgentMonitor sider
- Legacy `PipelineGraph` / `PipelineTracker` / `AgentActivityFeed` deleted
- WS events invalidate matching TanStack Query keys for live updates
- `ControlBar` reduced to global actions (Pause/Resume/Cancel/Redirect)
- `pnpm test && pnpm build` clean
- End-to-end `--mock-llm` walkthrough passes: graph canvas live, conversations grouped, experiments rendered, agent monitor populated, PI decisions visible

Plan 6 (observability rollout) complete. AgentLabX web UI is now a research-lab observability tool.
