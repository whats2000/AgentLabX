# Plan 7D: Frontend — Production-Line Graph + Recursive Subgraph Drawer + PI Advice Surfacing

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Retrofit the Session Detail page to match spec §8.2 — top canvas is a clean "production line" graph (forward edges + zone grouping, NO backtrack edges rendered), directly beneath it an active-stage subgraph drawer renders the currently-executing stage's internal nodes (`enter → stage_plan → gate → work → evaluate → decide`), and when `work` invokes a nested subgraph (`lab_meeting`) a third tier attaches. ChatView on the right side-panel groups conversation turns by stage with lazy-loaded collapsible sections. Agent Monitor lives on the left (no conversation duplication). `CheckpointModal` consumes `decision.needs_approval` and surfaces the latest PI advice when an escalation triggers.

**Architecture:** The frontend recursion rule is: always render the overall production line; render a sub-tier graph ONLY for the currently-active node; recurse down when that node itself invokes a nested subgraph. Inactive branches are never instantiated. All tiers read from the existing `/api/sessions/{id}/graph` endpoint (which already emits invocable-only stages in `subgraphs`, per Plan 7B T2) plus the new `/api/sessions/{id}/stage_plans/{stage}` endpoint added in T1 here. `GraphTopology` component stays on `@xyflow/react` but drops zone-hub edges and backtrack overlays — backtrack visual is a cursor-jump animation + small "↩ N" badge on the stage node's history.

**Tech Stack:** React 19, TypeScript 5.5, Vite 6, Ant Design 5, @xyflow/react + elkjs for layout, TanStack Query 5, Zustand 5, Vitest + React Testing Library.

**Pre-production principle:** AgentLabX has not shipped. Plan 7D makes breaking visual/layout changes — update tests when behaviour changes, no backwards-compat scaffolding.

**Spec sections implemented:** §8.2 Session Detail (graph-hierarchy principle, production-line top canvas, active-stage subgraph drawer, nested subgraph attachments), §8.3 component list (drops `AgentHistoryCard`, adds `StageSubgraphDrawer`, `StagePlanCard`; reframes `ChatView` to stage-grouped lazy-load).

**Companion spec:** `docs/superpowers/specs/2026-04-12-agentlabx-platform-design.md` §8.2, §8.3.

**Existing WIP to reconcile:** Commit `6f5bfa2` contains frontend explorations predating this plan — ChatView refactor toward stage-grouped turns, ControlBar slim-down, new components `AgentTurnBubble`, `ToolCallAnnotation`, `ZoneNode`. Evaluate each against the new design (T8 explicitly handles this).

**Out of scope (later plans):**
- Pixel-art RPG `lab_scene` conversation renderer — reserved `ChatView.mode` prop; no implementation.
- Mobile layout — desktop-first.
- Token streaming (`agent_llm_chunk` event) — still level-B payload only.

---

## Design decisions pinned before implementation

Three seams worth explicit calls.

**1. `StageSubgraphDrawer` renders the canonical 5-node shape from a hardcoded template, NOT from an API call.**

Every stage's subgraph has the same topology: `enter → stage_plan → gate → work → evaluate → decide`. Stages differ in their hook implementations (T3/T6 from Plan 7B), not their graph shape. The drawer renders a static React Flow graph with those 5 nodes; the "active node" cursor is driven by the `current_stage_internal_node` field read from graph topology (new in T1), or falls back to animating the whole drawer to match `/api/sessions/{id}` state. The drawer is NOT generated per-stage from a server-returned subgraph description — that would be over-engineering for identical shapes.

**2. Nested-subgraph rendering (e.g., `lab_meeting` invoked from `work`) is a modal/overlay anchored to the `work` node in the drawer, NOT a third tier stacked below.**

When `lab_meeting` fires, the frontend receives a `stage_started` event with `stage="lab_meeting"` and a `parent_stage` field (new — added in T1). The drawer visually anchors a small nested graph to the `work` node (via React Flow's native sub-rendering or a Popover overlay). On exit, the overlay fades out, leaving a collapsible `LabMeetingResult` chip on the `work` node. This keeps the recursion rule (active node → its graph) visually clean without cascading the whole layout downward.

**3. Backtracks are animated, never drawn as edges.**

When the cursor jumps backward (e.g., experimentation → literature_review via backtrack), the production-line graph plays a reverse-sweep cursor animation across the zones. The origin stage gets a subtle "↩ N" badge where N is `backtrack_attempts[origin→target]` (already exposed on topology edges per Plan 7A T9, but we DON'T render those edges as lines). This is intentional: backtrack edges produced a hairball under the old layout (pre-Plan 7).

---

## File structure

| File | Purpose | Create / Modify |
|---|---|---|
| `agentlabx/server/routes/sessions.py` | Add `GET /api/sessions/{id}/stage_plans/{stage}` endpoint; expose `current_stage_internal_node` + `parent_stage` in topology/state | Modify |
| `agentlabx/core/graph_mapper.py` | Include `current_stage_internal_node` in topology cursor when available (read from a new `state` field populated by `StageRunner`) | Modify |
| `agentlabx/core/state.py` | Add `current_stage_internal_node: str \| None` (e.g., "work", "evaluate") | Modify |
| `agentlabx/stages/runner.py` / `subgraph.py` | Emit stage-internal events + write `current_stage_internal_node` on each subgraph node transition | Modify |
| `web/src/hooks/useStagePlans.ts` | New TanStack Query hook for `/stage_plans/{stage}` | Create |
| `web/src/components/session/GraphTopology.tsx` | Drop backtrack-edge rendering; add cursor-jump animation on backtrack; add "↩ N" badge component | Modify |
| `web/src/components/session/StageNode.tsx` | Existing; add elapsed-time counter + live-cost chip; confirm per-stage control dropdown stays | Modify |
| `web/src/components/session/StageSubgraphDrawer.tsx` | New — static 5-node subgraph below production line, only mounted when a stage is active | Create |
| `web/src/components/session/StagePlanCard.tsx` | New — renders `StagePlan.items[]` with status chips (done/edit/todo/removed) + rationale | Create |
| `web/src/components/session/LabMeetingOverlay.tsx` | New — nested subgraph attachment for invocable stages fired from `work` | Create |
| `web/src/components/session/ChatView.tsx` | Reshape into stage-grouped collapsible sections; lazy-load turns per section | Modify |
| `web/src/components/session/StageGroup.tsx` | Existing; adapt to lazy-load semantics; auto-expand only active stage | Modify |
| `web/src/components/session/AgentMonitor.tsx` | Drop `AgentHistoryCard` composition; add `StagePlanCard` composition when viewing the active stage's agents | Modify |
| `web/src/components/session/AgentHistoryCard.tsx` | Remove entirely (duplicated by ChatView) | Delete |
| `web/src/components/session/CheckpointModal.tsx` | Read `decision.needs_approval` + latest `pi_decisions` entry; show PI advice + distinct `approve` vs `edit` UX | Modify |
| `web/src/pages/SessionDetailPage.tsx` | Apply the layout principle: top = GraphTopology + StageSubgraphDrawer; left sider = Controls + AgentMonitor; right sider = ChatView; sticky footer = FeedbackInput | Modify |
| `web/src/components/session/ZoneNode.tsx` | Evaluate: keep if it helps production-line zone grouping, otherwise delete | Modify or Delete |
| `web/tests/components/GraphTopology.test.tsx` | Assert backtrack edges NOT rendered; backtrack badge appears on origin stage | Modify |
| `web/tests/components/StageSubgraphDrawer.test.tsx` | New — renders only when active stage set; shows 5 nodes; cursor follows internal-node state | Create |
| `web/tests/components/StagePlanCard.test.tsx` | New — renders items with status chips | Create |
| `web/tests/components/ChatView.test.tsx` | Update — stage-grouped collapsibles; only active expanded; turns lazy-load on expand | Modify |
| `web/tests/components/CheckpointModal.test.tsx` | Update — shows PI advice when `pi_decisions` has a recent entry with confidence ≥ threshold | Modify |
| `web/tests/pages/SessionDetailPage.test.tsx` | Update — layout assertion matches §8.2 (production line top, drawer below when active, left AgentMonitor, right ChatView) | Modify |

---

## Task 1: Backend — `stage_plans` endpoint + subgraph-internal cursor

**Files:**
- Modify: `agentlabx/core/state.py` (+ `current_stage_internal_node`)
- Modify: `agentlabx/stages/subgraph.py` (write the field on each node)
- Modify: `agentlabx/core/graph_mapper.py` (expose in cursor)
- Modify: `agentlabx/server/routes/sessions.py` (+ stage_plans endpoint)
- Create: `tests/server/routes/test_stage_plans_endpoint.py`

- [ ] **Step 1: Write failing endpoint test**

Create `tests/server/routes/test_stage_plans_endpoint.py`:

```python
"""GET /api/sessions/{id}/stage_plans/{stage} returns StagePlan history."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from agentlabx.server.app import create_app


@pytest.fixture
def client(tmp_path):
    import os
    os.environ["AGENTLABX_STORAGE__DATABASE_URL"] = (
        f"sqlite+aiosqlite:///{tmp_path / 'sp.db'}"
    )
    os.environ["AGENTLABX_STORAGE__ARTIFACTS_PATH"] = str(tmp_path / "artifacts")
    app = create_app(use_mock_llm=True)
    with TestClient(app) as c:
        yield c
    os.environ.pop("AGENTLABX_STORAGE__DATABASE_URL", None)
    os.environ.pop("AGENTLABX_STORAGE__ARTIFACTS_PATH", None)


def test_stage_plans_endpoint_returns_empty_list_for_unstarted_session(client):
    r = client.post(
        "/api/sessions",
        json={"topic": "t", "user_id": "default", "config": {}},
    )
    assert r.status_code == 201
    sid = r.json()["session_id"]

    r2 = client.get(f"/api/sessions/{sid}/stage_plans/literature_review")
    assert r2.status_code == 200
    assert r2.json() == {"stage_name": "literature_review", "plans": []}


def test_stage_plans_endpoint_returns_404_on_unknown_session(client):
    r = client.get("/api/sessions/nonexistent/stage_plans/literature_review")
    assert r.status_code == 404
```

- [ ] **Step 2: Run — verify fail**

```
uv run pytest tests/server/routes/test_stage_plans_endpoint.py -v
```
Expected: FAIL (endpoint missing).

- [ ] **Step 3: Add the endpoint**

In `agentlabx/server/routes/sessions.py`, add:

```python
@router.get("/sessions/{session_id}/stage_plans/{stage_name}")
async def get_stage_plans(
    session_id: str,
    stage_name: str,
    context: AppContext = Depends(get_app_context),
) -> dict:
    """Return the versioned StagePlan history for a stage within a session.

    Response shape:
      {
        "stage_name": "literature_review",
        "plans": [  # oldest → newest
          {
            "items": [...],
            "rationale": "...",
            "hash_of_consumed_inputs": "..."
          },
          ...
        ]
      }
    """
    session = context.session_manager.get_session(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail=f"Session {session_id} not found")

    state = session.state or {}
    stage_plans = (state.get("stage_plans") or {}).get(stage_name, [])
    return {
        "stage_name": stage_name,
        "plans": stage_plans,
    }
```

Adapt `AppContext`, `session_manager.get_session`, and `Depends` to the existing codebase conventions (check another route for the pattern).

- [ ] **Step 4: Add `current_stage_internal_node` to state**

In `agentlabx/core/state.py`, inside `PipelineState`, add:

```python
    # Currently executing internal node of the active stage's subgraph
    # (e.g., "enter", "stage_plan", "work", "evaluate", "decide"). None when
    # the pipeline is between stages. Populated by the StageSubgraphBuilder's
    # nodes via state mutation; consumed by graph_mapper's cursor.
    current_stage_internal_node: str | None
```

Initialize to `None` in `create_initial_state`.

- [ ] **Step 5: Subgraph nodes write `current_stage_internal_node`**

In `agentlabx/stages/subgraph.py`, each of the 5 node functions (`enter_node`, `plan_node`, `work_node`, `evaluate_node`, `decide_node`) should write its own name to `state["current_stage_internal_node"]`:

```python
async def plan_node(s: _SubgraphState) -> dict[str, Any]:
    s["state"]["current_stage_internal_node"] = "stage_plan"
    # ... existing body
```

Apply the same pattern to each of the 5 nodes. The final `decide_node` should set it to `None` at the end (stage is exiting).

- [ ] **Step 6: Expose in graph_mapper cursor**

In `agentlabx/core/graph_mapper.py`, the cursor section in `build_topology`:

```python
    current_stage = state.get("current_stage")
    internal_node = state.get("current_stage_internal_node")
    cursor = None
    if current_stage:
        cursor = {
            "node_id": current_stage,
            "internal_node": internal_node,  # NEW
            "agent": None,  # set by most-recent agent_turn_started event in future
            "started_at": None,
        }
```

- [ ] **Step 7: Run endpoint + topology tests**

```
uv run pytest tests/server/routes/test_stage_plans_endpoint.py tests/core/test_graph_mapper.py -v
```
Expected: pass.

- [ ] **Step 8: Commit**

```bash
git add agentlabx/ tests/server/routes/test_stage_plans_endpoint.py
git commit -m "feat(api): stage_plans endpoint + subgraph-internal cursor (Plan 7D T1)"
```

---

## Task 2: Frontend hook — `useStagePlans`

**Files:**
- Create: `web/src/hooks/useStagePlans.ts`
- Modify: `web/src/hooks/useWebSocket.ts` (invalidate on `stage_started` event)
- Create: `web/tests/hooks/useStagePlans.test.tsx`

- [ ] **Step 1: Write failing test**

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
    const fetchSpy = vi.spyOn(globalThis, "fetch").mockResolvedValueOnce({
      ok: true,
      json: () => Promise.resolve(mockResponse),
    } as Response);

    const { result } = renderHook(
      () => useStagePlans("sess-1", "literature_review"),
      { wrapper: wrapper() },
    );

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(result.current.data).toEqual(mockResponse);
    expect(fetchSpy).toHaveBeenCalledWith(
      expect.stringContaining("/api/sessions/sess-1/stage_plans/literature_review"),
      expect.any(Object),
    );
  });
});
```

- [ ] **Step 2: Run — verify fail**

```
cd web && npm test -- useStagePlans
```

- [ ] **Step 3: Implement `useStagePlans`**

Create `web/src/hooks/useStagePlans.ts` matching the pattern of other hooks in `web/src/hooks/` (e.g., `useCost.ts`, `usePIHistory.ts`). Use `useQuery` keyed on `["stage-plans", sessionId, stageName]`, fetch `${API_BASE}/api/sessions/${sessionId}/stage_plans/${stageName}`, return the JSON response as-is.

- [ ] **Step 4: Wire cache invalidation**

In `web/src/hooks/useWebSocket.ts`, the event handler invalidates TanStack keys on `stage_started` / `stage_completed`. Add:

```typescript
case "stage_started":
case "stage_completed":
  queryClient.invalidateQueries({ queryKey: ["stage-plans", sessionId] });
  // ... (existing invalidations stay)
  break;
```

Use the partial-key form so any stage's `useStagePlans` rerenders.

- [ ] **Step 5: Run tests**

```
cd web && npm test -- useStagePlans useWebSocket
```

- [ ] **Step 6: Commit**

```bash
git add web/
git commit -m "feat(web): useStagePlans hook + WS invalidation (Plan 7D T2)"
```

---

## Task 3: `GraphTopology` — drop backtrack edges + cursor animation + backtrack badge

**Files:**
- Modify: `web/src/components/session/GraphTopology.tsx`
- Modify: `web/src/components/session/StageNode.tsx` (add backtrack badge)
- Modify: `web/tests/components/GraphTopology.test.tsx`

- [ ] **Step 1: Update GraphTopology test** to assert backtrack edges are NOT rendered

```typescript
it("does not render backtrack edges as visible lines", () => {
  const topology = {
    nodes: [
      { id: "lit", type: "stage", label: "Literature", zone: "discovery" },
      { id: "exp", type: "stage", label: "Experiment", zone: "implementation" },
    ],
    edges: [
      { from: "lit", to: "exp", kind: "sequential" },
      { from: "exp", to: "lit", kind: "backtrack", attempts: 2 },
    ],
    cursor: { node_id: "exp", internal_node: null },
    subgraphs: [],
  };
  const { container } = render(<GraphTopology topology={topology} />);
  // Forward edge present, backtrack edge absent from the rendered edges
  const edges = container.querySelectorAll(".react-flow__edge");
  expect(edges.length).toBe(1);
  // Backtrack origin node has a badge with attempts count
  expect(container.textContent).toContain("↩ 2");
});
```

- [ ] **Step 2: Update `GraphTopology` to filter backtrack edges + render cursor animation**

In `GraphTopology.tsx`, when mapping `topology.edges` to React Flow edges:

```typescript
const visibleEdges = topology.edges.filter((e) => e.kind !== "backtrack");
```

Keep the backtrack edges accessible separately so `StageNode` can render a badge when its `id` matches a backtrack origin. Pass `backtrackCounts: Record<string, number>` derived from the filtered-out edges into the node data:

```typescript
const backtrackCounts: Record<string, number> = {};
for (const e of topology.edges.filter((e) => e.kind === "backtrack")) {
  backtrackCounts[e.from] = (backtrackCounts[e.from] ?? 0) + (e.attempts ?? 1);
}
```

Merge into node `data` so `StageNode` can read it.

- [ ] **Step 3: `StageNode` renders backtrack badge**

Add to `StageNode.tsx`:

```typescript
{data.backtrackCount > 0 && (
  <Tag color="orange" style={{ fontSize: 10 }}>
    ↩ {data.backtrackCount}
  </Tag>
)}
```

Place alongside the existing status dot / iter tag / cost chip.

- [ ] **Step 4: Cursor animation on backtrack**

This is a best-effort UX polish. When the `cursor.node_id` jumps backward (previous render showed `experimentation`, new render shows `literature_review`), play a brief reverse-sweep animation. Simplest: add a CSS keyframe class `.cursor-reverse-sweep` that highlights the intermediate nodes briefly. Implementation: track the previous cursor in component state; if new cursor.node_id appears earlier in the sequence than previous, apply the class to nodes between previous and new for 600ms.

Skip this in T3 if it balloons — mark as TODO, it's polish. The badge is the load-bearing part.

- [ ] **Step 5: Run tests**

```
cd web && npm test -- GraphTopology StageNode
```

- [ ] **Step 6: Commit**

```bash
git add web/
git commit -m "feat(web): GraphTopology drops backtrack edges + StageNode badge (Plan 7D T3)"
```

---

## Task 4: `StageSubgraphDrawer` — active-stage internal-node view

**Files:**
- Create: `web/src/components/session/StageSubgraphDrawer.tsx`
- Create: `web/tests/components/StageSubgraphDrawer.test.tsx`

- [ ] **Step 1: Write failing test**

```typescript
import { describe, it, expect } from "vitest";
import { render } from "@testing-library/react";
import { StageSubgraphDrawer } from "../../src/components/session/StageSubgraphDrawer";

describe("StageSubgraphDrawer", () => {
  it("renders nothing when no active stage", () => {
    const { container } = render(<StageSubgraphDrawer activeStage={null} internalNode={null} />);
    expect(container.firstChild).toBeNull();
  });

  it("renders 5 internal nodes when a stage is active", () => {
    const { getByText } = render(
      <StageSubgraphDrawer activeStage="literature_review" internalNode="work" />,
    );
    ["ENTER", "PLAN", "WORK", "EVALUATE", "DECIDE"].forEach((label) => {
      expect(getByText(label)).toBeInTheDocument();
    });
  });

  it("highlights the internalNode currently active", () => {
    const { container } = render(
      <StageSubgraphDrawer activeStage="literature_review" internalNode="evaluate" />,
    );
    const highlighted = container.querySelector("[data-internal-node='evaluate'].active");
    expect(highlighted).not.toBeNull();
  });
});
```

- [ ] **Step 2: Run — verify fail**

- [ ] **Step 3: Implement `StageSubgraphDrawer`**

```typescript
import React from "react";
import { Card } from "antd";

interface Props {
  activeStage: string | null;
  internalNode: string | null;  // "enter" | "stage_plan" | "work" | "evaluate" | "decide" | null
}

const NODES = [
  { id: "enter", label: "ENTER" },
  { id: "stage_plan", label: "PLAN" },
  { id: "work", label: "WORK" },
  { id: "evaluate", label: "EVALUATE" },
  { id: "decide", label: "DECIDE" },
];

export function StageSubgraphDrawer({ activeStage, internalNode }: Props) {
  if (!activeStage) return null;

  return (
    <Card
      size="small"
      title={`Inside ${activeStage}`}
      style={{ marginTop: 12 }}
    >
      <div
        style={{
          display: "flex",
          gap: 24,
          alignItems: "center",
          justifyContent: "space-between",
          padding: "8px 16px",
        }}
      >
        {NODES.map((n, i) => (
          <React.Fragment key={n.id}>
            <div
              data-internal-node={n.id}
              className={internalNode === n.id ? "active" : ""}
              style={{
                padding: "6px 12px",
                borderRadius: 6,
                border: "1px solid",
                borderColor: internalNode === n.id ? "#1677ff" : "#d9d9d9",
                background: internalNode === n.id ? "#e6f4ff" : "transparent",
                fontWeight: internalNode === n.id ? 600 : 400,
                fontSize: 12,
              }}
            >
              {n.label}
            </div>
            {i < NODES.length - 1 && <span style={{ color: "#bfbfbf" }}>→</span>}
          </React.Fragment>
        ))}
      </div>
    </Card>
  );
}
```

Inline-styled component is acceptable here — it's ~40 lines and stylistically self-contained. A more elaborate React Flow rendering can come later if we need pan/zoom.

- [ ] **Step 4: Run tests**

```
cd web && npm test -- StageSubgraphDrawer
```

- [ ] **Step 5: Commit**

```bash
git add web/
git commit -m "feat(web): StageSubgraphDrawer renders active stage internal nodes (Plan 7D T4)"
```

---

## Task 5: `StagePlanCard` — render StagePlan items with status chips

**Files:**
- Create: `web/src/components/session/StagePlanCard.tsx`
- Create: `web/tests/components/StagePlanCard.test.tsx`

- [ ] **Step 1: Write failing test**

```typescript
import { describe, it, expect } from "vitest";
import { render } from "@testing-library/react";
import { StagePlanCard } from "../../src/components/session/StagePlanCard";

const samplePlan = {
  items: [
    { id: "i1", description: "Survey topic", status: "done", source: "prior", existing_artifact_ref: "lit_review[0]", edit_note: null, removed_reason: null },
    { id: "i2", description: "Gather papers", status: "todo", source: "contract", existing_artifact_ref: null, edit_note: null, removed_reason: null },
    { id: "i3", description: "Address feedback", status: "edit", source: "feedback", existing_artifact_ref: "lit_review[0]", edit_note: "add RL methods", removed_reason: null },
  ],
  rationale: "Literature review plan",
  hash_of_consumed_inputs: "abc",
};

describe("StagePlanCard", () => {
  it("renders each item with its status chip", () => {
    const { getByText } = render(<StagePlanCard plan={samplePlan} />);
    expect(getByText("Survey topic")).toBeInTheDocument();
    expect(getByText("Gather papers")).toBeInTheDocument();
    expect(getByText("Address feedback")).toBeInTheDocument();
    expect(getByText("done")).toBeInTheDocument();
    expect(getByText("todo")).toBeInTheDocument();
    expect(getByText("edit")).toBeInTheDocument();
  });

  it("shows the rationale", () => {
    const { getByText } = render(<StagePlanCard plan={samplePlan} />);
    expect(getByText(/Literature review plan/)).toBeInTheDocument();
  });
});
```

- [ ] **Step 2: Implement**

```typescript
import { Card, Tag, Typography } from "antd";

interface StagePlanItem {
  id: string;
  description: string;
  status: "done" | "edit" | "todo" | "removed";
  source: string;
  existing_artifact_ref: string | null;
  edit_note: string | null;
  removed_reason: string | null;
}

interface StagePlan {
  items: StagePlanItem[];
  rationale: string;
  hash_of_consumed_inputs: string;
}

const STATUS_COLORS: Record<StagePlanItem["status"], string> = {
  done: "green",
  edit: "orange",
  todo: "blue",
  removed: "default",
};

export function StagePlanCard({ plan }: { plan: StagePlan }) {
  return (
    <Card size="small" title="Stage Plan">
      <Typography.Paragraph type="secondary" style={{ fontSize: 12 }}>
        {plan.rationale}
      </Typography.Paragraph>
      <ul style={{ listStyle: "none", padding: 0, margin: 0 }}>
        {plan.items.map((item) => (
          <li key={item.id} style={{ padding: "4px 0" }}>
            <Tag color={STATUS_COLORS[item.status]}>{item.status}</Tag>
            <span>{item.description}</span>
            {item.edit_note && (
              <Typography.Text type="secondary" style={{ fontSize: 11, marginLeft: 8 }}>
                ({item.edit_note})
              </Typography.Text>
            )}
          </li>
        ))}
      </ul>
    </Card>
  );
}
```

- [ ] **Step 3: Run tests + commit**

```bash
cd web && npm test -- StagePlanCard
cd .. && git add web/ && git commit -m "feat(web): StagePlanCard renders plan items with status chips (Plan 7D T5)"
```

---

## Task 6: `ChatView` — stage-grouped, collapsible, lazy-loaded

**Files:**
- Modify: `web/src/components/session/ChatView.tsx`
- Modify: `web/src/components/session/StageGroup.tsx` (may already be lazy-load-shaped from 6f5bfa2)
- Modify: `web/tests/components/ChatView.test.tsx`

- [ ] **Step 1: Audit current state**

The WIP at `6f5bfa2` already reshaped ChatView toward stage-grouping; use `git show 6f5bfa2 -- web/src/components/session/ChatView.tsx web/src/components/session/StageGroup.tsx` to see the existing work. If it's already close, this task becomes a refinement rather than a rewrite.

- [ ] **Step 2: Update ChatView test**

Assert:
- Each stage renders as a collapsible `Collapse.Panel` (Ant Design).
- Only the `activeStage` section is open by default.
- Non-active sections don't invoke `useAgentHistory` until expanded — spy on the query key.

```typescript
it("lazy-loads agent history per stage — non-active stages do not fetch", () => {
  const fetchSpy = vi.spyOn(globalThis, "fetch");
  render(<ChatView sessionId="s1" activeStage="literature_review" />);
  // literature_review fetch should have fired; experimentation should not
  expect(fetchSpy).toHaveBeenCalledWith(
    expect.stringContaining("agents") && expect.stringContaining("literature_review"),
    expect.any(Object),
  );
  expect(fetchSpy).not.toHaveBeenCalledWith(
    expect.stringContaining("experimentation"),
    expect.any(Object),
  );
});
```

- [ ] **Step 3: Implement lazy-load**

Refactor `ChatView.tsx` so each stage's history query is only triggered when the `Collapse.Panel` is expanded. Use Ant Design's `Collapse` with `destroyInactivePanel={false}` so expanding keeps turns rendered but initial-collapsed panels don't mount the history hook.

Simplest approach: child `StageGroup` component that calls `useAgentHistory` only when `isExpanded === true`. Parent `ChatView` tracks expanded state and passes down.

- [ ] **Step 4: Tests + commit**

```bash
cd web && npm test -- ChatView StageGroup
cd .. && git add web/ && git commit -m "feat(web): ChatView stage-grouped + lazy-load turns (Plan 7D T6)"
```

---

## Task 7: `CheckpointModal` consumes `needs_approval` + surfaces PI advice

**Files:**
- Modify: `web/src/components/session/CheckpointModal.tsx`
- Modify: `web/tests/components/CheckpointModal.test.tsx`
- Modify: `web/src/hooks/usePIHistory.ts` (if needed — may already return latest entry)

- [ ] **Step 1: Update CheckpointModal test**

Assert:
- When session state has `needs_approval: true`, the modal is open.
- When `pi_decisions` has a recent entry with matching checkpoint, the modal shows the PI reasoning + confidence.
- When the checkpoint control is `approve`, modal shows Yes/No buttons.
- When the checkpoint control is `edit`, modal shows an edit form (new — not in prior CheckpointModal).

- [ ] **Step 2: Update CheckpointModal**

Read the latest `pi_decisions` entry via `usePIHistory`. When the checkpoint reason mentions `"PI advisor"`, render the advice prominently at the top of the modal. Distinguish `approve` vs `edit` stage controls via a new prop or by reading session preferences.

```typescript
interface CheckpointModalProps {
  sessionId: string;
  open: boolean;
  // ... existing
  needsApproval: boolean;
  lastPIAdvice?: {
    checkpoint: string;
    next_stage: string;
    reasoning: string;
    confidence: number;
  };
}

export function CheckpointModal(props: CheckpointModalProps) {
  const { lastPIAdvice } = props;
  return (
    <Modal open={props.open} /* ... */>
      {lastPIAdvice && (
        <Alert
          type="info"
          message={
            <span>
              PI advisor recommends <strong>{lastPIAdvice.next_stage}</strong>
              {" "}({(lastPIAdvice.confidence * 100).toFixed(0)}% confidence)
            </span>
          }
          description={lastPIAdvice.reasoning}
          style={{ marginBottom: 12 }}
        />
      )}
      {/* ... existing yes/no/edit UX per stage control */}
    </Modal>
  );
}
```

- [ ] **Step 3: Wire SessionDetailPage to pass props**

In `SessionDetailPage.tsx`, pass `needsApproval={session.needs_approval}` and `lastPIAdvice={piHistory?.[piHistory.length - 1]}` down.

- [ ] **Step 4: Tests + commit**

```bash
cd web && npm test -- CheckpointModal
cd .. && git add web/ && git commit -m "feat(web): CheckpointModal surfaces PI advice + approve/edit UX (Plan 7D T7)"
```

---

## Task 8: `SessionDetailPage` layout + reconcile 6f5bfa2 WIP + delete AgentHistoryCard

**Files:**
- Modify: `web/src/pages/SessionDetailPage.tsx`
- Modify: `web/src/components/session/AgentMonitor.tsx`
- Delete: `web/src/components/session/AgentHistoryCard.tsx` + test
- Evaluate: `web/src/components/session/ZoneNode.tsx`, `AgentTurn.tsx` (duplicate of `AgentTurnBubble.tsx`?), `ToolCallInline.tsx` (duplicate of `ToolCallAnnotation.tsx`?)
- Modify: `web/tests/pages/SessionDetailPage.test.tsx`

- [ ] **Step 1: Update SessionDetailPage layout per §8.2**

Layout shape:

```
┌────────────────────────────────────────────────────┐
│  Header: topic · session_id · status badge         │
├────────────────────────────────────────────────────┤
│  GraphTopology (production line, ~280px tall)      │
│  StageSubgraphDrawer (only when active, ~100px)    │
├────────┬───────────────────────────┬───────────────┤
│ Left   │ Center tabs:              │ Right sider   │
│ sider  │ • Artifacts               │ ChatView      │
│ Global │ • Experiments             │ (stage-       │
│ Ctrls  │ • Cost                    │  grouped)     │
│ +      │                           │               │
│ Agent  │                           │ Hypotheses    │
│ Monit  │                           │ PIDecisionLog │
│ or     │                           │ Cost compact  │
├────────┴───────────────────────────┴───────────────┤
│  FeedbackInput (sticky)                            │
└────────────────────────────────────────────────────┘
```

- [ ] **Step 2: Remove AgentHistoryCard composition from AgentMonitor**

In `AgentMonitor.tsx`, drop the `<AgentHistoryCard>` render. Replace with `<StagePlanCard plan={latestPlanForAgentStage} />` when the monitored agent belongs to the active stage.

- [ ] **Step 3: Delete obsolete components**

```bash
rm web/src/components/session/AgentHistoryCard.tsx
rm web/tests/components/AgentHistoryCard.test.tsx  # if exists
```

Check `AgentTurn.tsx` vs `AgentTurnBubble.tsx` and `ToolCallInline.tsx` vs `ToolCallAnnotation.tsx` — if duplicates, pick one canonical and delete the other.

- [ ] **Step 4: Evaluate ZoneNode**

If the new `GraphTopology` with React Flow's native subgraph grouping works, `ZoneNode.tsx` may no longer be needed. Delete if unused. If still useful for zone borders, keep.

- [ ] **Step 5: Update SessionDetailPage test**

Assert:
- GraphTopology + StageSubgraphDrawer are in the top section.
- Left sider contains `ControlBar` + `AgentMonitor`.
- Right sider contains `ChatView` (stage-grouped, see T6).
- Sticky footer has `FeedbackInput`.

- [ ] **Step 6: Tests + commit**

```bash
cd web && npm test
cd .. && git add -A web/ && git commit -m "feat(web): SessionDetailPage layout + reconcile WIP + drop AgentHistoryCard (Plan 7D T8)"
```

---

## Self-review checklist

- [ ] **Spec coverage:**
  - §8.2 graph-hierarchy principle — T3 (production line), T4 (subgraph drawer), T8 (recursive layout in SessionDetailPage)
  - §8.2 production-line graph — T3 (drops backtrack edges, adds badge)
  - §8.2 StageSubgraphDrawer with nested attachments — T4 (5-node drawer). Nested `lab_meeting` overlay deferred to a sub-follow-up (LabMeetingOverlay file listed in structure but not in a task; the lab_meeting subgraph body itself is also future work).
  - §8.3 component list updates — T5 (StagePlanCard), T8 (drop AgentHistoryCard), T7 (CheckpointModal PI advice)
  - Backend: §7.1 stage_plans endpoint — T1
  - PI advice surfacing — T7 (CheckpointModal)

- [ ] **No placeholders.** Every task has concrete code + commands. Lab meeting overlay is noted as future follow-up, not a silent gap.

- [ ] **Type consistency:** `StagePlan`, `StagePlanItem`, `StagePlanStatus` (web must mirror the backend shape — add types in `web/src/types/` if they don't exist).

- [ ] **Pre-production principle:** delete obsolete components (AgentHistoryCard) outright; don't retain as unused.

---

## Execution

Ship 7D after 7C validation. Subagent-driven recommended.

**Follow-ups not in 7D:**
- `LabMeetingOverlay` + full invocable-subgraph rendering — needs lab_meeting's subgraph body first
- Cursor reverse-sweep animation on backtrack — UX polish, T3 marks as optional
- Pixel-art `lab_scene` conversation renderer — reserved prop, future creative plan
- `TestFullSessionLifecycle` E2E timeout investigation — from 7C follow-up, orthogonal to 7D
