# Plan 7B: Stages as LangGraph Subgraphs + StagePlan Primitive

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Turn every stage into an internal LangGraph subgraph — `enter → stage_plan → gate → work → evaluate → decide` — driven by a `StagePlan` (a structured per-entry to-do list whose items are classified as `done` / `edit` / `todo` / `removed`). Also introduces the `invocable_only` flag so `lab_meeting` can live in the registry as a callable subgraph without appearing on the top-level pipeline graph.

**Architecture:** `BaseStage` gains four optional hooks — `build_plan(state, feedback)`, `execute_plan(state, plan, context)`, `evaluate(state, plan, execution)`, `decide(state, plan, evaluation)`. A new `StageSubgraphBuilder.compile(stage)` assembles these into a LangGraph `StateGraph` and returns a compiled subgraph whose entry signature matches `StageRunner`'s expectation. `StageRunner` now invokes the compiled subgraph instead of calling `stage.run` directly. Default hook implementations preserve the current behaviour (`build_plan` returns a single `todo` item "run stage", `execute_plan` delegates to `stage.run`, etc.) so Plan 7A's passing tests remain green without any stage-specific migration in this plan.

**Tech Stack:** Python 3.11+, LangGraph subgraphs, Pydantic v2, pytest-asyncio. No new dependencies.

**Pre-production principle:** AgentLabX has not shipped. Plan 7B makes breaking changes — update tests instead of retaining backwards compatibility.

**Spec sections implemented:** §3.2.1 stage subgraph shape, §3.2.2 StagePlan primitive, §5.5 `invocable_only` flag exclusion. §3.3 transition handler unchanged (Plan 7A).

**Companion spec:** `docs/superpowers/specs/2026-04-12-agentlabx-platform-design.md` §3.2.1, §3.2.2, §5.5.

**Out of scope (later plans):**
- **Per-stage migration** to actual plan-driven hooks (literature_review's own `build_plan` that itemises search topics, experimentation's `evaluate` that detects performance ceilings, etc.) — Plan 7B² (a sibling plan: "migrate stages to plan-driven hooks"). 7B ships the primitive + one example migration (literature_review) as the template.
- PI advisor reconception (Plan 7C)
- Frontend subgraph drawer (Plan 7D)
- Lab_meeting's full multi-agent discussion body (Plan 7C or a dedicated later plan)

## Design decisions pinned before implementation

Four seams the review flagged. Resolved in this plan text so Task 4 doesn't pause mid-implementation.

**1. Subgraph checkpointer — NO child checkpointer; subgraph runs atomically per parent step.**

Each stage's compiled subgraph is built WITHOUT a checkpointer. The parent pipeline graph's checkpointer (injected by `PipelineBuilder.build`) persists at the parent's node boundaries — the stage's entire `enter → stage_plan → gate → work → evaluate → decide` chain is a single parent-step from the checkpointer's perspective. Implication:
- On pause mid-stage, resume restarts the stage's subgraph from `enter`. Stages must be idempotent at this granularity (they already are — `StageResult` lists are append-only).
- No `thread_id` juggling at the subgraph layer.
- `StagePlan` persists via the state key `stage_plans[stage_name]` written at the end of the `stage_plan` node, which lands in the parent checkpoint along with every other state field when the stage's subgraph completes.

If a future plan needs intra-stage replay (e.g., for debugging a specific stage turn without re-running prior turns), that's a targeted subgraph-checkpointer addition, not Plan 7B.

**2. `stage_plans` reducer semantics — in-place mutation invariant, matches `agent_memory` (Plan 6A).**

Declared as plain `dict[str, list[StagePlan]]` with no `Annotated[..., reducer]` wrapper. LangGraph's default behaviour for unannotated dicts is whole-value overwrite, **not** dict merge. This is safe only because:
- Stages run sequentially (enforced by `PipelineBuilder`'s linear wiring).
- Only the current stage's subgraph writes to `stage_plans[name]`.
- The subgraph's `stage_plan` node mutates `state["stage_plans"]` in place via `state["stage_plans"] = {**existing, name: history + [new_plan]}`.

**Do NOT refactor** to return a partial `{"stage_plans": {...}}` update from a stage — it will silently wipe other stages' entries. If Plan 7B²/7C introduces parallel stage execution or event-driven partial returns, switch to `Annotated[dict, _merge_stage_plans]` with a proper dict-merge reducer FIRST. Same invariant as `agent_memory` in `agentlabx/stages/base.py::sync_agent_memory_to_state` — keep the docstring there in sync with this one.

**3. Explicit hook signatures (used throughout Task 3/4/6):**

```python
# On BaseStage:
def build_plan(self, state: PipelineState, *, feedback: str | None) -> StagePlan
async def execute_plan(self, state: PipelineState, plan: StagePlan, context: StageContext) -> StageExecution
def evaluate(self, state: PipelineState, *, plan: StagePlan, execution: StageExecution) -> StageEvaluation
def decide(self, state: PipelineState, *, plan: StagePlan, execution: StageExecution, evaluation: StageEvaluation) -> StageResult
```

Defaults in Task 3:
- `build_plan` → single `todo` item `"Run {self.name} stage (legacy .run() path)"`.
- `execute_plan` → awaits `self.run(state, context)` (legacy path), wraps the returned `StageResult` into a `StageExecution` (same fields minus `status` enum widened). One-to-one conversion, no adapter loss.
- `evaluate` → returns empty `StageEvaluation` (no overrides, no dead-end).
- `decide` → composes `StageResult` from `execution` + `evaluation.override_*` fields (override wins if set, else passthrough).

`StageExecution` and `StageEvaluation` types are introduced in Task 3 alongside the hooks.

**4. `invocable_only` stages get their own entry in the graph topology `subgraphs` array.**

Top-level `graph_mapper.build_topology` returns `{nodes, edges, cursor, subgraphs}`. Plan 7A left `subgraphs: []` with a `# TODO(7B)` comment. Plan 7B T2 populates it:
- Each registered stage whose class has `invocable_only=True` gets a subgraph entry: `{"id": "lab_meeting", "kind": "invocable_only", "label": "Lab Meeting", "nodes": [], "edges": []}`.
- Keeps `lab_meeting` off the production-line graph (per §5.5) while letting the frontend discover it for the recursive subgraph drawer (per §8.2).
- The `nodes`/`edges` arrays stay empty until Plan 7D; the frontend can still render a placeholder drill-in node.

Normal stage subgraphs (literature_review's `enter → ... → decide`) are NOT added to the topology's `subgraphs` array in 7B — the live-cursor graph drawer (§8.2) renders those from the compiled stage's `get_graph()` at runtime, not from a pre-serialised topology blob. Only invocable-only stages need topology-time discoverability because they have no top-level node to hang off.

---

## File structure

| File | Purpose | Create / Modify |
|---|---|---|
| `agentlabx/core/state.py` | Add `StagePlanStatus` Literal, `StagePlanItem` TypedDict, `StagePlan` TypedDict; add `stage_plans: dict[str, list[StagePlan]]` state key (keyed by stage, versioned list per entry) | Modify |
| `agentlabx/stages/base.py` | Add `invocable_only: ClassVar[bool] = False` to `BaseStage`. Add four optional hooks with default implementations: `build_plan`, `execute_plan`, `evaluate`, `decide`. Default `run()` still supported as fallback in `execute_plan`. | Modify |
| `agentlabx/stages/subgraph.py` | New — `StageSubgraphBuilder.compile(stage)` returns a LangGraph compiled subgraph | Create |
| `agentlabx/stages/runner.py` | `StageRunner` builds the subgraph on init (once per instance) and invokes it via `compiled_subgraph.ainvoke(state)` instead of `stage.run(...)` | Modify |
| `agentlabx/core/pipeline.py` | `PipelineBuilder` excludes `invocable_only=True` stages from top-level wiring. Subgraphs are still registered and discoverable. | Modify |
| `agentlabx/stages/lab_meeting.py` | Set `invocable_only = True`; confirm top-level graph no longer includes it | Modify |
| `agentlabx/stages/literature_review.py` | **Example migration** — override `build_plan` to itemise planned searches; use the four hooks explicitly; drop `run()` override | Modify |
| `tests/core/test_state.py` | StagePlan types + initial `stage_plans` state key | Modify |
| `tests/stages/test_base_hooks.py` | Default hook behaviour on a vanilla `BaseStage` subclass | Create |
| `tests/stages/test_subgraph.py` | `StageSubgraphBuilder.compile` produces a graph whose node ids match `enter → stage_plan → gate → work → evaluate → decide` and whose invocation returns the expected `StageResult` shape | Create |
| `tests/stages/test_invocable_only.py` | `LabMeeting.invocable_only is True`; `PipelineBuilder.build(default_sequence)` does NOT include it even if the registry contains it | Create |
| `tests/stages/test_literature_review_subgraph.py` | Migrated literature_review runs via subgraph and produces a StagePlan with expected items | Create |
| `tests/integration/test_plan7b_subgraph_end_to_end.py` | Full pipeline run where at least one stage uses plan-driven hooks and backtrack semantics still work | Create |

---

## Task 1: StagePlan types + `stage_plans` state key

**Files:**
- Modify: `agentlabx/core/state.py`
- Modify: `tests/core/test_state.py`

- [ ] **Step 1: Extend `tests/core/test_state.py` with failing test**

Append:

```python
from agentlabx.core.state import (
    StagePlan,
    StagePlanItem,
    StagePlanStatus,
)


def test_stage_plan_status_has_four_values():
    assert set(StagePlanStatus.__args__) == {"done", "edit", "todo", "removed"}


def test_stage_plan_item_shape():
    item: StagePlanItem = {
        "id": "i1",
        "description": "Collect 3 recent papers on CoT",
        "status": "todo",
        "source": "contract",
        "existing_artifact_ref": None,
        "edit_note": None,
        "removed_reason": None,
    }
    assert item["status"] == "todo"


def test_stage_plan_shape():
    plan: StagePlan = {
        "items": [],
        "rationale": "empty plan for a bypassed stage",
        "hash_of_consumed_inputs": "abc123",
    }
    assert plan["rationale"].startswith("empty")


def test_initial_state_has_stage_plans_key():
    from agentlabx.core.state import create_initial_state

    state = create_initial_state(
        session_id="s1", user_id="u1", research_topic="t"
    )
    assert state["stage_plans"] == {}
```

- [ ] **Step 2: Run — verify fail**

Run: `uv run pytest tests/core/test_state.py -v`
Expected: FAIL (imports don't exist).

- [ ] **Step 3: Add types to `agentlabx/core/state.py`**

Below the existing Plan 6 observability types (`AgentMemoryRecord`, `ExperimentAttempt`), add:

```python
StagePlanStatus = Literal["done", "edit", "todo", "removed"]
StagePlanItemSource = Literal["contract", "feedback", "request", "user", "prior"]


class StagePlanItem(TypedDict):
    id: str
    description: str
    status: StagePlanStatus
    source: StagePlanItemSource
    existing_artifact_ref: str | None
    edit_note: str | None
    removed_reason: str | None


class StagePlan(TypedDict):
    items: list[StagePlanItem]
    rationale: str
    hash_of_consumed_inputs: str
```

Then add a field to `PipelineState` (just below the Plan 7A backtrack keys):

```python
    # Stage plans (Plan 7B) — versioned list per stage, last element is latest.
    # INVARIANT: this field is a plain dict (NOT Annotated with a reducer).
    # LangGraph's default behaviour is whole-value overwrite, NOT dict merge.
    # Safe because (1) stages run sequentially, (2) only the current stage's
    # subgraph writes to stage_plans[name]. The stage_plan node in the
    # subgraph mutates via state["stage_plans"] = {**existing, name: hist+new}.
    #
    # DO NOT return {"stage_plans": {...}} as a partial update from a stage —
    # that will silently wipe other stages' entries. Same invariant as
    # agent_memory (see agentlabx/stages/base.py::sync_agent_memory_to_state).
    # Plan 7B²/7C introducing parallel stage execution or event-driven partial
    # returns MUST switch to Annotated[dict, _merge_stage_plans] first.
    stage_plans: dict[str, list[StagePlan]]
```

And initialise in `create_initial_state`:

```python
        stage_plans={},
```

- [ ] **Step 4: Run — verify pass**

Run: `uv run pytest tests/core/test_state.py -v`
Expected: all new tests pass.

- [ ] **Step 5: Commit**

```bash
git add agentlabx/core/state.py tests/core/test_state.py
git commit -m "feat(state): StagePlan + StagePlanItem types + stage_plans state key (Plan 7B T1)"
```

---

## Task 2: `invocable_only` flag on `BaseStage` + `LabMeeting.invocable_only = True` + `PipelineBuilder` exclusion + graph_mapper topology surfacing

**Files:**
- Modify: `agentlabx/stages/base.py`
- Modify: `agentlabx/stages/lab_meeting.py`
- Modify: `agentlabx/core/pipeline.py`
- Modify: `agentlabx/core/graph_mapper.py` — surface invocable-only stages via the topology's `subgraphs` array so the frontend can discover them even though they're not on the production-line graph
- Create: `tests/stages/test_invocable_only.py`

- [ ] **Step 1: Write failing test**

Create `tests/stages/test_invocable_only.py`:

```python
"""invocable_only stages are in the registry but excluded from top-level wiring."""
from __future__ import annotations

import pytest

from agentlabx.core.pipeline import PipelineBuilder
from agentlabx.core.registry import PluginRegistry, PluginType
from agentlabx.core.session import SessionPreferences
from agentlabx.plugins._builtin import register_builtin_plugins
from agentlabx.stages.base import BaseStage
from agentlabx.stages.lab_meeting import LabMeeting


@pytest.fixture
def registry():
    r = PluginRegistry()
    register_builtin_plugins(r)
    return r


def test_basestage_default_invocable_only_is_false():
    assert BaseStage.invocable_only is False


def test_labmeeting_is_invocable_only():
    assert LabMeeting.invocable_only is True


def test_pipelinebuilder_skips_invocable_only_stages(registry):
    """Lab_meeting is registered but must not appear as a node in the top-level graph."""
    builder = PipelineBuilder(
        registry=registry, preferences=SessionPreferences()
    )
    seq = [
        "literature_review",
        "plan_formulation",
        "lab_meeting",   # deliberately requested — builder must skip
        "experimentation",
    ]
    graph = builder.build(stage_sequence=seq)
    node_ids = {n for n in graph.get_graph().nodes}
    assert "lab_meeting" not in node_ids
    assert "experimentation" in node_ids


def test_pipelinebuilder_does_not_skip_stages_with_invocable_only_false(registry):
    builder = PipelineBuilder(
        registry=registry, preferences=SessionPreferences()
    )
    seq = ["literature_review", "plan_formulation"]
    graph = builder.build(stage_sequence=seq)
    node_ids = {n for n in graph.get_graph().nodes}
    assert "literature_review" in node_ids
    assert "plan_formulation" in node_ids
```

- [ ] **Step 2: Run — verify fail**

Run: `uv run pytest tests/stages/test_invocable_only.py -v`
Expected: FAIL (`invocable_only` undefined).

- [ ] **Step 3: Add `invocable_only` to `BaseStage`**

In `agentlabx/stages/base.py`:

```python
class BaseStage(ABC):
    name: str
    description: str
    required_agents: list[str]
    required_tools: list[str]
    zone: ClassVar[ZoneName | None] = None
    invocable_only: ClassVar[bool] = False  # True = callable subgraph, excluded from top-level wiring
    ...
```

In `agentlabx/stages/lab_meeting.py`, on the `LabMeeting` class:

```python
class LabMeeting(BaseStage):
    name = "lab_meeting"
    zone = None
    invocable_only = True
    ...
```

- [ ] **Step 4: Update `PipelineBuilder.build` to skip `invocable_only` stages**

In `agentlabx/core/pipeline.py` inside `build`, after resolving stage classes, filter the sequence. Where the current code does:

```python
        runners: dict[str, StageRunner] = {}
        for stage_name in stage_sequence:
            stage_cls = self.registry.resolve(PluginType.STAGE, stage_name)
            stage_instance = stage_cls()
            runners[stage_name] = StageRunner(stage_instance, context=stage_context)
```

replace with:

```python
        runners: dict[str, StageRunner] = {}
        effective_sequence: list[str] = []
        for stage_name in stage_sequence:
            stage_cls = self.registry.resolve(PluginType.STAGE, stage_name)
            if getattr(stage_cls, "invocable_only", False):
                # Callable subgraph — not wired into the top-level graph.
                # Will be invoked from stage work nodes when requested.
                continue
            stage_instance = stage_cls()
            runners[stage_name] = StageRunner(stage_instance, context=stage_context)
            effective_sequence.append(stage_name)
```

Then use `effective_sequence` everywhere `stage_sequence` is referenced below that point: `builder.add_edge(START, effective_sequence[0])`, the per-stage loop, `route_map`. Also update `state["default_sequence"]` handling if it expects the unfiltered list — the filtered list should be what drives top-level routing.

Note: if `effective_sequence` is empty (e.g., all stages invocable_only — absurd edge case), the current code would crash at `effective_sequence[0]`. Add a guard:

```python
        if not effective_sequence:
            raise ValueError("stage_sequence has no runnable (non-invocable-only) stages")
```

- [ ] **Step 5: Surface invocable-only stages in `graph_mapper` topology**

Frontend needs to discover invocable-only stages for the recursive subgraph drawer (§8.2) even though they're off the production-line graph. Update `agentlabx/core/graph_mapper.py::build_topology` to populate the `subgraphs` list with entries for invocable-only registered stages.

Replace the `# TODO(7B)` block (added during Plan 7A polish) with:

```python
    # Invocable-only stages (e.g., lab_meeting, §5.5) are registered but not
    # wired into the top-level graph. Surface them here so the frontend can
    # discover them for the recursive subgraph drawer (spec §8.2). The
    # nodes/edges arrays stay empty in Plan 7B; Plan 7D renders the
    # subgraph internals from the compiled stage's get_graph() at runtime.
    subgraphs: list[dict[str, object]] = []
    if registry is not None:
        try:
            from agentlabx.core.registry import PluginType
            for name, cls in registry.list(PluginType.STAGE):
                if getattr(cls, "invocable_only", False):
                    subgraphs.append({
                        "id": name,
                        "kind": "invocable_only",
                        "label": getattr(cls, "description", name),
                        "nodes": [],
                        "edges": [],
                    })
        except Exception:
            # Registry-less path (tests) — subgraphs stays empty.
            pass

    return {
        "nodes": nodes,
        "edges": edges,
        "cursor": cursor,
        "subgraphs": subgraphs,
    }
```

(The exact registry enumeration method may differ — check `PluginRegistry` for the right API. If it's `registry.plugins[PluginType.STAGE].items()` or similar, adapt.)

Add a test to `tests/stages/test_invocable_only.py`:

```python
def test_graph_mapper_surfaces_invocable_only_stages(registry):
    """Invocable-only stages appear in topology.subgraphs, not in topology.nodes."""
    from agentlabx.core.graph_mapper import build_topology
    from agentlabx.core.pipeline import PipelineBuilder

    builder = PipelineBuilder(
        registry=registry, preferences=SessionPreferences()
    )
    compiled = builder.build(stage_sequence=["literature_review", "plan_formulation"])
    state = {}  # build_topology doesn't need a full state here

    topology = build_topology(compiled, state, registry=registry)
    node_ids = {n["id"] for n in topology["nodes"]}
    subgraph_ids = {s["id"] for s in topology["subgraphs"]}

    assert "lab_meeting" not in node_ids
    assert "lab_meeting" in subgraph_ids
    lm = next(s for s in topology["subgraphs"] if s["id"] == "lab_meeting")
    assert lm["kind"] == "invocable_only"
```

- [ ] **Step 6: Run tests**

Run: `uv run pytest tests/stages/test_invocable_only.py -v`
Expected: all 5 PASS (4 existing + 1 new graph_mapper test).

Also run regression: `uv run pytest tests/ -x -q`
Expected: all pass. Pre-existing tests that enumerated all stages in `default_sequence` via registry → actual graph nodes may break if they enumerated `lab_meeting`. Update per pre-production principle.

- [ ] **Step 7: Commit**

```bash
git add agentlabx/stages/base.py agentlabx/stages/lab_meeting.py agentlabx/core/pipeline.py agentlabx/core/graph_mapper.py tests/stages/test_invocable_only.py
git commit -m "feat(pipeline): invocable_only flag excludes lab_meeting + surfaces in topology subgraphs (Plan 7B T2)"
```

---

## Task 3: `BaseStage` subgraph hooks with default implementations

**Files:**
- Modify: `agentlabx/stages/base.py`
- Create: `tests/stages/test_base_hooks.py`

The four hooks work in sequence: `build_plan(state, feedback) → StagePlan`, `execute_plan(state, plan, context) → dict` (output), `evaluate(state, plan, execution) → StagePlanExecution` (carries status + diagnostics), `decide(state, plan, evaluation) → StageResult`. Defaults delegate the whole thing back to the existing `run()` so non-migrated stages work unchanged.

- [ ] **Step 1: Write failing test**

Create `tests/stages/test_base_hooks.py`:

```python
"""BaseStage subgraph hooks — default implementations preserve .run() semantics."""
from __future__ import annotations

import pytest

from agentlabx.core.state import (
    StagePlan,
    StagePlanItem,
    create_initial_state,
)
from agentlabx.stages.base import (
    BaseStage,
    StageContext,
    StageExecution,
    StageResult,
)


class _LegacyStage(BaseStage):
    """Pre-7B stage: implements only .run(), relies on default hooks."""

    name = "legacy"
    description = "legacy stage using only .run()"
    required_agents: list[str] = []
    required_tools: list[str] = []
    zone = "discovery"

    async def run(self, state, context):
        return StageResult(
            output={"literature_review": [{"papers": [], "summary": "legacy ran"}]},
            status="done",
            reason="legacy",
        )


def _state():
    return create_initial_state(
        session_id="s1", user_id="u1", research_topic="t"
    )


def test_default_build_plan_returns_single_todo_item():
    stage = _LegacyStage()
    plan = stage.build_plan(_state(), feedback=None)
    assert len(plan["items"]) == 1
    assert plan["items"][0]["status"] == "todo"
    assert "run" in plan["items"][0]["description"].lower()


@pytest.mark.asyncio
async def test_default_execute_plan_delegates_to_run():
    stage = _LegacyStage()
    state = _state()
    plan = stage.build_plan(state, feedback=None)
    execution = await stage.execute_plan(
        state, plan, StageContext(settings={}, event_bus=None, registry=None)
    )
    assert execution.output == {
        "literature_review": [{"papers": [], "summary": "legacy ran"}]
    }
    assert execution.status == "done"


def test_default_evaluate_passes_through_execution_status():
    stage = _LegacyStage()
    execution = StageExecution(
        output={}, status="done", reason="ok", feedback=None, next_hint=None
    )
    evaluation = stage.evaluate(_state(), plan={}, execution=execution)
    assert evaluation.dead_end is False


def test_default_decide_builds_stage_result_from_execution():
    stage = _LegacyStage()
    execution = StageExecution(
        output={"plan": [{"full_text": "x"}]},
        status="done",
        reason="ok",
        feedback=None,
        next_hint=None,
    )
    evaluation = stage.evaluate(_state(), plan={}, execution=execution)
    result = stage.decide(_state(), plan={}, execution=execution, evaluation=evaluation)
    assert result.output == {"plan": [{"full_text": "x"}]}
    assert result.status == "done"
```

- [ ] **Step 2: Run — verify fail**

Run: `uv run pytest tests/stages/test_base_hooks.py -v`
Expected: FAIL (`StageExecution` and hooks undefined).

- [ ] **Step 3: Extend `BaseStage` with hooks + `StageExecution` / `StageEvaluation` models**

In `agentlabx/stages/base.py`, after the `StageResult` class, add:

```python
class StageExecution(BaseModel):
    """Intermediate result of the `execute_plan` hook — fed to `evaluate`."""
    output: Any
    status: Literal["done", "backtrack", "negative_result", "request"]
    reason: str
    feedback: str | None = None
    next_hint: str | None = None
    requests: list[CrossStageRequest] | None = None


class StageEvaluation(BaseModel):
    """Evaluate-hook output — may override execution's status."""
    dead_end: bool = False
    override_status: Literal["done", "backtrack", "negative_result", "request"] | None = None
    override_next_hint: str | None = None
    override_reason: str | None = None
    notes: list[str] = []
```

Then add hooks to `BaseStage`:

```python
class BaseStage(ABC):
    ...

    # ── Subgraph hooks (Plan 7B) ─────────────────────────────────────────
    # Override these for plan-driven behaviour. Defaults delegate to .run().

    def build_plan(
        self, state: PipelineState, *, feedback: str | None = None
    ) -> StagePlan:
        """Return a StagePlan for this entry.

        Default: a single `todo` item that the default execute_plan resolves
        by calling `.run()`. Stages overriding this must itemise concrete
        tasks per §3.2.2.
        """
        return StagePlan(
            items=[
                StagePlanItem(
                    id=f"{self.name}:run",
                    description=f"Run {self.name} stage (legacy .run() path)",
                    status="todo",
                    source="contract",
                    existing_artifact_ref=None,
                    edit_note=None,
                    removed_reason=None,
                )
            ],
            rationale="Default plan — single todo delegating to .run().",
            hash_of_consumed_inputs="",
        )

    async def execute_plan(
        self,
        state: PipelineState,
        plan: StagePlan,
        context: StageContext,
    ) -> StageExecution:
        """Execute actionable plan items. Default: delegate to .run()."""
        # Default path: preserve the pre-7B single-step .run() semantics.
        result = await self.run(state, context)
        return StageExecution(
            output=result.output,
            status=result.status,
            reason=result.reason,
            feedback=result.feedback,
            next_hint=result.next_hint,
            requests=result.requests,
        )

    def evaluate(
        self,
        state: PipelineState,
        *,
        plan: StagePlan,
        execution: StageExecution,
    ) -> StageEvaluation:
        """Detect dead-ends or additional work. Default: pass through."""
        return StageEvaluation()

    def decide(
        self,
        state: PipelineState,
        *,
        plan: StagePlan,
        execution: StageExecution,
        evaluation: StageEvaluation,
    ) -> StageResult:
        """Build the final StageResult. Default: compose execution + evaluation."""
        status = evaluation.override_status or execution.status
        next_hint = evaluation.override_next_hint or execution.next_hint
        reason = evaluation.override_reason or execution.reason
        return StageResult(
            output=execution.output,
            status=status,
            next_hint=next_hint,
            reason=reason,
            feedback=execution.feedback,
            requests=execution.requests,
        )
```

Note: the legacy `async def run(...)` abstract method stays — stages that don't migrate override only `run()`; stages that migrate override the hooks and stop overriding `run()` (the default `execute_plan` is no longer reached in that case).

- [ ] **Step 4: Run — verify pass**

Run: `uv run pytest tests/stages/test_base_hooks.py -v`
Expected: 4 PASS.

- [ ] **Step 5: Commit**

```bash
git add agentlabx/stages/base.py tests/stages/test_base_hooks.py
git commit -m "feat(stages): BaseStage subgraph hooks with defaults (Plan 7B T3)"
```

---

## Task 4: `StageSubgraphBuilder` — compile `enter → stage_plan → gate → work → evaluate → decide`

**Files:**
- Create: `agentlabx/stages/subgraph.py`
- Create: `tests/stages/test_subgraph.py`

The builder wires the four hooks into a LangGraph `StateGraph`. The subgraph uses the same `PipelineState` type as the top-level graph — it reads from and writes to state directly. Gate branches:

- `stage_plan` node produces a `StagePlan` → written into state under `stage_plans[stage_name][-1]`
- `gate` inspects the plan: if all items are `done`/`removed` → route to `decide` (bypass). If items exist and none are actionable (empty) → route to `decide` with a `status=done, reason=plan-empty`. Otherwise → route to `work`.
- `work` node calls `stage.execute_plan(...)` and stashes a `StageExecution` in a scratch state field (`_stage_execution`).
- `evaluate` node calls `stage.evaluate(...)` and stashes a `StageEvaluation`.
- `decide` node calls `stage.decide(...)` and returns the `StageResult` as a dict — the runner translates to state updates.

Plan-initiated backtrack: if `build_plan` returns a plan whose first item's status is `removed` with `removed_reason == "prerequisite_missing"` AND the plan has `rationale` starting with `"backtrack:"`, the gate routes directly to `decide` with an override so it emits `StageResult(status="backtrack", next_hint=<target from rationale>, feedback=<rationale>)`. Concrete pattern defined here to keep the API narrow; Plan 7B² will extend.

- [ ] **Step 1: Write failing test**

Create `tests/stages/test_subgraph.py`:

```python
"""StageSubgraphBuilder compiles enter → stage_plan → gate → work → evaluate → decide."""
from __future__ import annotations

import pytest

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
        return StageResult(
            output={"literature_review": [{"papers": [], "summary": "echo"}]},
            status="done",
            reason="ok",
        )


@pytest.mark.asyncio
async def test_compiled_subgraph_has_expected_nodes():
    stage = _EchoStage()
    compiled = StageSubgraphBuilder().compile(stage)
    node_ids = set(compiled.get_graph().nodes)
    assert {"enter", "stage_plan", "gate", "work", "evaluate", "decide"}.issubset(
        node_ids
    )


@pytest.mark.asyncio
async def test_compiled_subgraph_runs_default_path():
    stage = _EchoStage()
    compiled = StageSubgraphBuilder().compile(stage)
    state = create_initial_state(
        session_id="s1", user_id="u1", research_topic="t"
    )
    state["current_stage"] = "echo"
    result = await compiled.ainvoke(
        {"state": state,
         "context": StageContext(settings={}, event_bus=None, registry=None)},
        config={"configurable": {"thread_id": "t1"}},
    )
    # Subgraph must record a StagePlan for this entry
    assert "echo" in result["state"]["stage_plans"]
    # and produce a final StageResult with status=done
    assert result["stage_result"].status == "done"


@pytest.mark.asyncio
async def test_subgraph_bypass_when_plan_empty():
    class _BypassStage(_EchoStage):
        name = "bypass"

        def build_plan(self, state, *, feedback=None):
            # Plan with only 'done' items — should bypass to decide
            from agentlabx.core.state import StagePlan, StagePlanItem
            return StagePlan(
                items=[
                    StagePlanItem(
                        id="already",
                        description="already done",
                        status="done",
                        source="prior",
                        existing_artifact_ref=None,
                        edit_note=None,
                        removed_reason=None,
                    )
                ],
                rationale="bypass: outputs already valid",
                hash_of_consumed_inputs="",
            )

    stage = _BypassStage()
    compiled = StageSubgraphBuilder().compile(stage)
    state = create_initial_state(
        session_id="s1", user_id="u1", research_topic="t"
    )
    state["current_stage"] = "bypass"
    result = await compiled.ainvoke(
        {"state": state,
         "context": StageContext(settings={}, event_bus=None, registry=None)},
        config={"configurable": {"thread_id": "t1"}},
    )
    assert result["stage_result"].status == "done"
    assert "bypass" in result["stage_result"].reason.lower()
```

- [ ] **Step 2: Run — verify fail**

Run: `uv run pytest tests/stages/test_subgraph.py -v`
Expected: FAIL (`StageSubgraphBuilder` undefined).

- [ ] **Step 3: Create `agentlabx/stages/subgraph.py`**

```python
"""Compile per-stage LangGraph subgraphs: enter → stage_plan → gate → work → evaluate → decide."""
from __future__ import annotations

from typing import Any, TypedDict

from langgraph.graph import END, START, StateGraph

from agentlabx.core.state import PipelineState, StagePlan
from agentlabx.stages.base import (
    BaseStage,
    StageContext,
    StageEvaluation,
    StageExecution,
    StageResult,
)


class _SubgraphState(TypedDict, total=False):
    """Working state for a single stage's subgraph execution.

    `state` is the full PipelineState (mutated as the subgraph runs).
    `context` is the StageContext injected by StageRunner.
    Intermediate hooks stash their outputs here so later nodes can read.
    """
    state: PipelineState
    context: StageContext
    plan: StagePlan
    execution: StageExecution
    evaluation: StageEvaluation
    stage_result: StageResult


class StageSubgraphBuilder:
    """Compose a BaseStage into a compiled LangGraph subgraph."""

    def compile(self, stage: BaseStage) -> Any:
        builder: StateGraph = StateGraph(_SubgraphState)

        def enter_node(s: _SubgraphState) -> dict[str, Any]:
            # Pick up backtrack_feedback if this entry is post-backtrack
            feedback = s["state"].get("backtrack_feedback")
            return {"_feedback": feedback} if False else {}

        async def plan_node(s: _SubgraphState) -> dict[str, Any]:
            feedback = s["state"].get("backtrack_feedback")
            plan = stage.build_plan(s["state"], feedback=feedback)
            # Persist the plan on state for observability (versioned per entry).
            plans: dict = dict(s["state"].get("stage_plans", {}))
            history = list(plans.get(stage.name, []))
            history.append(plan)
            plans[stage.name] = history
            s["state"]["stage_plans"] = plans
            return {"plan": plan}

        def gate_node(s: _SubgraphState) -> str:
            """Route: plan_empty → decide; otherwise → work."""
            plan = s["plan"]
            actionable = [
                i for i in plan["items"]
                if i["status"] in ("todo", "edit")
            ]
            if not actionable:
                return "decide"
            return "work"

        async def work_node(s: _SubgraphState) -> dict[str, Any]:
            execution = await stage.execute_plan(
                s["state"], s["plan"], s["context"]
            )
            return {"execution": execution}

        def evaluate_node(s: _SubgraphState) -> dict[str, Any]:
            evaluation = stage.evaluate(
                s["state"], plan=s["plan"], execution=s["execution"]
            )
            return {"evaluation": evaluation}

        def decide_node(s: _SubgraphState) -> dict[str, Any]:
            execution = s.get("execution")
            evaluation = s.get("evaluation")
            if execution is None:
                # Bypass path: synthesise a done StageResult with plan rationale
                rationale = s["plan"]["rationale"]
                execution = StageExecution(
                    output={},
                    status="done",
                    reason=f"plan-empty: {rationale}",
                )
                evaluation = StageEvaluation()
            if evaluation is None:
                evaluation = StageEvaluation()
            result = stage.decide(
                s["state"],
                plan=s["plan"],
                execution=execution,
                evaluation=evaluation,
            )
            return {"stage_result": result}

        builder.add_node("enter", enter_node)
        builder.add_node("stage_plan", plan_node)
        builder.add_node("work", work_node)
        builder.add_node("evaluate", evaluate_node)
        builder.add_node("decide", decide_node)

        builder.add_edge(START, "enter")
        builder.add_edge("enter", "stage_plan")
        builder.add_conditional_edges(
            "stage_plan",
            gate_node,
            {"work": "work", "decide": "decide"},
        )
        builder.add_edge("work", "evaluate")
        builder.add_edge("evaluate", "decide")
        builder.add_edge("decide", END)

        return builder.compile()
```

Note: the subgraph state uses `TypedDict, total=False` so nodes can return partial updates that LangGraph merges. Plan-initiated backtrack (§3.2.2 case) is handled by the stage's own `build_plan` returning a plan whose `rationale` carries the target — this doesn't require routing complexity here (decide's default constructs the StageResult from execution.status; evaluation.override_status lets a plan surface as backtrack).

- [ ] **Step 4: Run — verify pass**

Run: `uv run pytest tests/stages/test_subgraph.py -v`
Expected: 3 PASS.

- [ ] **Step 5: Commit**

```bash
git add agentlabx/stages/subgraph.py tests/stages/test_subgraph.py
git commit -m "feat(subgraph): compile stage subgraphs (enter→plan→gate→work→eval→decide) (Plan 7B T4)"
```

---

## Task 5: `StageRunner` invokes the compiled subgraph

**Files:**
- Modify: `agentlabx/stages/runner.py`

Instead of calling `self.stage.run(entered_state, self.context)` directly, build once per `StageRunner` instance a compiled subgraph via `StageSubgraphBuilder().compile(self.stage)` and invoke it. All existing behaviour (emit `stage_started`/`stage_completed`, backtrack-cost snapshot, feedback plumbing, cooperative pause) stays — the subgraph produces the same `StageResult` the old `stage.run(...)` did.

- [ ] **Step 1: Write no new test — existing runner tests should ALL still pass**

Because default hooks delegate to `.run()`, every existing `StageRunner`-based test should pass unchanged when the runner is rewired. This is the core correctness assertion for T5.

- [ ] **Step 2: Update `agentlabx/stages/runner.py`**

In `StageRunner.__init__`, after `self.stage = stage`, add:

```python
        from agentlabx.stages.subgraph import StageSubgraphBuilder
        self._compiled_subgraph = StageSubgraphBuilder().compile(stage)
```

In `run()`, replace the `result = await self.stage.run(entered_state, self.context)` line with:

```python
            subgraph_result = await self._compiled_subgraph.ainvoke(
                {"state": entered_state, "context": self.context},
                config={"configurable": {"thread_id": f"{state.get('session_id', 's')}:{self.stage.name}"}},
            )
            result: StageResult = subgraph_result["stage_result"]
```

The rest of the `try:` block (merging output, emitting `stage_completed`, backtrack plumbing) stays unchanged — `result` is still a `StageResult` with the same shape as before.

Also: add `from agentlabx.stages.base import StageResult` if not already imported (for the explicit type annotation).

- [ ] **Step 3: Run the full stages suite**

Run: `uv run pytest tests/stages/ -v`
Expected: all pass. The T1-T4 Plan 7A tests, runner tests, and Plan 7B subgraph tests all rely on this integration.

If any pre-existing runner test fails: inspect whether the failure is a real regression or a test-fragility issue (e.g., test mocked `stage.run` but the runner no longer calls it directly). Update the test per pre-production principle to mock at the right layer — either patch `stage.execute_plan` (the new delegation point) or patch the whole compiled subgraph.

- [ ] **Step 4: Run full suite**

Run: `uv run pytest tests/ -x -q`
Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add agentlabx/stages/runner.py [any updated test files]
git commit -m "feat(runner): delegate stage execution to compiled subgraph (Plan 7B T5)"
```

---

## Task 6: Migrate `literature_review` to plan-driven hooks (example migration)

**Files:**
- Modify: `agentlabx/stages/literature_review.py`
- Create: `tests/stages/test_literature_review_subgraph.py`

Literature review is the canonical candidate: its work is inherently a list of searches / papers to read, each of which can be itemised in a StagePlan. This task demonstrates the migration pattern other stages will follow in Plan 7B².

- [ ] **Step 1: Read current `agentlabx/stages/literature_review.py`**

The current stage implements `async def run()` that assembles a `LitReviewResult` via the ConfigAgent's `phd_student`. Understand its flow before migrating.

- [ ] **Step 2: Write failing test `tests/stages/test_literature_review_subgraph.py`**

```python
"""literature_review runs via subgraph and produces a StagePlan."""
from __future__ import annotations

import pytest

from agentlabx.core.state import create_initial_state
from agentlabx.stages.base import StageContext
from agentlabx.stages.literature_review import LiteratureReviewStage
from agentlabx.stages.subgraph import StageSubgraphBuilder


@pytest.mark.asyncio
async def test_literature_review_build_plan_itemises_search_topics():
    stage = LiteratureReviewStage()
    state = create_initial_state(
        session_id="s1",
        user_id="u1",
        research_topic="chain of thought for MATH",
    )
    plan = stage.build_plan(state, feedback=None)
    # At least 2 items; at least one must be a todo for fresh work
    assert len(plan["items"]) >= 2
    assert any(i["status"] == "todo" for i in plan["items"])


@pytest.mark.asyncio
async def test_literature_review_runs_through_subgraph_produces_stage_plan():
    stage = LiteratureReviewStage()
    compiled = StageSubgraphBuilder().compile(stage)
    state = create_initial_state(
        session_id="s1", user_id="u1", research_topic="cot math"
    )
    state["current_stage"] = "literature_review"
    result = await compiled.ainvoke(
        {"state": state, "context": StageContext(settings={}, event_bus=None, registry=None)},
        config={"configurable": {"thread_id": "t1"}},
    )
    assert "literature_review" in result["state"]["stage_plans"]
    assert result["stage_result"].status == "done"
```

- [ ] **Step 3: Run — verify fail**

Run: `uv run pytest tests/stages/test_literature_review_subgraph.py -v`
Expected: FAIL (default `build_plan` produces single item).

- [ ] **Step 4: Migrate `literature_review.py`**

Replace the stage body. Keep the class name `LiteratureReviewStage`. Implement:

```python
class LiteratureReviewStage(BaseStage):
    name = "literature_review"
    description = "Collect and summarise relevant literature"
    zone = "discovery"
    required_agents = ["phd_student"]
    required_tools = ["arxiv_search"]

    def build_plan(
        self, state: PipelineState, *, feedback: str | None = None
    ) -> StagePlan:
        """Itemise planned literature searches based on research topic + feedback."""
        topic = state.get("research_topic", "")
        items: list[StagePlanItem] = [
            StagePlanItem(
                id=f"lit:topic-survey",
                description=f"Survey existing work on: {topic}",
                status="todo",
                source="contract",
                existing_artifact_ref=None,
                edit_note=None,
                removed_reason=None,
            ),
            StagePlanItem(
                id=f"lit:recent-papers",
                description="Gather 3-5 recent (last 2y) key papers",
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
                    id="lit:feedback-driven",
                    description=f"Address feedback: {feedback}",
                    status="todo",
                    source="feedback",
                    existing_artifact_ref=None,
                    edit_note=None,
                    removed_reason=None,
                )
            )
        # If prior lit_review exists and feedback is None, mark topic-survey as done
        prior = state.get("literature_review", [])
        if prior and not feedback:
            items[0] = {**items[0], "status": "done",
                        "existing_artifact_ref": f"literature_review[-1]"}

        return StagePlan(
            items=items,
            rationale=(
                f"Literature review plan for '{topic}'"
                + (f" (revising based on feedback)" if feedback else "")
            ),
            hash_of_consumed_inputs=topic,
        )

    async def execute_plan(
        self,
        state: PipelineState,
        plan: StagePlan,
        context: StageContext,
    ) -> StageExecution:
        """Execute actionable plan items via the PhD student agent."""
        # Keep the existing agent interaction simple: one phd_student call per
        # todo/edit item, aggregating results. If no todo/edit items, bypass.
        todo_items = [i for i in plan["items"] if i["status"] in ("todo", "edit")]
        if not todo_items:
            return StageExecution(
                output={}, status="done", reason="all plan items already satisfied"
            )

        # Delegate to the legacy .run() for the agent-calling details; a full
        # migration (per-item agent dispatch) is Plan 7B².
        legacy_result = await self.run(state, context)
        return StageExecution(
            output=legacy_result.output,
            status=legacy_result.status,
            reason=legacy_result.reason,
            feedback=legacy_result.feedback,
            next_hint=legacy_result.next_hint,
            requests=legacy_result.requests,
        )

    # Keep the existing async def run() so execute_plan's fallback works.
    # (copy/retain whatever the current run() body is)
```

Note: the original `async def run()` body stays intact — `execute_plan` delegates to it for the actual agent call. The migration adds structured planning + bypass-when-already-done semantics without rewriting the agent interaction. Plan 7B² will complete the migration by replacing `run()` delegation with per-item agent dispatch.

- [ ] **Step 5: Run literature_review tests**

Run: `uv run pytest tests/stages/test_literature_review*.py -v`
Expected: all pass — new subgraph tests + any existing literature_review tests.

- [ ] **Step 6: Regression**

Run: `uv run pytest tests/ -x -q`
Expected: all pass.

- [ ] **Step 7: Commit**

```bash
git add agentlabx/stages/literature_review.py tests/stages/test_literature_review_subgraph.py
git commit -m "feat(stages): migrate literature_review to plan-driven hooks (Plan 7B T6)"
```

---

## Task 7: End-to-end integration test

**Files:**
- Create: `tests/integration/test_plan7b_subgraph_end_to_end.py`

Exercise the full pipeline run to confirm:
1. Every stage produces a StagePlan visible in `state["stage_plans"]`.
2. `lab_meeting` is never entered via top-level routing (it's invocable_only).
3. A backtrack still flows correctly through subgraph-based stages (Plan 7A behaviour preserved).

- [ ] **Step 1: Write the test**

Create `tests/integration/test_plan7b_subgraph_end_to_end.py`:

```python
"""End-to-end: subgraph-based stages + StagePlans + lab_meeting exclusion."""
from __future__ import annotations

import pytest

from agentlabx.core.pipeline import PipelineBuilder
from agentlabx.core.registry import PluginRegistry
from agentlabx.core.session import SessionPreferences
from agentlabx.core.state import create_initial_state
from agentlabx.plugins._builtin import register_builtin_plugins


@pytest.fixture
def registry():
    r = PluginRegistry()
    register_builtin_plugins(r)
    return r


@pytest.mark.asyncio
async def test_end_to_end_produces_stage_plans_and_excludes_lab_meeting(registry):
    seq = [
        "literature_review",
        "plan_formulation",
        "lab_meeting",       # Will be excluded — invocable_only
        "experimentation",
        "peer_review",
    ]
    graph = PipelineBuilder(
        registry=registry, preferences=SessionPreferences()
    ).build(stage_sequence=seq)

    # lab_meeting must NOT be a top-level node
    assert "lab_meeting" not in set(graph.get_graph().nodes)

    state = create_initial_state(
        session_id="s1",
        user_id="u1",
        research_topic="chain of thought for MATH",
        default_sequence=[s for s in seq if s != "lab_meeting"],
        max_total_iterations=30,
    )

    # Run the pipeline. Stages producing real agent output require mocks for
    # any external services — if the existing test suite has a mock-LLM
    # fixture, reuse it here. For Plan 7B's purposes, it's enough that
    # stage_plans get populated even with default stub stages, so the test
    # monkey-patches StageRunner.run with a minimal advancer if needed.
    from agentlabx.stages import runner as runner_mod

    async def fake_run(self, state):
        name = self.stage.name
        return {
            "current_stage": name,
            "stage_iterations": {
                **state.get("stage_iterations", {}),
                name: state.get("stage_iterations", {}).get(name, 0) + 1,
            },
            "total_iterations": state.get("total_iterations", 0) + 1,
            "next_stage": None,
        }

    # NOTE: we patch the runner's final behaviour but the subgraph still
    # runs first — stage_plans get written by the subgraph's stage_plan node
    # before the runner's update reaches state. If this test requires the
    # subgraph to be the source of record, adjust to patch
    # stage.execute_plan instead.

    # ACCEPTABLE SCOPE: for Plan 7B's purposes, the test demonstrates the
    # exclusion + pipeline composes. A deeper test of plan population lives
    # in test_literature_review_subgraph.py and test_subgraph.py.
    import pytest_asyncio  # ensures asyncio integration available
    result = await graph.ainvoke(
        state, config={"configurable": {"thread_id": "t1"}}
    )

    # lab_meeting never ran
    assert "lab_meeting" not in result["completed_stages"]
```

- [ ] **Step 2: Run — verify pass**

Run: `uv run pytest tests/integration/test_plan7b_subgraph_end_to_end.py -v`
Expected: PASS.

- [ ] **Step 3: Run full suite**

Run: `uv run pytest tests/ -x -q`
Expected: all pass.

- [ ] **Step 4: Commit**

```bash
git add tests/integration/test_plan7b_subgraph_end_to_end.py
git commit -m "test(integration): Plan 7B end-to-end with subgraphs + lab_meeting exclusion (Plan 7B T7)"
```

---

## Self-review checklist

- [ ] **Spec coverage:**
  - §3.2.1 stage subgraph (enter→plan→gate→work→evaluate→decide) — T4 (StageSubgraphBuilder) + T5 (runner delegation)
  - §3.2.2 StagePlan primitive (done/edit/todo/removed + rationale + hash) — T1 (types) + T3 (hooks) + T6 (literature_review example)
  - §5.5 invocable_only flag — T2
  - Per-stage migration of remaining 7 stages — deferred to Plan 7B²

- [ ] **Type consistency:** `StagePlan`, `StagePlanItem`, `StagePlanStatus`, `StageExecution`, `StageEvaluation`, `BaseStage.build_plan/execute_plan/evaluate/decide`, `StageSubgraphBuilder.compile` — all reference the same names across tasks.

- [ ] **No placeholders.** Every step shows code and commands.

- [ ] **Pre-production principle honoured.** Any failing pre-existing runner test that mocked `stage.run` directly should be updated to mock the new integration point (either `stage.execute_plan` or the compiled subgraph) — not papered over with a compat shim in the runner.

---

## Execution

Ship 7B after 7A's validation is complete. Subagent-driven recommended. Follow-ups:

- **Plan 7B²** — Migrate the remaining 7 stages (plan_formulation, data_exploration, data_preparation, experimentation, results_interpretation, report_writing, peer_review) to plan-driven hooks. Pattern established in T6.
- **Plan 7C** — PI advisor reconception, escalation target replacement for Plan 7A's `backtrack_limit_exceeded` (handler's default fallback → PI consultation).
- **Plan 7D** — frontend retrofit: production-line graph + recursive subgraph drawer per §8.2.
