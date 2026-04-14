# Plan 7E: Post-Ship Fixes + Stage Migrations + UX Polish

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Close gaps found in the Plan 7 end-to-end review, migrate the remaining 7 stages to plan-driven hooks, and apply UX polish to the 7D surfaces. Organized into three parts with different priorities.

**Architecture:** No architectural changes — Plan 7E is a cleanup + feature-completion pass over the shipped Plan 7A/B/C/D surface. Part A closes real bugs in the shipped system (internal-node cursor never moves; HITL pause announced but not enforced; subgraph extraction fails silently). Part B takes the `literature_review` migration template from Plan 7B T6 and applies it to the remaining 7 stages — each stage's `build_plan` itemizes its concrete tasks so the StagePlan primitive becomes authoritative instead of decorative. Part C ships UX polish deferred during Plan 7D: checkpoint mode forwarding, accessibility, cursor backtrack animation, endpoint validation, session-keyed panel state.

**Tech Stack:** Python 3.11+, React 19, TypeScript 5.5, LangGraph, Pydantic v2, pytest-asyncio, Vitest. No new dependencies.

**Pre-production principle:** AgentLabX has not shipped a stable release. Break and update tests freely; no backwards-compat scaffolding.

**Spec-alignment rule (active):** if any task's implementation would diverge from the platform spec, flag it before shipping — update the spec with the approved reality, don't leave silent drift. See `feedback_spec_alignment.md` in user memory.

**Companion spec:** `docs/superpowers/specs/2026-04-12-agentlabx-platform-design.md` §3.2.1 (stage subgraph), §3.2.2 (StagePlan), §3.3 (transition handler), §3.8 (HITL), §8.2 (Session Detail layout).

**Plan 7 tags:** `plan7a-complete` (77d2e84), `plan7b-complete` (7c1b18a), `plan7c-complete` (4391b76), `plan7d-complete` (896322c). Plan 7E starts from `plan7d-complete`.

**Out of scope:**
- `lab_meeting` subgraph body implementation (multi-agent discussion logic) — separate plan.
- `lab_scene` pixel-art conversation renderer — reserved `ChatView.mode` prop; creative polish plan.
- Mobile layout — desktop-first.

---

## Task organisation

| Part | Priority | What | Count |
|---|---|---|---|
| A | Critical — real bugs in shipped features | Cursor event streaming (M1); HITL pause enforcement (CC1); subgraph extraction logging (M3) | 3 tasks |
| B | Feature completion | Migrate remaining 7 stages to plan-driven hooks using T6's template | 3 tasks (grouped by zone) |
| C | UX polish | Stage control mode forwarding (M2); reverse-sweep backtrack animation (L2); accessibility (L1); endpoint validation (L3); session-keyed panel state (L4) | 5 tasks |

**Dispatch order:** Part A before Part B (stage migrations benefit from cursor event streaming being live). Part C can run in parallel with either.

---

## Part A: Critical fixes

### Task A1: Cursor event streaming — `stage_internal_node_changed`

**Problem:** Each subgraph node writes `state["current_stage_internal_node"]` via in-place mutation. LangGraph discards in-place mutations on subgraph input state; only node-return dicts apply. Even if propagation were added, the subgraph runs atomically from the parent's perspective — by the time `subgraph_result` arrives, the cursor has already reached `"decide"`. Result: the inner subgraph drawer cursor ring in Plan 7D's Figure 2 never moves in production.

**Fix:** emit a `stage_internal_node_changed` WebSocket event from each of the 5 subgraph node functions. Frontend invalidates `["graph"]` on the event, triggering a re-fetch of `/graph` whose mapper then picks up the latest `current_stage_internal_node`. Also: have each subgraph node return a partial state update with the new node name so outer state reflects the live value (LangGraph's merge applies the return).

**Files:**
- Modify: `agentlabx/stages/subgraph.py` — emit event + return partial state per node
- Modify: `agentlabx/core/event_types.py` — add `STAGE_INTERNAL_NODE_CHANGED` constant
- Modify: `agentlabx/server/events.py` — re-export
- Modify: `agentlabx/stages/runner.py` — propagate `current_stage_internal_node` from subgraph result (mirrors T7's stage_plans propagation fix)
- Modify: `web/src/hooks/useWebSocket.ts` — map the new event to `["graph", sid]` invalidation
- Create: `tests/stages/test_subgraph_internal_cursor.py` — verify events fire + outer state updates

- [ ] **Step 1: Add event constant**

In `agentlabx/core/event_types.py`:

```python
class EventTypes:
    # ... existing
    STAGE_INTERNAL_NODE_CHANGED = "stage_internal_node_changed"
```

Re-export via `agentlabx/server/events.py` (check existing pattern).

- [ ] **Step 2: Write failing test**

Create `tests/stages/test_subgraph_internal_cursor.py`:

```python
"""Subgraph nodes emit stage_internal_node_changed events + update outer state."""
from __future__ import annotations

import pytest

from agentlabx.core.event_types import EventTypes
from agentlabx.core.events import Event, EventBus
from agentlabx.core.state import create_initial_state
from agentlabx.stages.base import BaseStage, StageContext, StageResult
from agentlabx.stages.subgraph import StageSubgraphBuilder


class _EchoStage(BaseStage):
    name = "echo"
    description = "echo"
    required_agents: list[str] = []
    required_tools: list[str] = []
    zone = "discovery"

    async def run(self, state, context):
        return StageResult(output={}, status="done", reason="ok")


@pytest.mark.asyncio
async def test_subgraph_emits_internal_node_changed_events():
    events: list[Event] = []
    bus = EventBus()
    bus.subscribe("*", lambda e: events.append(e) or None)

    compiled = StageSubgraphBuilder().compile(_EchoStage())
    state = create_initial_state(session_id="s1", user_id="u1", research_topic="t")
    state["current_stage"] = "echo"

    await compiled.ainvoke(
        {
            "state": state,
            "context": StageContext(settings={}, event_bus=bus, registry=None),
        },
        config={"configurable": {"thread_id": "t1"}},
    )

    # Expect one event per internal node (5 nodes: enter, stage_plan, work, evaluate, decide)
    internal_events = [
        e for e in events if e.type == EventTypes.STAGE_INTERNAL_NODE_CHANGED
    ]
    internal_nodes = [e.data["internal_node"] for e in internal_events]
    assert "enter" in internal_nodes
    assert "stage_plan" in internal_nodes
    assert "work" in internal_nodes
    assert "evaluate" in internal_nodes
    assert "decide" in internal_nodes


@pytest.mark.asyncio
async def test_subgraph_nodes_return_current_internal_node_in_update():
    """Returns propagate to outer state (LangGraph applies node return dicts)."""
    compiled = StageSubgraphBuilder().compile(_EchoStage())
    state = create_initial_state(session_id="s1", user_id="u1", research_topic="t")
    state["current_stage"] = "echo"

    result = await compiled.ainvoke(
        {
            "state": state,
            "context": StageContext(settings={}, event_bus=None, registry=None),
        },
        config={"configurable": {"thread_id": "t1"}},
    )

    # After subgraph exits, the outer state's current_stage_internal_node
    # reflects the FINAL node to write (decide). Runner will then clear to None.
    assert result["state"]["current_stage_internal_node"] == "decide"
```

- [ ] **Step 3: Update `subgraph.py`**

Each node function:
1. Writes `s["state"]["current_stage_internal_node"] = "<name>"` as before (in-place for inner tracking)
2. ADDS: emit event via `s["context"].event_bus` if available
3. ADDS: returns `{"current_stage_internal_node": "<name>"}` as part of the update dict (so LangGraph applies it to the subgraph state)

Pattern for each node:

```python
async def plan_node(s: _SubgraphState) -> dict[str, Any]:
    s["state"]["current_stage_internal_node"] = "stage_plan"
    bus = s.get("context") and s["context"].event_bus
    if bus is not None:
        from agentlabx.core.event_types import EventTypes
        from agentlabx.core.events import Event
        await bus.emit(
            Event(
                type=EventTypes.STAGE_INTERNAL_NODE_CHANGED,
                data={
                    "internal_node": "stage_plan",
                    "stage": s["state"].get("current_stage"),
                    "session_id": s["state"].get("session_id"),
                },
                source=s["state"].get("current_stage", "subgraph"),
            )
        )
    # ... existing body (build plan, write to state["stage_plans"], etc.)
    # return dict MUST include the internal-node update so outer state sees it
    return {..., "current_stage_internal_node": "stage_plan"}
```

Apply this pattern to all 5 node functions (`enter_node`, `plan_node`, `work_node`, `evaluate_node`, `decide_node`). The decide_node's return should include `"current_stage_internal_node": "decide"` (runner clears to None on stage exit).

Note: event emit is `async` only for `plan_node` and `work_node` which are already `async def`. `enter_node`, `evaluate_node`, `decide_node` are synchronous — you'll need either (a) make them async, or (b) use a sync `bus.emit_sync` variant if one exists. Check `EventBus` API; the existing subscribers are likely async-compatible. Safest: make all 5 nodes `async def`.

- [ ] **Step 4: Update `runner.py` to propagate the live value**

Mirror the `stage_plans` propagation fix. After the existing `subgraph_result = await self._compiled_subgraph.ainvoke(...)`:

```python
        # Propagate the internal-node cursor (same pattern as stage_plans).
        updated_internal_node = subgraph_result.get("state", {}).get(
            "current_stage_internal_node"
        )
        if updated_internal_node is not None:
            update["current_stage_internal_node"] = updated_internal_node
```

Place this alongside the `stage_plans` propagation at lines 93-95. Then the existing `update["current_stage_internal_node"] = None` at line 186 still runs (clears on stage exit) — which is correct.

Actually: the line-186 clear happens AFTER this propagation, so the final outer-state value will be `None` (since runner's lines overwrite). But by that point the subgraph has fully exited, the `/graph` endpoint won't show intermediate values anyway — only the WS events gave the frontend live updates during execution.

The RIGHT behaviour is:
- While subgraph runs: WS events push intermediate node names to frontend → /graph invalidation → cursor ring moves.
- Subgraph exits: `current_stage_internal_node` cleared to `None` in outer state.

So the T7-style propagation isn't strictly needed for the cursor UX (events carry the signal). BUT it is useful for `/graph` endpoint consumers that poll rather than stream. Keep the propagation.

- [ ] **Step 5: Wire WS invalidation in `useWebSocket.ts`**

Add to the `INVALIDATE` table:

```typescript
stage_internal_node_changed: (sid) => [["graph", sid]],
```

Now every internal-node transition triggers a `/graph` refetch. The cursor ring follows.

- [ ] **Step 6: Run tests**

```bash
uv run pytest tests/stages/test_subgraph_internal_cursor.py tests/stages/test_subgraph.py tests/stages/test_runner.py -v
cd web && npm test -- useWebSocket
```

All pass. Then full sweep:

```bash
uv run pytest tests/ -x -q --deselect tests/integration/test_mock_llm_event_stream.py --deselect tests/agents/test_pi_agent_real_llm.py::TestPIAgentRealLLM::test_real_api_call
cd web && npm test
```

- [ ] **Step 7: Commit**

```bash
git add agentlabx/stages/subgraph.py agentlabx/stages/runner.py agentlabx/core/event_types.py agentlabx/server/events.py web/src/hooks/useWebSocket.ts tests/stages/test_subgraph_internal_cursor.py [updated tests]
git commit -m "feat(subgraph): emit stage_internal_node_changed events + propagate cursor (Plan 7E A1)"
```

---

### Task A2: HITL pause enforcement — honour `decision.needs_approval`

**Problem:** `transition_node` in `agentlabx/core/pipeline.py` emits `checkpoint_reached` when `decision.needs_approval === true`, but returns the state update anyway. The graph routes forward before the user sees the modal. `CheckpointModal.tsx` currently acknowledges this: "Backend does not actually pause on checkpoints yet" (observational-only). The `paused_event` mechanism exists (used by the pause/resume buttons) but isn't triggered by needs_approval.

**Fix:** when `decision.needs_approval === true`, `transition_node` clears `paused_event` before returning. The StageRunner's existing `await self.context.paused_event.wait()` at the start of each stage then blocks the next stage until the user resumes via API (`POST /api/sessions/{id}/resume`). Additionally: a new `POST /api/sessions/{id}/checkpoint/approve` endpoint handles the modal's approval action (resumes + optionally clears human_override).

**Files:**
- Modify: `agentlabx/core/pipeline.py` — clear `paused_event` on needs_approval
- Modify: `agentlabx/server/routes/sessions.py` — add `/checkpoint/approve` endpoint (or fold into existing `/resume`)
- Modify: `agentlabx/stages/runner.py` — verify `paused_event.wait()` is the first thing it awaits (it already is; no change expected)
- Modify: `web/src/components/session/CheckpointModal.tsx` — update the disclaimer comment; wire approve/reject buttons to the new endpoint
- Create: `tests/server/routes/test_checkpoint_approval.py`

- [ ] **Step 1: Write failing test**

Create `tests/server/routes/test_checkpoint_approval.py`:

```python
"""HITL pause: needs_approval transition clears paused_event; /checkpoint/approve resumes."""
from __future__ import annotations

import os
import pytest
from fastapi.testclient import TestClient

from agentlabx.server.app import create_app


@pytest.fixture
def client(tmp_path):
    os.environ["AGENTLABX_STORAGE__DATABASE_URL"] = (
        f"sqlite+aiosqlite:///{tmp_path / 'ckpt.db'}"
    )
    os.environ["AGENTLABX_STORAGE__ARTIFACTS_PATH"] = str(tmp_path / "artifacts")
    app = create_app(use_mock_llm=True)
    with TestClient(app) as c:
        yield c


def test_checkpoint_approve_endpoint_resumes_paused_session(client):
    # Create a session and pause it via the pause endpoint (simulates a
    # needs_approval pause).
    r = client.post("/api/sessions", json={"topic": "t", "user_id": "default"})
    sid = r.json()["session_id"]

    client.post(f"/api/sessions/{sid}/pause")
    sess = client.get(f"/api/sessions/{sid}").json()
    # Status or paused flag should reflect the pause (depends on existing API)

    r2 = client.post(
        f"/api/sessions/{sid}/checkpoint/approve",
        json={"action": "approve"},
    )
    assert r2.status_code == 200
    # After approve, session should be unpaused


def test_checkpoint_approve_with_redirect(client):
    r = client.post("/api/sessions", json={"topic": "t", "user_id": "default"})
    sid = r.json()["session_id"]

    r2 = client.post(
        f"/api/sessions/{sid}/checkpoint/approve",
        json={"action": "redirect", "redirect_target": "plan_formulation"},
    )
    assert r2.status_code == 200
    # human_override should be set; next run picks it up in TransitionHandler
```

The exact assertion shape depends on the existing session API. Read `tests/server/routes/test_session_lifecycle.py` (or similar) for the pattern.

- [ ] **Step 2: Clear `paused_event` in `transition_node`**

In `agentlabx/core/pipeline.py`, find the existing `checkpoint_reached` emission (added in 7C T7). Just after the emit:

```python
            if decision.needs_approval:
                # Emit checkpoint_reached (existing line)
                await event_bus.emit(...)

                # NEW: pause the pipeline so StageRunner blocks before the next
                # stage until the user approves/rejects via /checkpoint/approve.
                if stage_context and stage_context.paused_event:
                    stage_context.paused_event.clear()
```

The `paused_event` was injected into `stage_context` by `PipelineExecutor.start_session`. Verify its availability in `transition_node`'s closure — it's already in scope via the builder's `stage_context` argument.

- [ ] **Step 3: Add `/checkpoint/approve` endpoint**

In `agentlabx/server/routes/sessions.py`:

```python
from pydantic import BaseModel


class CheckpointApproveRequest(BaseModel):
    action: Literal["approve", "reject", "redirect", "edit"]
    redirect_target: str | None = None
    edited_output: dict | None = None
    reason: str | None = None


@router.post("/sessions/{session_id}/checkpoint/approve")
async def approve_checkpoint(
    session_id: str,
    body: CheckpointApproveRequest,
    context: AppContext = Depends(get_app_context),
) -> dict:
    """Resume a session paused at a HITL checkpoint.

    Actions:
      approve      — unpause; let the pipeline route per decision.next_stage
      reject       — unpause but set human_override to the current stage (retry it)
      redirect     — unpause + set human_override to redirect_target
      edit         — unpause + apply edited_output to state (deferred impl)

    See spec §3.8 HITL execution mode.
    """
    session = context.session_manager.get_session(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail=f"Session {session_id} not found")

    # Apply action-specific state mutations BEFORE unpausing so the resumed
    # runner sees the updated state.
    if body.action == "redirect" and body.redirect_target:
        # human_override is consumed by TransitionHandler priority 1 (see 7A spec).
        # For now we can't set state directly through this path — the executor
        # needs an API for in-flight state patches. Simplest: emit a
        # human_override event that the session manager picks up.
        # If that mechanism doesn't exist yet, scope-guard: only support approve
        # and reject in this commit; add redirect/edit in a follow-up.
        raise HTTPException(status_code=501, detail="redirect/edit actions deferred")

    # Signal the paused event via the executor's paused_event for this session.
    executor = context.executor
    executor.resume_session(session_id)  # existing method from Plan 2/4

    return {"status": "resumed", "action": body.action}
```

Simplify the first-pass scope: support `approve` + `reject` (no state mutation needed — rejection simply resumes with whatever next_stage the handler already picked). `redirect` and `edit` can raise 501 with a pointer to a follow-up issue.

Check existing executor API — there should already be a `resume_session` method used by `POST /api/sessions/{id}/resume`. If the new endpoint is functionally identical to `/resume` for the approve case, consider just using the existing one and making `/checkpoint/approve` a thin wrapper or alias.

- [ ] **Step 4: Update `CheckpointModal.tsx`**

- Remove the "observational-only" comment at lines 16-23.
- Wire the Approve / Reject buttons to `POST /api/sessions/{id}/checkpoint/approve` with the appropriate action.
- Show a spinner during the request; close the modal on success.

- [ ] **Step 5: Run tests + commit**

```bash
uv run pytest tests/server/routes/test_checkpoint_approval.py tests/core/test_pipeline.py -v
cd web && npm test -- CheckpointModal
cd .. && git add -A && git commit -m "feat(hitl): pause on needs_approval + /checkpoint/approve endpoint (Plan 7E A2)"
```

---

### Task A3: Subgraph extraction — log warnings on failure

**Problem:** `agentlabx/core/graph_mapper.py` wraps subgraph extraction in `try/except Exception: pass`. A user-visible empty drawer could mean "not active" or "extraction crashed" — the frontend can't tell.

**Fix:** replace the bare `except Exception: pass` with a logged warning. Surface an `error` field on the subgraph entry so the UI can render a fallback ("Subgraph unavailable") instead of silently absent.

**Files:**
- Modify: `agentlabx/core/graph_mapper.py`
- Modify: `web/src/components/session/StageSubgraphDrawer.tsx` — render error message when `subgraph.error` is set
- Create: `tests/core/test_graph_mapper_error.py`

- [ ] **Step 1: Write failing test**

```python
def test_graph_mapper_surfaces_subgraph_extraction_error(registry, monkeypatch):
    """When subgraph extraction raises, entry has an 'error' field + logs a warning."""
    import logging
    from unittest.mock import patch

    # Force StageSubgraphBuilder.compile to raise
    def raising_compile(self, stage):
        raise RuntimeError("synthetic compile failure")

    monkeypatch.setattr(
        "agentlabx.stages.subgraph.StageSubgraphBuilder.compile", raising_compile
    )

    state = create_initial_state(session_id="s1", user_id="u1", research_topic="t")
    state["current_stage"] = "literature_review"

    with caplog.at_level(logging.WARNING):
        topology = build_topology(compiled_graph_fixture, state, registry=registry)

    active_subgraph = next(
        (s for s in topology["subgraphs"] if s["id"] == "literature_review"),
        None,
    )
    assert active_subgraph is not None
    assert active_subgraph.get("error") is not None
    assert "synthetic compile failure" in active_subgraph["error"]
    assert "subgraph extraction failed" in caplog.text.lower()
```

- [ ] **Step 2: Update extraction block**

In `graph_mapper.py`:

```python
import logging
logger = logging.getLogger(__name__)

# Inside the extraction try/except:
try:
    # ... existing extraction
    subgraphs.append({
        "id": current_stage,
        "kind": "stage_subgraph",
        # ... nodes, edges
    })
except Exception as exc:
    logger.warning(
        "Subgraph extraction failed for stage %s: %s",
        current_stage, exc, exc_info=True,
    )
    subgraphs.append({
        "id": current_stage,
        "kind": "stage_subgraph",
        "label": current_stage,
        "nodes": [],
        "edges": [],
        "error": f"Subgraph extraction failed: {exc}",
    })
```

- [ ] **Step 3: Frontend — show error state**

In `StageSubgraphDrawer.tsx`, when `subgraph.error` is set:

```typescript
if (subgraph.error) {
  return (
    <Card size="small" title={`Inside ${subgraph.label}`} style={{ marginTop: 12 }}>
      <Alert type="warning" message="Subgraph unavailable" description={subgraph.error} />
    </Card>
  );
}
```

- [ ] **Step 4: Test + commit**

```bash
uv run pytest tests/core/test_graph_mapper_error.py -v
cd web && npm test -- StageSubgraphDrawer
cd .. && git add -A && git commit -m "feat(graph): log + surface subgraph extraction errors (Plan 7E A3)"
```

---

## Part B: Stage migrations

Each migration follows the same template as Plan 7B T6 (literature_review):

1. Read the stage's current `.run()` body.
2. Add a `build_plan(state, *, feedback)` override that itemises the work.
3. Keep `.run()` intact for `execute_plan`'s default delegation (full per-item dispatch is a later plan).
4. Add unit test that asserts `build_plan` produces the expected items.

**Prerequisite:** Task A1 must land first so the internal-node cursor actually moves for migrated stages (otherwise the inner drawer is static for them too).

### Task B1: Discovery zone — migrate `plan_formulation`

Only 1 stage (literature_review already migrated in 7B T6).

**Files:**
- Modify: `agentlabx/stages/plan_formulation.py` — add `build_plan` override
- Create: `tests/stages/test_plan_formulation_subgraph.py`

- [ ] **Step 1: Read current stage**

```bash
cat agentlabx/stages/plan_formulation.py
```

The stage currently implements `.run()` that asks the postdoc + PhD student to produce a ResearchPlan with goals/methodology/hypotheses.

- [ ] **Step 2: Write failing test**

Template from `tests/stages/test_literature_review_subgraph.py`:

```python
"""plan_formulation runs via subgraph and produces a StagePlan."""
import pytest

from agentlabx.core.state import create_initial_state
from agentlabx.stages.plan_formulation import PlanFormulationStage


def test_plan_formulation_build_plan_itemises_research_plan_tasks():
    stage = PlanFormulationStage()
    state = create_initial_state(
        session_id="s1", user_id="u1", research_topic="test topic"
    )
    plan = stage.build_plan(state, feedback=None)
    # Expect at least: goals, methodology, hypotheses items
    assert len(plan["items"]) >= 3
    ids = {i["id"] for i in plan["items"]}
    assert "plan:goals" in ids
    assert "plan:methodology" in ids
    assert "plan:hypotheses" in ids


def test_plan_formulation_build_plan_adds_feedback_item_when_feedback_given():
    stage = PlanFormulationStage()
    state = create_initial_state(
        session_id="s1", user_id="u1", research_topic="t"
    )
    plan = stage.build_plan(state, feedback="revise methodology for bigger scale")
    feedback_items = [i for i in plan["items"] if i["source"] == "feedback"]
    assert len(feedback_items) >= 1
    assert "revise methodology" in feedback_items[0]["description"]


def test_plan_formulation_build_plan_marks_goals_done_when_prior_plan_exists():
    stage = PlanFormulationStage()
    state = create_initial_state(
        session_id="s1", user_id="u1", research_topic="t"
    )
    from agentlabx.core.state import ResearchPlan

    state["plan"] = [
        ResearchPlan(
            goals=["g1"], methodology="m", hypotheses=["h1"],
            full_text="prior plan",
        )
    ]
    plan = stage.build_plan(state, feedback=None)
    goals_item = next(i for i in plan["items"] if i["id"] == "plan:goals")
    assert goals_item["status"] == "done"
```

- [ ] **Step 3: Implement `build_plan`**

Add to `PlanFormulationStage`:

```python
from agentlabx.core.state import (
    PipelineState, ResearchPlan, StagePlan, StagePlanItem,
)


    def build_plan(
        self, state: PipelineState, *, feedback: str | None = None
    ) -> StagePlan:
        topic = state.get("research_topic", "")
        prior = state.get("plan", [])
        has_prior = bool(prior) and not feedback

        goals_status = "done" if has_prior else "todo"
        items: list[StagePlanItem] = [
            StagePlanItem(
                id="plan:goals",
                description=f"Define research goals for: {topic}",
                status=goals_status,
                source="prior" if has_prior else "contract",
                existing_artifact_ref="plan[-1]" if has_prior else None,
                edit_note=None,
                removed_reason=None,
            ),
            StagePlanItem(
                id="plan:methodology",
                description="Specify methodology and approach",
                status="todo",
                source="contract",
                existing_artifact_ref=None,
                edit_note=None,
                removed_reason=None,
            ),
            StagePlanItem(
                id="plan:hypotheses",
                description="Propose initial hypotheses",
                status="todo",
                source="contract",
                existing_artifact_ref=None,
                edit_note=None,
                removed_reason=None,
            ),
        ]

        if feedback:
            items.append(
                StagePlanItem(
                    id="plan:feedback-driven",
                    description=f"Revise plan: {feedback}",
                    status="todo",
                    source="feedback",
                    existing_artifact_ref=None,
                    edit_note=None,
                    removed_reason=None,
                )
            )

        rationale = f"Plan formulation for '{topic}'"
        if feedback:
            rationale += " (revising under feedback)"
        elif has_prior:
            rationale += " (prior plan exists; extending)"

        return StagePlan(
            items=items,
            rationale=rationale,
            hash_of_consumed_inputs=topic,
        )
```

Leave `.run()` intact — `execute_plan`'s default delegates to it.

- [ ] **Step 4: Update class docstring**

Per the literature_review precedent, note that plan items are observability-only today:

```python
class PlanFormulationStage(BaseStage):
    """Plan 7E migration: build_plan itemises research goals + methodology
    + hypotheses + optional feedback-driven work; execute_plan stays at the
    default (delegates to legacy .run()), so plan items are OBSERVABILITY-ONLY
    in 7E. A future plan will migrate execute_plan to iterate over plan.items.
    """
```

- [ ] **Step 5: Test + commit**

```bash
uv run pytest tests/stages/test_plan_formulation_subgraph.py -v
git add agentlabx/stages/plan_formulation.py tests/stages/test_plan_formulation_subgraph.py
git commit -m "feat(stages): migrate plan_formulation to plan-driven hooks (Plan 7E B1)"
```

---

### Task B2: Implementation zone — migrate data_exploration, data_preparation, experimentation

Three stages. Apply the same template. **Experimentation is the most structurally interesting** — it has baseline/main/ablation phases enforced by the stage contract, so its `build_plan` itemises one of each.

**Files:**
- Modify: `agentlabx/stages/data_exploration.py`
- Modify: `agentlabx/stages/data_preparation.py`
- Modify: `agentlabx/stages/experimentation.py`
- Create: `tests/stages/test_data_exploration_subgraph.py`
- Create: `tests/stages/test_data_preparation_subgraph.py`
- Create: `tests/stages/test_experimentation_subgraph.py`

#### data_exploration

`build_plan` items:
- `eda:survey` — "Survey dataset structure and quality"
- `eda:quality-issues` — "Identify data quality issues"
- `eda:recommendations` — "Recommend preparation steps"
- feedback-driven item if feedback given
- prior-bypass: survey marked done if `state["data_exploration"]` non-empty and no feedback

#### data_preparation

`build_plan` items:
- `prep:clean` — "Clean dataset based on EDA findings"
- `prep:features` — "Engineer features required by plan"
- `prep:pipeline-code` — "Produce dataset preparation code"
- feedback-driven item
- prior-bypass on `state["dataset_code"]` non-empty

#### experimentation

`build_plan` items (enforces the baseline/main/ablation structure from spec §3.6):
- `exp:baseline` — "Run at least one baseline experiment"
- `exp:main` — "Run main experiments against hypotheses"
- `exp:ablation` — "Run ablation studies (required if main shows improvement)"
- feedback-driven item
- prior-bypass: individual items mark `done` based on which tags already exist in `state["experiment_results"]` (e.g., `baseline` tag present → `exp:baseline` → `done`)

The prior-bypass for experimentation is the most meaningful — it encodes "don't re-run a baseline you already have."

Each stage gets 3–4 unit tests like B1.

- [ ] **Step 1: Write 3 test files** (one per stage) following the B1 template

- [ ] **Step 2: Implement 3 `build_plan` overrides** (one per stage)

- [ ] **Step 3: Update 3 class docstrings** with the migration note

- [ ] **Step 4: Test**

```bash
uv run pytest tests/stages/test_data_exploration_subgraph.py tests/stages/test_data_preparation_subgraph.py tests/stages/test_experimentation_subgraph.py -v
```

- [ ] **Step 5: Commit**

```bash
git add agentlabx/stages/data_exploration.py agentlabx/stages/data_preparation.py agentlabx/stages/experimentation.py tests/stages/test_data_exploration_subgraph.py tests/stages/test_data_preparation_subgraph.py tests/stages/test_experimentation_subgraph.py
git commit -m "feat(stages): migrate implementation zone (EDA/prep/exp) to plan-driven hooks (Plan 7E B2)"
```

---

### Task B3: Synthesis zone — migrate results_interpretation, report_writing, peer_review

Three stages. Same template.

#### results_interpretation

`build_plan` items:
- `interp:metrics` — "Interpret experiment metrics against hypotheses"
- `interp:hypothesis-updates` — "Update hypothesis status (supported/refuted/active)"
- `interp:narrative` — "Produce narrative interpretation"
- feedback-driven item
- prior-bypass on `state["interpretation"]` non-empty

#### report_writing

`build_plan` items:
- `report:abstract` — "Write abstract"
- `report:introduction` — "Write introduction"
- `report:methodology` — "Write methodology section"
- `report:results` — "Write results section"
- `report:discussion` — "Write discussion"
- `report:conclusion` — "Write conclusion"
- feedback-driven item
- prior-bypass: sections marked done based on `state["report"][-1].sections` keys present

#### peer_review

`build_plan` items:
- `review:baselines-check` — "Check experiment baselines are sufficient"
- `review:novelty` — "Evaluate novelty and significance"
- `review:clarity` — "Review report clarity"
- `review:recommendation` — "Produce accept/revise/reject recommendation"
- feedback-driven item
- prior-bypass on `state["review"]` non-empty

- [ ] **Step 1: Write 3 test files**

- [ ] **Step 2: Implement 3 `build_plan` overrides**

- [ ] **Step 3: Update 3 class docstrings**

- [ ] **Step 4: Test**

```bash
uv run pytest tests/stages/test_results_interpretation_subgraph.py tests/stages/test_report_writing_subgraph.py tests/stages/test_peer_review_subgraph.py -v
```

- [ ] **Step 5: Commit**

```bash
git add agentlabx/stages/results_interpretation.py agentlabx/stages/report_writing.py agentlabx/stages/peer_review.py tests/stages/test_results_interpretation_subgraph.py tests/stages/test_report_writing_subgraph.py tests/stages/test_peer_review_subgraph.py
git commit -m "feat(stages): migrate synthesis zone (interp/report/review) to plan-driven hooks (Plan 7E B3)"
```

---

## Part C: UX polish

### Task C1: Forward stage control mode in `checkpoint_reached` event

**Problem:** backend emits `checkpoint_reached` without signalling whether the stage's control is `approve` (binary yes/no UX) or `edit` (edit-output form UX). Modal shows all three buttons (approve/edit/redirect) regardless.

**Fix:** `transition_node` reads the stage's configured control from `SessionPreferences.stage_controls[stage_name]` and puts it in the event's data. Modal reads the mode and renders accordingly.

**Files:**
- Modify: `agentlabx/core/pipeline.py` — add `control_mode` to event data
- Modify: `web/src/components/session/CheckpointModal.tsx` — render mode-aware UX

- [ ] **Step 1: Test**

Add a test in `tests/core/test_pipeline.py`:

```python
@pytest.mark.asyncio
async def test_checkpoint_reached_event_includes_control_mode(registry, monkeypatch):
    # Configure stage_controls[literature_review]="approve"
    # Force a needs_approval transition
    # Assert the emitted event has data["control_mode"] == "approve"
```

- [ ] **Step 2: Update emission**

In `agentlabx/core/pipeline.py` where the event fires:

```python
control_mode = self.preferences.get_stage_control(current_stage)
await event_bus.emit(
    Event(
        type=EventTypes.CHECKPOINT_REACHED,
        data={
            "stage": current_stage,
            "next_stage": decision.next_stage,
            "reason": decision.reason,
            "control_mode": control_mode,  # NEW — "approve" | "edit" | ...
            "pi_recommendation": ..., # existing
        },
        source="transition_handler",
    )
)
```

- [ ] **Step 3: Modal renders mode-aware UX**

In `CheckpointModal.tsx`, read `event.data.control_mode`:

- `approve` → show Approve / Reject buttons only (hide Edit).
- `edit` → show Approve + Edit (with textarea) + Reject.
- fallback → show all three.

- [ ] **Step 4: Commit**

```bash
git add agentlabx/core/pipeline.py web/src/components/session/CheckpointModal.tsx tests/core/test_pipeline.py web/tests/components/CheckpointModal.test.tsx
git commit -m "feat(hitl): forward stage control mode to CheckpointModal (Plan 7E C1)"
```

---

### Task C2: Cursor reverse-sweep animation on backtrack

**Problem:** Plan 7D Figure 1 promised an "orange glow sweeps through intermediate stages" when the cursor jumps backward. Implementation was TODO-marked in `GraphTopology.tsx:212-214`.

**Fix:** ~30 LOC CSS keyframe + edge animation. Detect the cursor jump across renders via a `useRef(previousCursor)`. When `previousCursorIndex > newCursorIndex` in the default_sequence, apply a `.cursor-reverse-sweep` class to intermediate node ids for 600ms.

**Files:**
- Modify: `web/src/components/session/GraphTopology.tsx`
- Modify: `web/src/index.css` (or wherever global styles live)
- Modify: `web/tests/components/GraphTopology.test.tsx`

(Detailed steps: the plan is short enough to complete within the dispatch; dispatch with the TODO location as starting point.)

---

### Task C3: Accessibility — ARIA + keyboard handlers

**Problem:** `CheckpointModal` buttons use `@ant-design/icons` without `aria-label` (SR reads "button" thrice). `StageSubgraphDrawer` / `LabMeetingOverlay` / `StageNode` have clickable divs without `role="button"` or keyboard handlers (keyboard users can't toggle panels).

**Fix:** apply the standard a11y pattern:
- Add `aria-label` to all icon-only buttons (Approve / Reject / Edit in modal).
- Add `role="button"` + `tabIndex={0}` + `onKeyDown` (Enter/Space triggers click) to clickable divs.

**Files:**
- Modify: `web/src/components/session/CheckpointModal.tsx`
- Modify: `web/src/components/session/StageSubgraphDrawer.tsx`
- Modify: `web/src/components/session/LabMeetingOverlay.tsx`
- Modify: `web/src/components/session/StageNode.tsx`
- Add accessibility tests in each affected test file.

---

### Task C4: Endpoint validation — 404 on unknown stages

**Problem:** `/stage_plans/{stage}` and `/stages/{stage}/history` accept any string and return empty results. Typos from client produce silent empty renders instead of actionable 404s.

**Fix:** whitelist against `registry.list_plugins(PluginType.STAGE)` keys. Return 404 for unknown stage names.

**Files:**
- Modify: `agentlabx/server/routes/sessions.py` (both endpoints)
- Modify: `tests/server/routes/test_stage_plans_endpoint.py` (add unknown-stage test)
- Modify: `tests/server/routes/test_stage_history_endpoint.py` (add unknown-stage test)

---

### Task C5: `uiStore` session-keyed panel state

**Problem:** `innerPanelOpen`, `meetingPanelOpen`, `drawerOpen` are single booleans. User switches sessions; stale state claims the new session has its panel open.

**Fix:** key panel state by sessionId. Either:

- `innerPanelOpen: Record<string, boolean>` — keyed map.
- Or: clear state when sessionId changes (effect on SessionDetailPage).

First is more architecturally correct (allows multiple sessions via URL); second is simpler. Pick second for now, commit TODO for first if multi-session URL routing is ever added.

**Files:**
- Modify: `web/src/stores/uiStore.ts`
- Modify: `web/src/pages/SessionDetailPage.tsx` — clear panel state on sessionId change
- Modify: `web/tests/stores/uiStore.test.ts`

---

## Self-review checklist

- [ ] **Spec coverage:**
  - §3.2.1 stage subgraph — Part B completes the migration footprint (all 8 stages now have `build_plan` overrides).
  - §3.2.2 StagePlan — Part B makes plan items authoritative (observability + visibility for all stages).
  - §3.3 transition handler — A2 closes the HITL pause gap.
  - §3.8 HITL execution modes — A2 + C1 honour the `approve` / `edit` distinction.
  - §8.2 Session Detail layout — Part C polishes.
- [ ] **No placeholders:** every task shows concrete code + commands or points at an existing template to mirror.
- [ ] **Process rule honoured:** if any task's implementation diverges from spec, flag before shipping — update spec with approved reality. Apply `feedback_spec_alignment.md` discipline.
- [ ] **Pre-production:** delete dead code outright; no backwards-compat shims.

---

## Execution

Dispatch order: **Part A → Part B → Part C**. Parts B and C can run in parallel after A1.

After Plan 7E ships:
- Spec becomes reality-accurate end-to-end across Plan 7.
- All 8 stages produce structured plans visible to users.
- HITL genuinely pauses.
- UX parity with Option A design target.

Remaining backlog (post-7E):
- **Per-item agent dispatch** — each stage's `execute_plan` iterates over `plan.items` and dispatches an agent per item. Today `execute_plan` delegates to `.run()` (single-shot). This is a substantial refactor per stage.
- `lab_meeting` subgraph body.
- `lab_scene` pixel-art conversation renderer.
- Pre-existing `SessionCreatePage` flakes + `TestFullSessionLifecycle` E2E timeouts.
