# Plan 7D: Frontend — Production-Line Graph + On-Demand Subgraph Drawers + PI Advice Surfacing

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans. Steps use checkbox (`- [ ]`) syntax for tracking.
>
> **Companion layout preview:** `docs/superpowers/specs/2026-04-14-plan7d-layout-preview.md` — render in Markdown preview for the Mermaid figures this plan implements.

**Goal:** Retrofit the Session Detail page to the Option A layout (chat hero + collapsible right drawer) with an always-visible production-line graph on top, plus two on-demand subgraph panels that open when the user clicks the active stage (inner subgraph) and the WORK node of the inner subgraph while a meeting is running (meeting subgraph). `CheckpointModal` consumes `decision.needs_approval` and surfaces the latest PI advice when an escalation triggers.

**Architecture:** Frontend recursion rule (spec §8.2 principle 5): all graph topology is **extracted from LangGraph** at runtime via `compiled.get_graph()` / `get_graph(xray=1)` — never hardcoded. The `/api/sessions/{id}/graph` endpoint returns top-level nodes/edges + an enriched `subgraphs` array populated with the active stage's compiled subgraph (when a stage is running) and the meeting's compiled subgraph (when a meeting is invoked). A stage's internal shape (Plan 7B T4: `enter → stage_plan → gate → work → evaluate → decide`, acyclic) is produced by `StageSubgraphBuilder` and read by the frontend as-is; if a future plan adds a node, the UI reflects it without code changes. Backtrack edges are synthesised from `state["backtrack_attempts"]` and rendered as dashed amber curves with attempt-count labels; labels demote to hover tooltips when total backtrack edges exceed 8.

**Tech Stack:** React 19, TypeScript 5.5, Vite 6, Ant Design 5, @xyflow/react + elkjs for layout, TanStack Query 5, Zustand 5, Vitest + React Testing Library.

**Pre-production principle:** AgentLabX has not shipped. Plan 7D makes breaking visual/layout changes — update tests when behaviour changes, no backwards-compat scaffolding.

**Spec sections implemented:** §8.2 Session Detail (graph-hierarchy principle, production-line top canvas, on-demand subgraph drawers, PI advice surfacing), §8.3 component list (drops `AgentHistoryCard`, adds `StageSubgraphDrawer`, `LabMeetingOverlay`, `StagePlanCard`; reframes `ChatView` to stage-grouped lazy-load).

**Companion documents:**
- `docs/superpowers/specs/2026-04-12-agentlabx-platform-design.md` §3.2.1 (stage subgraph shape), §8.2 (frontend layout), §8.3 (component list)
- `docs/superpowers/specs/2026-04-14-plan7d-layout-preview.md` (Mermaid figures + composed layout + density stress-tests)

**Existing WIP to reconcile:** Commit `6f5bfa2` contains frontend explorations predating this plan — ChatView refactor toward stage-grouped turns, ControlBar slim-down, new components `AgentTurnBubble`, `ToolCallAnnotation`, `ZoneNode`. Evaluate each against the new design (T9 explicitly handles this).

**Out of scope (later plans):**
- Pixel-art RPG `lab_scene` conversation renderer — reserved `ChatView.mode` prop; no implementation.
- Mobile layout — desktop-first.
- Token streaming (`agent_llm_chunk` event) — still level-B payload only.

---

## Design decisions pinned before implementation

Four seams with explicit calls from the layout-preview review.

**1. Layout: Option A — chat hero + right drawer.**

Header → always-visible graph strip (main + optional inner + optional meeting) → chat fills remaining main area → collapsible 320px drawer on the right carries all secondary tabs (Agent Monitor, Stage Plan, Hypotheses, PI Decisions, Cost, Artifacts, Experiments). The three-panel layout is dropped: the left "Agent Monitor" sider is consolidated into the right drawer, freeing the entire main column for chat. Feedback input stays sticky at the bottom.

**2. Subgraph drawers are on-demand (click to open), not auto-visible.**

- Inner subgraph: user clicks the active stage's node in the main graph → inner panel opens beneath the main strip. Click again → closes.
- Meeting subgraph: only reachable when a callable subgraph (currently `lab_meeting`) is running AND inner is open. User clicks the WORK node in the inner panel → meeting panel opens next to inner. Click again → closes.
- When both inner and meeting are open, they share a horizontal row (~50/50 split). When only inner is open, it takes full width of the subgraph row.
- Default state: both closed. Graph strip collapses to just the main graph.

**3. No hardcoded topology.**

All graph structure — top-level stages, inner stage subgraphs, meeting subgraphs — comes from `/api/sessions/{id}/graph` which extracts via `compiled.get_graph()` / `compiled.get_graph(xray=1)`. The frontend renders whatever nodes/edges the API returns. A plan that adds a new internal node or renames one produces an updated graph automatically; no UI change required. This reverses the earlier (stale) plan that proposed a hardcoded 5-node template in `StageSubgraphDrawer`.

**4. Backtracks are rendered as edges, not hidden.**

Each non-zero entry in `state["backtrack_attempts"]` becomes one dashed amber curve drawn directly origin → target, labelled with the attempt count. When total backtrack edges exceed 8, labels demote to hover tooltips (edges still render). No collapse toggle — the density stress-tests in the layout preview show even 28 edges remain parseable when the forward spine stays visible. This reverses the earlier (stale) plan that proposed dropping backtrack edges entirely.

**Cursor plumbing:** `/graph` response's `cursor` object carries three fields — `node_id` (active top-level stage), `internal_node` (active node inside stage's subgraph, e.g. "work"), `meeting_node` (active node inside meeting subgraph when running). All three drive a blue-ring `🔵` marker in their respective tiers.

---

## File structure

| File | Purpose | Create / Modify |
|---|---|---|
| `agentlabx/core/state.py` | Add `current_stage_internal_node: str \| None` + `current_meeting_node: str \| None` (written by subgraph nodes) | Modify |
| `agentlabx/stages/subgraph.py` | Each of the 5 subgraph node functions writes its own name to `state["current_stage_internal_node"]`; `decide_node` clears it on exit | Modify |
| `agentlabx/stages/lab_meeting.py` (future: once implemented) | Meeting subgraph's nodes write `state["current_meeting_node"]` | Modify — flag for later if lab_meeting body isn't implemented yet |
| `agentlabx/core/graph_mapper.py` | Extract active stage's subgraph + meeting's subgraph via `compiled.get_graph(xray=1)`; populate `subgraphs[]` with real nodes/edges; synthesise backtrack edges from `state["backtrack_attempts"]`; add `internal_node` + `meeting_node` to cursor | Modify |
| `agentlabx/server/routes/sessions.py` | Add `GET /api/sessions/{id}/stage_plans/{stage}` endpoint | Modify |
| `web/src/types/graph.ts` (if not present) | TypeScript types mirroring the `/graph` response shape | Create or modify |
| `web/src/hooks/useStagePlans.ts` | New TanStack Query hook for `/stage_plans/{stage}` | Create |
| `web/src/hooks/useGraph.ts` | Update return type to include enriched `subgraphs[]` + new cursor fields | Modify |
| `web/src/hooks/useWebSocket.ts` | Invalidate `["stage-plans", sessionId]` on `stage_started` / `stage_completed` | Modify |
| `web/src/components/session/GraphTopology.tsx` | Render forward edges + backtrack edges (dashed amber) with attempt-count labels; demote labels to tooltips when total > 8; active stage node clickable; cursor marker on active stage | Modify |
| `web/src/components/session/StageNode.tsx` | Existing; add click affordance `▾` on active stage; keep existing status/iter/cost/control chips | Modify |
| `web/src/components/session/StageSubgraphDrawer.tsx` | New — renders the active stage's subgraph from `topology.subgraphs[id=currentStage]`; cursor marker on `cursor.internal_node`; WORK node clickable when meeting is running | Create |
| `web/src/components/session/LabMeetingOverlay.tsx` | New — renders the meeting subgraph from `topology.subgraphs[id=lab_meeting]`; cursor marker on `cursor.meeting_node`; shown side-by-side with `StageSubgraphDrawer` when meeting is open | Create |
| `web/src/components/session/StagePlanCard.tsx` | New — renders latest `StagePlan.items[]` with status chips + rationale | Create |
| `web/src/components/session/ChatView.tsx` | Reshape into stage-grouped collapsible sections; only active-stage auto-expands; turns lazy-load per section on expand | Modify |
| `web/src/components/session/StageGroup.tsx` | Adapt to lazy-load semantics (don't call `useAgentHistory` until expanded) | Modify |
| `web/src/components/session/AgentMonitor.tsx` | Drop `AgentHistoryCard` composition; add `StagePlanCard` composition when viewing an agent belonging to the active stage | Modify |
| `web/src/components/session/AgentHistoryCard.tsx` | Delete — duplicated by ChatView per §8.2 | Delete |
| `web/src/components/session/CheckpointModal.tsx` | Read `decision.needs_approval` + latest `pi_decisions` entry; show PI advice + distinct `approve` vs `edit` UX | Modify |
| `web/src/pages/SessionDetailPage.tsx` | Apply Option A layout: header + graph strip (main + optional inner + optional meeting) + chat main area + right drawer + sticky feedback | Modify |
| `web/src/stores/uiStore.ts` | Track open/closed state of inner and meeting panels + right-drawer active tab | Modify |
| `web/src/components/session/ZoneNode.tsx` | Evaluate vs new GraphTopology needs; keep if it helps zone grouping visually, else delete | Modify or Delete |
| `web/tests/components/GraphTopology.test.tsx` | Backtrack edges rendered; labels demoted past 8; click on active stage fires toggle | Modify |
| `web/tests/components/StageSubgraphDrawer.test.tsx` | Renders from topology.subgraphs[activeStage]; cursor on internal_node | Create |
| `web/tests/components/LabMeetingOverlay.test.tsx` | Renders when meeting_node != null; cursor on meeting_node; closes on re-click | Create |
| `web/tests/components/StagePlanCard.test.tsx` | Status chips + rationale rendering | Create |
| `web/tests/components/ChatView.test.tsx` | Stage-grouped collapsibles; lazy-load on expand | Modify |
| `web/tests/components/CheckpointModal.test.tsx` | PI advice surfaces when pi_decisions has recent high-confidence entry | Modify |
| `web/tests/pages/SessionDetailPage.test.tsx` | Option A layout assertions | Modify |
| `tests/server/routes/test_stage_plans_endpoint.py` | Backend endpoint contract | Create |

---

## Task 1: Backend — subgraph extraction, cursor fields, stage_plans endpoint

**Files:**
- Modify: `agentlabx/core/state.py` (+ `current_stage_internal_node`, `current_meeting_node`)
- Modify: `agentlabx/stages/subgraph.py` (each node writes its name; decide clears)
- Modify: `agentlabx/core/graph_mapper.py` (extract subgraphs + synthesize backtrack edges + extend cursor)
- Modify: `agentlabx/server/routes/sessions.py` (+ stage_plans endpoint)
- Create: `tests/server/routes/test_stage_plans_endpoint.py`

### Step 1: Write failing endpoint test

Create `tests/server/routes/test_stage_plans_endpoint.py`:

```python
"""GET /api/sessions/{id}/stage_plans/{stage} returns StagePlan history."""
from __future__ import annotations

import os
import pytest
from fastapi.testclient import TestClient

from agentlabx.server.app import create_app


@pytest.fixture
def client(tmp_path):
    os.environ["AGENTLABX_STORAGE__DATABASE_URL"] = (
        f"sqlite+aiosqlite:///{tmp_path / 'sp.db'}"
    )
    os.environ["AGENTLABX_STORAGE__ARTIFACTS_PATH"] = str(tmp_path / "artifacts")
    app = create_app(use_mock_llm=True)
    with TestClient(app) as c:
        yield c
    os.environ.pop("AGENTLABX_STORAGE__DATABASE_URL", None)
    os.environ.pop("AGENTLABX_STORAGE__ARTIFACTS_PATH", None)


def test_stage_plans_endpoint_empty_for_unstarted_session(client):
    r = client.post("/api/sessions", json={"topic": "t", "user_id": "default"})
    assert r.status_code == 201
    sid = r.json()["session_id"]

    r2 = client.get(f"/api/sessions/{sid}/stage_plans/literature_review")
    assert r2.status_code == 200
    assert r2.json() == {"stage_name": "literature_review", "plans": []}


def test_stage_plans_endpoint_404_on_unknown_session(client):
    r = client.get("/api/sessions/nonexistent/stage_plans/literature_review")
    assert r.status_code == 404
```

### Step 2: Add the endpoint

In `agentlabx/server/routes/sessions.py` (match existing route patterns for imports and dependencies):

```python
@router.get("/sessions/{session_id}/stage_plans/{stage_name}")
async def get_stage_plans(
    session_id: str,
    stage_name: str,
    context: AppContext = Depends(get_app_context),
) -> dict:
    session = context.session_manager.get_session(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail=f"Session {session_id} not found")
    state = session.state or {}
    stage_plans = (state.get("stage_plans") or {}).get(stage_name, [])
    return {"stage_name": stage_name, "plans": stage_plans}
```

Verify: `uv run pytest tests/server/routes/test_stage_plans_endpoint.py -v` passes.

### Step 3: Add cursor fields to PipelineState

In `agentlabx/core/state.py` inside `PipelineState`:

```python
    # Active subgraph internal-node cursor (Plan 7D)
    # Populated by StageSubgraphBuilder nodes via state mutation; cleared by
    # decide_node on stage exit. Consumed by graph_mapper's cursor.
    current_stage_internal_node: str | None
    current_meeting_node: str | None
```

Initialize to `None` in `create_initial_state`.

### Step 4: Subgraph nodes write the cursor

In `agentlabx/stages/subgraph.py`, each node function writes its name BEFORE doing its work. Because the subgraph runs atomically from the parent's perspective (no per-node checkpointing), the user observes these transitions via live WebSocket events from `StageRunner`, not via LangGraph checkpoints. The written values persist into the state dict and flow to `graph_mapper`.

```python
async def enter_node(s: _SubgraphState) -> dict[str, Any]:
    s["state"]["current_stage_internal_node"] = "enter"
    return {}

async def plan_node(s: _SubgraphState) -> dict[str, Any]:
    s["state"]["current_stage_internal_node"] = "stage_plan"
    # ... existing body

async def work_node(s: _SubgraphState) -> dict[str, Any]:
    s["state"]["current_stage_internal_node"] = "work"
    # ... existing body

def evaluate_node(s: _SubgraphState) -> dict[str, Any]:
    s["state"]["current_stage_internal_node"] = "evaluate"
    # ... existing body

def decide_node(s: _SubgraphState) -> dict[str, Any]:
    s["state"]["current_stage_internal_node"] = "decide"
    # ... existing body
    # at end (before returning):
    # leave it as "decide" — StageRunner will blank it on stage completion
```

In `agentlabx/stages/runner.py` at the end of `run()` (after subgraph invocation completes):

```python
    # Clear internal-node cursor now that the subgraph has exited.
    update["current_stage_internal_node"] = None
```

### Step 5: Extract subgraphs + synthesize backtrack edges in graph_mapper

In `agentlabx/core/graph_mapper.py`, rework `build_topology` to:

1. Read top-level nodes/edges from `compiled_graph.get_graph()` (existing behaviour).
2. For the currently-active stage (`state["current_stage"]`), extract its compiled subgraph via `compiled_graph.get_graph(xray=1)` — this returns a dict-like structure with nested subgraph entries. Find the entry whose id matches the active stage; populate its `nodes` and `edges` in the returned `subgraphs[]` array.
3. For any running meeting (detect via `state["current_meeting_node"] is not None` or via registered invocable-only stages in the registry), extract its subgraph similarly.
4. Synthesize backtrack edges from `state["backtrack_attempts"]` — one edge per entry with `kind: "backtrack"` and `attempts` populated.
5. Populate `cursor.internal_node` from `state["current_stage_internal_node"]` and `cursor.meeting_node` from `state["current_meeting_node"]`.

The registry-less fallback path (for tests without a registry) skips subgraph extraction; returns empty `subgraphs[]`. The xray=1 extraction needs LangGraph's actual graph-walking API — confirm method signatures against current LangGraph version (check `compiled_graph.get_graph(xray=1).nodes` structure; some versions return a `Graph` object with `.nodes`/`.edges` attrs, others return a dict). Adapt to whichever shape the installed version produces.

Add unit tests in `tests/core/test_graph_mapper.py`:

- `test_graph_topology_includes_cursor_internal_node_when_state_has_it`
- `test_graph_topology_extracts_active_stage_subgraph`
- `test_graph_topology_synthesizes_backtrack_edges_from_state`

### Step 6: Commit

```bash
git add agentlabx/core/state.py agentlabx/stages/subgraph.py agentlabx/stages/runner.py agentlabx/core/graph_mapper.py agentlabx/server/routes/sessions.py tests/server/routes/test_stage_plans_endpoint.py tests/core/test_graph_mapper.py
git commit -m "feat(api): stage_plans endpoint + subgraph extraction + cursor plumbing (Plan 7D T1)"
```

---

## Task 2: Frontend hook — `useStagePlans` + graph-cache invalidation

**Files:**
- Create: `web/src/hooks/useStagePlans.ts`
- Modify: `web/src/hooks/useWebSocket.ts`
- Create: `web/tests/hooks/useStagePlans.test.tsx`

### Step 1: Write failing test

Create `web/tests/hooks/useStagePlans.test.tsx`:

```typescript
import { describe, it, expect, vi } from "vitest";
import { renderHook, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import type { ReactNode } from "react";
import { useStagePlans } from "../../src/hooks/useStagePlans";

function wrapper() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={qc}>{children}</QueryClientProvider>
  );
}

describe("useStagePlans", () => {
  it("fetches stage plans for a given stage", async () => {
    const mockResponse = {
      stage_name: "literature_review",
      plans: [
        {
          items: [
            {
              id: "lit:topic-survey",
              description: "Survey X",
              status: "todo",
              source: "contract",
              existing_artifact_ref: null,
              edit_note: null,
              removed_reason: null,
            },
          ],
          rationale: "Default plan",
          hash_of_consumed_inputs: "abc",
        },
      ],
    };
    vi.spyOn(globalThis, "fetch").mockResolvedValueOnce({
      ok: true,
      json: () => Promise.resolve(mockResponse),
    } as Response);

    const { result } = renderHook(
      () => useStagePlans("sess-1", "literature_review"),
      { wrapper: wrapper() },
    );

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(result.current.data).toEqual(mockResponse);
  });
});
```

### Step 2: Implement `useStagePlans`

Mirror the pattern of `web/src/hooks/usePIHistory.ts` (or similar Plan 6 hook). Query key: `["stage-plans", sessionId, stageName]`. URL: `/api/sessions/{sessionId}/stage_plans/{stageName}`.

### Step 3: WS invalidation

In `web/src/hooks/useWebSocket.ts` add `stage-plans` to the keys invalidated on `stage_started` / `stage_completed`:

```typescript
stage_started: (sid) => [["graph", sid], ["stage-plans", sid]],
stage_completed: (sid) => [
  ["graph", sid],
  ["experiments", sid],
  ["session", sid],
  ["artifacts", sid],
  ["transitions", sid],
  ["hypotheses", sid],
  ["stage-plans", sid],
],
```

### Step 4: Run tests + commit

```bash
cd web && npm test -- useStagePlans useWebSocket
cd .. && git add web/ && git commit -m "feat(web): useStagePlans hook + WS invalidation (Plan 7D T2)"
```

---

## Task 3: `GraphTopology` — render forward + backtrack edges + clickable active stage

**Files:**
- Modify: `web/src/components/session/GraphTopology.tsx`
- Modify: `web/src/components/session/StageNode.tsx`
- Modify: `web/tests/components/GraphTopology.test.tsx`

### Step 1: Update GraphTopology test

```typescript
it("renders forward edges solid and backtrack edges dashed with labels", () => {
  const topology = {
    nodes: [
      { id: "lit", type: "stage", label: "Lit", zone: "discovery" },
      { id: "exp", type: "stage", label: "Exp", zone: "implementation" },
    ],
    edges: [
      { from: "lit", to: "exp", kind: "sequential" },
      { from: "exp", to: "lit", kind: "backtrack", attempts: 2 },
    ],
    cursor: { node_id: "exp", internal_node: null, meeting_node: null },
    subgraphs: [],
  };
  const { container } = render(<GraphTopology topology={topology} />);
  const edges = container.querySelectorAll(".react-flow__edge");
  expect(edges.length).toBe(2);  // both rendered
  expect(container.textContent).toContain("↩ 2");  // label visible at low density
});

it("demotes backtrack labels to tooltips when count > 8", () => {
  const makeBacktracks = (n: number) =>
    Array.from({ length: n }, (_, i) => ({
      from: "exp",
      to: "lit",
      kind: "backtrack",
      attempts: i + 1,
    }));
  const topology = {
    nodes: [/* ... 2 stage nodes */],
    edges: [/* 1 forward */, ...makeBacktracks(9)],
    cursor: { node_id: "exp", internal_node: null, meeting_node: null },
    subgraphs: [],
  };
  const { container } = render(<GraphTopology topology={topology} />);
  // 9 backtrack edges: no label text visible
  expect(container.textContent).not.toContain("↩ 9");
  // edges still in DOM
  expect(container.querySelectorAll(".react-flow__edge").length).toBe(10);
});

it("clicking the active stage fires onStageClick", async () => {
  const onStageClick = vi.fn();
  const topology = {
    nodes: [{ id: "exp", type: "stage", label: "Exp", zone: "implementation" }],
    edges: [],
    cursor: { node_id: "exp", internal_node: "work", meeting_node: null },
    subgraphs: [],
  };
  const { getByText } = render(
    <GraphTopology topology={topology} onStageClick={onStageClick} />,
  );
  await userEvent.click(getByText("Exp"));
  expect(onStageClick).toHaveBeenCalledWith("exp");
});
```

### Step 2: Update `GraphTopology.tsx`

- Keep forward edges as solid React Flow edges (existing behaviour).
- Render backtrack edges as dashed amber edges. When `backtrackCount > 8`, set `label: ""` and add a tooltip/title.
- Pass `onStageClick` down to `StageNode` for the active stage.
- Cursor ring: apply `active` class to the node whose id === `cursor.node_id`.

Compute `backtrackCount = topology.edges.filter(e => e.kind === "backtrack").length`. Apply label-demote threshold in the edge mapping:

```typescript
const DEMOTE_THRESHOLD = 8;
const backtrackEdges = topology.edges.filter((e) => e.kind === "backtrack");
const demoteLabels = backtrackEdges.length > DEMOTE_THRESHOLD;

const rfEdges = topology.edges.map((e, i) => ({
  id: `e${i}`,
  source: e.from,
  target: e.to,
  style:
    e.kind === "backtrack"
      ? { stroke: "#d97706", strokeDasharray: "5 5" }
      : undefined,
  label: e.kind === "backtrack" && !demoteLabels ? `↩ ${e.attempts}` : undefined,
  labelStyle: { fontSize: 10, fill: "#d97706" },
  // tooltip for demoted label — React Flow's label prop doesn't carry a title;
  // use data.title and render via a custom edge component if needed.
  data: {
    title: e.kind === "backtrack" ? `Backtrack: ${e.attempts} attempt(s)` : undefined,
  },
}));
```

### Step 3: Update `StageNode.tsx` for click affordance

Add `onStageClick` prop. When active (i.e., `cursor.node_id === node.id`), show `▾` glyph + cursor ring. Entire node clickable via `onClick={() => onStageClick?.(node.id)}`.

### Step 4: Run tests + commit

```bash
cd web && npm test -- GraphTopology StageNode
cd .. && git add web/ && git commit -m "feat(web): GraphTopology renders backtrack edges + label demote + click affordance (Plan 7D T3)"
```

---

## Task 4: `StageSubgraphDrawer` — dynamic topology from `/graph` subgraphs[]

**Files:**
- Create: `web/src/components/session/StageSubgraphDrawer.tsx`
- Create: `web/tests/components/StageSubgraphDrawer.test.tsx`

### Step 1: Write failing test

```typescript
import { describe, it, expect, vi } from "vitest";
import { render } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { StageSubgraphDrawer } from "../../src/components/session/StageSubgraphDrawer";

const mockSubgraph = {
  id: "experimentation",
  kind: "stage_subgraph",
  nodes: [
    { id: "enter", type: "internal" },
    { id: "stage_plan", type: "internal" },
    { id: "work", type: "internal" },
    { id: "evaluate", type: "internal" },
    { id: "decide", type: "internal" },
  ],
  edges: [
    { from: "enter", to: "stage_plan" },
    { from: "stage_plan", to: "work" },
    { from: "stage_plan", to: "decide" },
    { from: "work", to: "evaluate" },
    { from: "evaluate", to: "decide" },
  ],
};

describe("StageSubgraphDrawer", () => {
  it("renders nothing when closed", () => {
    const { container } = render(
      <StageSubgraphDrawer
        activeStage={null}
        subgraph={null}
        cursorInternalNode={null}
        meetingActive={false}
        onWorkClick={() => {}}
      />,
    );
    expect(container.firstChild).toBeNull();
  });

  it("renders nodes from topology subgraph when open", () => {
    const { getByText } = render(
      <StageSubgraphDrawer
        activeStage="experimentation"
        subgraph={mockSubgraph}
        cursorInternalNode="work"
        meetingActive={false}
        onWorkClick={() => {}}
      />,
    );
    ["enter", "stage_plan", "work", "evaluate", "decide"].forEach((nodeId) => {
      expect(getByText(new RegExp(nodeId, "i"))).toBeInTheDocument();
    });
  });

  it("highlights the cursorInternalNode", () => {
    const { container } = render(
      <StageSubgraphDrawer
        activeStage="experimentation"
        subgraph={mockSubgraph}
        cursorInternalNode="evaluate"
        meetingActive={false}
        onWorkClick={() => {}}
      />,
    );
    const active = container.querySelector("[data-internal-node='evaluate'].active");
    expect(active).not.toBeNull();
  });

  it("WORK node is clickable when meetingActive=true", async () => {
    const onWorkClick = vi.fn();
    const { getByText } = render(
      <StageSubgraphDrawer
        activeStage="experimentation"
        subgraph={mockSubgraph}
        cursorInternalNode="work"
        meetingActive={true}
        onWorkClick={onWorkClick}
      />,
    );
    await userEvent.click(getByText(/work/i));
    expect(onWorkClick).toHaveBeenCalled();
  });
});
```

### Step 2: Implement

```typescript
import React from "react";
import { Card } from "antd";
import type { GraphSubgraph } from "../../types/graph";

interface Props {
  activeStage: string | null;
  subgraph: GraphSubgraph | null;
  cursorInternalNode: string | null;
  meetingActive: boolean;
  onWorkClick: () => void;
}

export function StageSubgraphDrawer({
  activeStage,
  subgraph,
  cursorInternalNode,
  meetingActive,
  onWorkClick,
}: Props) {
  if (!activeStage || !subgraph) return null;

  return (
    <Card size="small" title={`Inside ${activeStage}`} style={{ marginTop: 12 }}>
      <div style={{ display: "flex", gap: 24, alignItems: "center", padding: "8px 16px" }}>
        {subgraph.nodes.map((n, i) => {
          const isActive = cursorInternalNode === n.id;
          const isWork = n.id === "work";
          const clickable = isWork && meetingActive;
          return (
            <React.Fragment key={n.id}>
              <div
                data-internal-node={n.id}
                className={isActive ? "active" : ""}
                onClick={clickable ? onWorkClick : undefined}
                style={{
                  padding: "6px 12px",
                  borderRadius: 6,
                  border: "1px solid",
                  borderColor: isActive ? "#1677ff" : "#d9d9d9",
                  background: isActive ? "#e6f4ff" : "transparent",
                  fontWeight: isActive ? 600 : 400,
                  fontSize: 12,
                  cursor: clickable ? "pointer" : "default",
                }}
              >
                {n.id.toUpperCase()}{clickable ? " ▾" : ""}
              </div>
              {i < subgraph.nodes.length - 1 && <span style={{ color: "#bfbfbf" }}>→</span>}
            </React.Fragment>
          );
        })}
      </div>
    </Card>
  );
}
```

Note: this renders nodes in the order they appear in `subgraph.nodes`. For more sophisticated layouts (e.g., if a future subgraph has branching), switch to React Flow with the topology's edges. For the current 5-node linear shape (Plan 7B T4), a flat flex row is sufficient.

### Step 3: Run tests + commit

```bash
cd web && npm test -- StageSubgraphDrawer
cd .. && git add web/ && git commit -m "feat(web): StageSubgraphDrawer renders dynamic topology from /graph (Plan 7D T4)"
```

---

## Task 4a: `LabMeetingOverlay` — meeting subgraph, opens next to inner

**Files:**
- Create: `web/src/components/session/LabMeetingOverlay.tsx`
- Create: `web/tests/components/LabMeetingOverlay.test.tsx`

Structurally similar to `StageSubgraphDrawer`: renders nodes from `topology.subgraphs[id="lab_meeting"]`; cursor from `cursor.meeting_node`; no `▾` (no further nesting today).

### Step 1: Write failing test + Step 2: Implement

Follow the same pattern as T4. The component's Props:

```typescript
interface Props {
  subgraph: GraphSubgraph | null;
  cursorMeetingNode: string | null;
}
```

Rendering visibility is controlled by the parent (`SessionDetailPage`) — this component just renders what it's given.

### Step 3: Run tests + commit

```bash
git commit -m "feat(web): LabMeetingOverlay renders meeting subgraph (Plan 7D T4a)"
```

---

## Task 5: `StagePlanCard` — status chips + rationale

**Files:**
- Create: `web/src/components/session/StagePlanCard.tsx`
- Create: `web/tests/components/StagePlanCard.test.tsx`

Same contract as the earlier draft. Renders a `StagePlan` with ant-design `Tag`s color-coded per status (`done=green`, `edit=orange`, `todo=blue`, `removed=default`). Shows `rationale` as a secondary paragraph above the item list.

Dispatch as a small independent task (see prior Plan 7D draft §T5 code listing — unchanged). Commit message:

```bash
git commit -m "feat(web): StagePlanCard renders plan items with status chips (Plan 7D T5)"
```

---

## Task 6: `ChatView` — stage-grouped, collapsible, lazy-loaded

**Files:**
- Modify: `web/src/components/session/ChatView.tsx`
- Modify: `web/src/components/session/StageGroup.tsx`
- Modify: `web/tests/components/ChatView.test.tsx`

Audit the existing WIP at `6f5bfa2` first (`git show 6f5bfa2 -- web/src/components/session/ChatView.tsx`) — it already partially implements this shape; the remaining work is (a) per-section lazy-load via `useAgentHistory` gated on `isExpanded`, and (b) auto-expanding only the active-stage section.

Use Ant Design's `Collapse` with explicit `activeKey` control (parent tracks a string[]). Each `StageGroup` child calls `useAgentHistory` ONLY when its stage is in `activeKey`.

Commit:

```bash
git commit -m "feat(web): ChatView stage-grouped + lazy-load per section (Plan 7D T6)"
```

---

## Task 7: `CheckpointModal` consumes `needs_approval` + surfaces PI advice

**Files:**
- Modify: `web/src/components/session/CheckpointModal.tsx`
- Modify: `web/tests/components/CheckpointModal.test.tsx`

Add a top banner (Ant Design `Alert` type=info) when the latest `pi_decisions` entry has `confidence >= threshold` and `used_fallback === false`. Format:

> **PI advisor recommends `<next_stage>`** ({confidence * 100}% confidence)
> `<reasoning>`

Distinguish `approve` vs `edit` stage controls by reading the `SessionPreferences.stage_controls[stage]` value: `approve` → two buttons (Accept / Override), `edit` → form for editing the stage output before advancing.

Closes the M2 TODO(7D) left by Plan 7C at `agentlabx/core/pipeline.py` (where `decision.needs_approval` is currently unread).

Commit:

```bash
git commit -m "feat(web): CheckpointModal surfaces PI advice + approve/edit UX (Plan 7D T7)"
```

---

## Task 8: `SessionDetailPage` Option A layout + uiStore state

**Files:**
- Modify: `web/src/pages/SessionDetailPage.tsx`
- Modify: `web/src/stores/uiStore.ts`
- Modify: `web/tests/pages/SessionDetailPage.test.tsx`

### Layout target

```
┌──────────────────────────────────────────────────────────────┐
│ Header                                                        │
├──────────────────────────────────────────────────────────────┤
│ GraphTopology (main production line, always visible)          │
│ [StageSubgraphDrawer | LabMeetingOverlay]  ← conditional row  │
├──────────────────────────────────────────────┬───────────────┤
│ ChatView (main column, flex)                 │ Drawer 320px  │
│                                              │ (toggle)      │
│                                              │  Tabs:        │
│                                              │   Monitor /   │
│                                              │   Plan / Hyps │
│                                              │   PI / Cost / │
│                                              │   Artif / Exp │
├──────────────────────────────────────────────┴───────────────┤
│ FeedbackInput (sticky)                                        │
└──────────────────────────────────────────────────────────────┘
```

### uiStore fields to add

```typescript
interface UIState {
  // ... existing fields
  innerPanelOpen: boolean;    // user clicked active stage
  meetingPanelOpen: boolean;  // user clicked WORK while meeting active
  drawerOpen: boolean;        // right secondary drawer
  drawerTab: "monitor" | "plan" | "hypotheses" | "pi" | "cost" | "artifacts" | "experiments";

  toggleInnerPanel: () => void;
  toggleMeetingPanel: () => void;
  toggleDrawer: () => void;
  setDrawerTab: (tab: DrawerTab) => void;
}
```

Closing the stage (inner panel closes when stage exits) is automatic — selector on `cursor.node_id` change.

### Integration

- `SessionDetailPage` reads `topology = useGraph(sessionId).data`.
- `StageSubgraphDrawer` receives `subgraph = topology.subgraphs.find(s => s.id === topology.cursor.node_id) ?? null`.
- `LabMeetingOverlay` receives `subgraph = topology.subgraphs.find(s => s.id === "lab_meeting") ?? null` (only rendered when `topology.cursor.meeting_node != null`).
- Row with both open: `<Row gutter={16}><Col span={12}><StageSubgraphDrawer/></Col><Col span={12}><LabMeetingOverlay/></Col></Row>`; otherwise inner takes full width.

### Delete `AgentHistoryCard`

```bash
rm web/src/components/session/AgentHistoryCard.tsx
rm web/tests/components/AgentHistoryCard.test.tsx  # if present
```

Also audit: `AgentTurn.tsx` vs `AgentTurnBubble.tsx` (pick one, delete the other); `ToolCallInline.tsx` vs `ToolCallAnnotation.tsx` (same); `ZoneNode.tsx` (keep if still used by GraphTopology's zone grouping, else delete).

Commit:

```bash
git commit -m "feat(web): SessionDetailPage Option A layout + subgraph panel state (Plan 7D T8)"
```

---

## Task 9: Reconcile WIP at `6f5bfa2` + deletion cleanup

**Files:**
- Evaluate: `web/src/components/session/AgentTurn.tsx` vs `AgentTurnBubble.tsx`
- Evaluate: `web/src/components/session/ToolCallInline.tsx` vs `ToolCallAnnotation.tsx`
- Evaluate: `web/src/components/session/ZoneNode.tsx`

For each duplicate pair or stale component, either:
- **Keep** if it's cleanly used by the new layout (e.g., `AgentTurnBubble` might be the canonical chat-row; `ToolCallAnnotation` might be the canonical inline tool display).
- **Delete** if superseded or unused.

This task is the last pass before ship — run the full frontend suite and tidy any unused imports/components the prior tasks accumulated.

Commit:

```bash
git commit -m "chore(web): reconcile WIP components + delete duplicates (Plan 7D T9)"
```

---

## Self-review checklist

- [ ] **Spec coverage:**
  - §8.2 graph-hierarchy principle: T3 (main), T4 (inner), T4a (meeting), T8 (layout)
  - §8.2 production-line + backtrack edge rendering: T3
  - §3.2.1 stage subgraph shape: T1 (extraction), T4 (rendering) — matches updated 2-branch acyclic shape
  - §5.5 `invocable_only` subgraphs surfacing: T1 (enriched subgraphs[]), T4a (rendering)
  - §8.3 component list updates: T5 (StagePlanCard), T8 (drop AgentHistoryCard), T7 (CheckpointModal)
  - Backend: §7.1 stage_plans endpoint — T1
  - PI advice surfacing: T7

- [ ] **No placeholders.** Every step shows concrete code + commands or points at an existing component pattern to mirror.

- [ ] **Type consistency:** `GraphSubgraph`, `StagePlan`, `StagePlanItem`, `StagePlanStatus`, cursor fields — all mirror backend.

- [ ] **Pre-production principle:** delete obsolete components outright; no backwards-compat retention.

- [ ] **Spec-alignment discipline:** no divergence from spec §3.2.1 or §8.2 without explicit user approval + spec update.

---

## Execution

Ship after validating the layout preview against rendered Mermaid. Subagent-driven execution recommended; dispatch T1 first (backend foundation), then T2 (frontend hook), then T3–T9 in order.

Follow-ups not in 7D:
- Plan 7B² stage migrations (independent of frontend)
- `TestFullSessionLifecycle` E2E timeout investigation
- `lab_scene` conversation renderer (reserved ChatView.mode prop)
- `lab_meeting` subgraph body (separate plan when the multi-agent discussion logic is specced)
