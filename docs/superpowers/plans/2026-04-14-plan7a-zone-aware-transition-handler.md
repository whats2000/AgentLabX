# Plan 7A: Zone-Aware Transition Handler + Backtrack Retry Governance

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Rework the pipeline's transition handler to understand zones (Discovery/Implementation/Synthesis), apply partial rollback on backtracks (preserving hypotheses, experiment_log, agent_memory), and enforce per-edge retry counters plus a global backtrack-cost fraction to prevent runaway loops.

**Architecture:** The transition handler gains a rule-based priority chain — human override → hard limits → backtrack retry/cost gate → zone-aware HITL approval → default sequence. Stages declare their zone as a class attribute, resolved through a single `agentlabx/core/zones.py` module. An `apply_partial_rollback` helper in `agentlabx/core/state.py` returns a partial state update that rewinds only `current_stage`, `next_stage`, and attaches `backtrack_feedback`; hypotheses, experiment_log, completed_stages, cost_tracker, and agent_memory are preserved. On escalation (per-edge limit or cost-fraction exceeded), `TransitionHandler.decide()` owns the fallback — it returns a concrete `next_stage` rather than a null-out, so `transition_node` just applies the decision.

**Tech Stack:** Python 3.11+, LangGraph, Pydantic v2, pytest-asyncio. No new dependencies.

**Pre-production principle (project-wide):** AgentLabX has not shipped a stable release. Plan 7A is free to make breaking changes — update existing tests when behaviour changes, do not add backwards-compat scaffolding. If a test pins the old behaviour (e.g., empty `transition_log`), rewrite the test.

**Spec sections implemented:** §3.3.1 decision flow, §3.3.2 partial rollback, §3.3.3 zone-aware routing, §3.3.7 retry governance.

**Companion spec:** `docs/superpowers/specs/2026-04-12-agentlabx-platform-design.md` §3.3.

**Out of scope (later plans):**
- StagePlan primitive + stages as LangGraph subgraphs (Plan 7B)
- `invocable_only` flag + lab_meeting exclusion from top-level graph wiring (Plan 7B)
- PI advisor reconception + PI-driven escalation (Plan 7C)
- Frontend (production-line graph + subgraph drawer, mermaid swap) (Plan 7D)

---

## File structure

| File | Purpose | Create / Modify |
|---|---|---|
| `agentlabx/stages/base.py` | Add `zone: ClassVar[str \| None]` to `BaseStage` | Modify |
| `agentlabx/stages/{literature_review,plan_formulation,data_exploration,data_preparation,experimentation,results_interpretation,report_writing,peer_review}.py` | Bare `zone = "<discovery\|implementation\|synthesis>"` on each | Modify |
| `agentlabx/stages/lab_meeting.py` | `zone = None` (cross-zone collaboration, Plan 7B will also mark invocable_only) | Modify |
| `agentlabx/core/zones.py` | Single source for zone resolution; `zone_for(name, registry=None)` with hardcoded fallback for registry-less callers | Create |
| `agentlabx/core/graph_mapper.py` | Call `core/zones.zone_for(...)` instead of the hardcoded dict; surface `backtrack_attempts` on edges | Modify |
| `agentlabx/server/routes/sessions.py` | Pass the app's registry into `build_topology` | Modify |
| `agentlabx/core/state.py` | Add `backtrack_attempts`, `backtrack_cost_spent`, `backtrack_feedback` keys; add `apply_partial_rollback` helper | Modify |
| `agentlabx/core/session.py` | Extend `SessionPreferences` with `max_backtrack_attempts_per_edge`, `max_backtrack_cost_fraction` | Modify |
| `agentlabx/stages/runner.py` | Snapshot `cost_tracker.total_cost` on entry; on backtrack status, write `backtrack_feedback` and add cost delta to `backtrack_cost_spent` | Modify |
| `agentlabx/stages/transition.py` | Tighten `action` to `Literal`; add retry/cost gate; zone-aware approval via `core/zones`; `decide()` owns escalation fallback | Modify |
| `agentlabx/core/pipeline.py` | `transition_node` uses `apply_partial_rollback`, increments counters, clears feedback on advance, appends `transition_log`, applies escalation route | Modify |
| `tests/core/test_zones.py` | Zone resolver unit tests | Create |
| `tests/core/test_state.py` | `apply_partial_rollback` + new state-key initial values | Create |
| `tests/core/test_session_preferences.py` | Retry-governance preference fields | Create |
| `tests/stages/test_base_zone.py` | All registered stages declare valid zones | Create |
| `tests/stages/test_runner_backtrack_cost.py` | StageRunner snapshots + delta on backtrack; feedback written | Create |
| `tests/stages/test_transition_retry.py` | Per-edge counter + cost-fraction gate + escalation fallback | Create |
| `tests/stages/test_transition_zone.py` | Zone-aware approval defaults + per-stage overrides | Create |
| `tests/core/test_pipeline_backtrack.py` | End-to-end: backtrack → counter increment → partial rollback → transition_log append | Create |
| `tests/core/test_graph_mapper.py` | Extend: backtrack attempts surface on edges | Modify |

---

## Task 1: Zone metadata on stages + `core/zones.py` single source + registry plumbing

**Files:**
- Modify: `agentlabx/stages/base.py` — add `zone: ClassVar[str | None] = None`
- Modify: each of 9 stage files — bare `zone = "..."`
- Create: `agentlabx/core/zones.py`
- Modify: `agentlabx/core/graph_mapper.py`
- Modify: `agentlabx/server/routes/sessions.py`
- Create: `tests/core/test_zones.py`, `tests/stages/test_base_zone.py`

- [ ] **Step 1: Write failing `test_base_zone.py`**

Create `tests/stages/test_base_zone.py`:

```python
"""Every registered stage must declare a valid zone."""
import pytest
from agentlabx.core.registry import PluginRegistry, PluginType
from agentlabx.plugins import _builtin

STAGE_ZONE_EXPECTATIONS = {
    "literature_review": "discovery",
    "plan_formulation": "discovery",
    "data_exploration": "implementation",
    "data_preparation": "implementation",
    "experimentation": "implementation",
    "results_interpretation": "synthesis",
    "report_writing": "synthesis",
    "peer_review": "synthesis",
    "lab_meeting": None,
}


@pytest.fixture
def registry() -> PluginRegistry:
    r = PluginRegistry()
    _builtin.register_builtin_plugins(r)
    return r


def test_every_registered_stage_declares_expected_zone(registry: PluginRegistry):
    for name, expected in STAGE_ZONE_EXPECTATIONS.items():
        cls = registry.resolve(PluginType.STAGE, name)
        assert cls.zone == expected, (
            f"{name}.zone={cls.zone!r} expected {expected!r}"
        )
```

- [ ] **Step 2: Write failing `test_zones.py`**

Create `tests/core/test_zones.py`:

```python
"""zone_for(): single source of zone resolution."""
import pytest
from agentlabx.core.registry import PluginRegistry
from agentlabx.core.zones import zone_for
from agentlabx.plugins import _builtin


@pytest.fixture
def registry() -> PluginRegistry:
    r = PluginRegistry()
    _builtin.register_builtin_plugins(r)
    return r


def test_zone_for_reads_class_attribute_when_registry_given(registry):
    assert zone_for("literature_review", registry) == "discovery"
    assert zone_for("experimentation", registry) == "implementation"
    assert zone_for("peer_review", registry) == "synthesis"
    assert zone_for("lab_meeting", registry) is None


def test_zone_for_falls_back_to_hardcoded_map_when_registry_none():
    # Registry-less callers (tests, graph_mapper fixtures) still resolve.
    assert zone_for("literature_review", None) == "discovery"
    assert zone_for("experimentation", None) == "implementation"
    assert zone_for("peer_review", None) == "synthesis"


def test_zone_for_returns_none_on_unknown_stage():
    assert zone_for("not_a_stage", None) is None
```

- [ ] **Step 3: Run both tests to verify they fail**

Run: `uv run pytest tests/core/test_zones.py tests/stages/test_base_zone.py -v`
Expected: FAIL (module missing + zone attribute missing).

- [ ] **Step 4: Add `zone` to `BaseStage`**

In `agentlabx/stages/base.py` add imports and attribute:

```python
from typing import ClassVar, Literal

ZoneName = Literal["discovery", "implementation", "synthesis"]


class BaseStage(ABC):
    name: str
    description: str
    required_agents: list[str]
    required_tools: list[str]
    zone: ClassVar[ZoneName | None] = None  # None = cross-zone / special
    ...
```

- [ ] **Step 5: Set `zone` on every concrete stage**

In each stage file, add a bare class-level attribute under `name` (matches existing `name = "..."` convention):

- `literature_review.py`: `zone = "discovery"`
- `plan_formulation.py`: `zone = "discovery"`
- `data_exploration.py`: `zone = "implementation"`
- `data_preparation.py`: `zone = "implementation"`
- `experimentation.py`: `zone = "implementation"`
- `results_interpretation.py`: `zone = "synthesis"`
- `report_writing.py`: `zone = "synthesis"`
- `peer_review.py`: `zone = "synthesis"`
- `lab_meeting.py`: `zone = None`

- [ ] **Step 6: Create `agentlabx/core/zones.py`**

```python
"""Single source of zone resolution for stages.

Stages declare `zone` as a ClassVar on BaseStage subclasses. This module
resolves a stage name to its zone, preferring the class attribute (via the
registry) but falling back to a hardcoded map for registry-less callers
(tests, /graph fixtures, any code that can't easily plumb a registry).
"""
from __future__ import annotations

from typing import TYPE_CHECKING, Literal

if TYPE_CHECKING:
    from agentlabx.core.registry import PluginRegistry

ZoneName = Literal["discovery", "implementation", "synthesis"]

# Fallback map kept in sync with the class-level `zone` attributes on the
# concrete stage classes. Tests verify the two agree.
_FALLBACK_ZONES: dict[str, ZoneName | None] = {
    "literature_review": "discovery",
    "plan_formulation": "discovery",
    "data_exploration": "implementation",
    "data_preparation": "implementation",
    "experimentation": "implementation",
    "results_interpretation": "synthesis",
    "report_writing": "synthesis",
    "peer_review": "synthesis",
    "lab_meeting": None,
}


def zone_for(stage_name: str, registry: PluginRegistry | None = None) -> ZoneName | None:
    """Return the zone declared by `stage_name`, or None for special/unknown."""
    if registry is not None:
        try:
            from agentlabx.core.registry import PluginType

            cls = registry.resolve(PluginType.STAGE, stage_name)
            return getattr(cls, "zone", None)
        except Exception:
            pass
    return _FALLBACK_ZONES.get(stage_name)


def cross_zone(origin: str, target: str, registry: PluginRegistry | None = None) -> bool:
    """True iff origin and target declare different non-null zones, OR either is None.

    Treating a None zone (lab_meeting, unknown) as cross-zone is conservative:
    HITL rules in TransitionHandler will apply approval unless the operator
    opts out via per-stage controls.
    """
    a = zone_for(origin, registry)
    b = zone_for(target, registry)
    if a is None or b is None:
        return True
    return a != b
```

- [ ] **Step 7: Update `graph_mapper.py` to use `zone_for`**

In `agentlabx/core/graph_mapper.py`:
- Delete the module-level `STAGE_ZONES` dict
- Add parameter: `def build_topology(compiled_graph, state, registry=None)`
- Replace `STAGE_ZONES.get(nid)` with `zone_for(nid, registry)`
- Import: `from agentlabx.core.zones import zone_for`

- [ ] **Step 8: Update `routes/sessions.py` to pass the app's registry**

Find the `/graph` endpoint handler and locate the `build_topology(...)` call. Update it to pass the registry from the app context:

```python
# Before:
topology = build_topology(compiled, state)

# After:
topology = build_topology(compiled, state, registry=app_ctx.registry)
```

(The exact attribute name on `app_ctx` is whatever the existing handler already uses — grep for it.)

- [ ] **Step 9: Run all tests for this task**

Run: `uv run pytest tests/stages/test_base_zone.py tests/core/test_zones.py tests/core/test_graph_mapper.py -v`
Expected: all pass.

- [ ] **Step 10: Commit**

```bash
git add agentlabx/stages/base.py agentlabx/stages/literature_review.py agentlabx/stages/plan_formulation.py agentlabx/stages/data_exploration.py agentlabx/stages/data_preparation.py agentlabx/stages/experimentation.py agentlabx/stages/results_interpretation.py agentlabx/stages/report_writing.py agentlabx/stages/peer_review.py agentlabx/stages/lab_meeting.py agentlabx/core/zones.py agentlabx/core/graph_mapper.py agentlabx/server/routes/sessions.py tests/stages/test_base_zone.py tests/core/test_zones.py
git commit -m "feat(zones): unified zone resolution + per-stage metadata (Plan 7A T1)"
```

---

## Task 2: Retry-governance state keys

**Files:**
- Modify: `agentlabx/core/state.py`
- Create: `tests/core/test_state.py`

- [ ] **Step 1: Write failing test**

Create `tests/core/test_state.py`:

```python
from agentlabx.core.state import create_initial_state


def test_initial_state_has_backtrack_tracking_fields():
    state = create_initial_state(
        session_id="s1", user_id="u1", research_topic="t"
    )
    assert state["backtrack_attempts"] == {}
    assert state["backtrack_cost_spent"] == 0.0
    assert state["backtrack_feedback"] is None


def test_backtrack_attempts_uses_edge_string_keys():
    # "origin->target" string keys (tuple keys aren't JSON-serializable,
    # and LangGraph's checkpointer requires JSON-safe state).
    state = create_initial_state(
        session_id="s1", user_id="u1", research_topic="t"
    )
    state["backtrack_attempts"]["experimentation->literature_review"] = 2
    assert (
        state["backtrack_attempts"]["experimentation->literature_review"] == 2
    )
```

- [ ] **Step 2: Run — verify fail**

Run: `uv run pytest tests/core/test_state.py -v`
Expected: FAIL — `KeyError: 'backtrack_attempts'`.

- [ ] **Step 3: Extend `PipelineState` + `create_initial_state`**

In `agentlabx/core/state.py`, in `PipelineState` below the Plan 6 observability block:

```python
    # Backtrack governance (Plan 7A)
    # Keys are "origin_stage->target_stage" strings; tuple keys aren't
    # JSON-serializable and LangGraph's checkpointer needs JSON-safe state.
    backtrack_attempts: dict[str, int]
    backtrack_cost_spent: float
    backtrack_feedback: str | None
```

And in `create_initial_state`:

```python
        backtrack_attempts={},
        backtrack_cost_spent=0.0,
        backtrack_feedback=None,
```

- [ ] **Step 4: Run — verify pass**

Run: `uv run pytest tests/core/test_state.py -v`
Expected: 2 PASS.

- [ ] **Step 5: Commit**

```bash
git add agentlabx/core/state.py tests/core/test_state.py
git commit -m "feat(state): backtrack retry/cost/feedback state keys (Plan 7A T2)"
```

---

## Task 3: `apply_partial_rollback` helper

**Files:**
- Modify: `agentlabx/core/state.py` (append helper)
- Modify: `tests/core/test_state.py` (extend)

- [ ] **Step 1: Extend `tests/core/test_state.py` with failing rollback tests**

Append:

```python
from datetime import datetime

from agentlabx.core.state import (
    Hypothesis,
    apply_partial_rollback,
    create_initial_state,
)


def test_apply_partial_rollback_preserves_hypotheses_and_experiment_log():
    state = create_initial_state(
        session_id="s1", user_id="u1", research_topic="t"
    )
    state["current_stage"] = "experimentation"
    state["next_stage"] = None
    state["completed_stages"] = [
        "literature_review",
        "plan_formulation",
        "data_exploration",
        "data_preparation",
    ]
    state["hypotheses"] = [
        Hypothesis(
            id="H1",
            statement="X improves Y",
            status="active",
            created_at_stage="plan_formulation",
        )
    ]
    state["experiment_log"] = [
        {
            "attempt_id": "a1",
            "approach_summary": "baseline",
            "outcome": "failure",
            "failure_reason": "OOM",
            "learnings": [],
            "linked_hypothesis_id": "H1",
            "ts": datetime.now(),
        }
    ]
    state["agent_memory"] = {
        "ml_engineer": {
            "working_memory": {"k": "v"},
            "notes": ["n1"],
            "last_active_stage": "experimentation",
            "turn_count": 5,
        }
    }

    update = apply_partial_rollback(
        state, target="literature_review", feedback="Missing RL methods"
    )

    # Partial update shape: ONLY the rewound fields present.
    assert set(update.keys()) == {
        "current_stage",
        "next_stage",
        "backtrack_feedback",
    }
    assert update["current_stage"] == "literature_review"
    assert update["next_stage"] is None
    assert update["backtrack_feedback"] == "Missing RL methods"
```

- [ ] **Step 2: Run — verify fail**

Run: `uv run pytest tests/core/test_state.py::test_apply_partial_rollback_preserves_hypotheses_and_experiment_log -v`
Expected: FAIL — helper not defined.

- [ ] **Step 3: Implement `apply_partial_rollback`**

Append to `agentlabx/core/state.py`:

```python
def apply_partial_rollback(
    state: PipelineState, *, target: str, feedback: str | None
) -> dict[str, Any]:
    """Return a partial state update rewinding `current_stage` to `target`.

    Deliberately returns only the three keys to overwrite. LangGraph's
    node-return merge semantics leave every other field untouched —
    hypotheses, experiment_log, experiment_results, completed_stages,
    cost_tracker, and agent_memory are preserved.

    Real labs don't forget what they've learned when they revisit an earlier
    stage (spec §3.3.2).
    """
    return {
        "current_stage": target,
        "next_stage": None,
        "backtrack_feedback": feedback,
    }
```

- [ ] **Step 4: Run — verify pass**

Run: `uv run pytest tests/core/test_state.py -v`
Expected: 3 PASS total.

- [ ] **Step 5: Commit**

```bash
git add agentlabx/core/state.py tests/core/test_state.py
git commit -m "feat(state): apply_partial_rollback helper (Plan 7A T3)"
```

---

## Task 4: SessionPreferences retry-governance knobs

**Files:**
- Modify: `agentlabx/core/session.py`
- Create: `tests/core/test_session_preferences.py`

- [ ] **Step 1: Write failing test**

Create `tests/core/test_session_preferences.py`:

```python
from agentlabx.core.session import SessionPreferences


def test_retry_governance_defaults():
    p = SessionPreferences()
    assert p.max_backtrack_attempts_per_edge == 2
    assert p.max_backtrack_cost_fraction == 0.4


def test_retry_governance_overrides():
    p = SessionPreferences(
        max_backtrack_attempts_per_edge=5,
        max_backtrack_cost_fraction=0.6,
    )
    assert p.max_backtrack_attempts_per_edge == 5
    assert p.max_backtrack_cost_fraction == 0.6
```

- [ ] **Step 2: Run — verify fail**

Run: `uv run pytest tests/core/test_session_preferences.py -v`
Expected: FAIL — fields unknown.

- [ ] **Step 3: Add fields to `SessionPreferences`**

In `agentlabx/core/session.py` inside the `SessionPreferences(BaseModel)` class:

```python
    max_backtrack_attempts_per_edge: int = 2
    max_backtrack_cost_fraction: float = 0.4
```

- [ ] **Step 4: Run — verify pass**

Run: `uv run pytest tests/core/test_session_preferences.py -v`
Expected: 2 PASS.

- [ ] **Step 5: Commit**

```bash
git add agentlabx/core/session.py tests/core/test_session_preferences.py
git commit -m "feat(session): retry-governance preference knobs (Plan 7A T4)"
```

---

## Task 5: StageRunner — backtrack feedback + cost delta

**Files:**
- Modify: `agentlabx/stages/runner.py`
- Create: `tests/stages/test_runner_backtrack_cost.py`

On entry, snapshot `state["cost_tracker"].total_cost` into a local. When the stage returns with `status == "backtrack"`, compute the delta against the now-mutated `state["cost_tracker"].total_cost` and accumulate into `backtrack_cost_spent`. Also copy `StageResult.feedback` into `backtrack_feedback`.

- [ ] **Step 1: Write failing test**

Create `tests/stages/test_runner_backtrack_cost.py`:

```python
"""StageRunner accumulates backtrack cost + plumbs feedback into state."""
import pytest
from unittest.mock import AsyncMock

from agentlabx.core.state import CostTracker, create_initial_state
from agentlabx.stages.base import BaseStage, StageContext, StageResult
from agentlabx.stages.runner import StageRunner


class _FakeStage(BaseStage):
    name = "fake"
    description = "fake"
    required_agents: list[str] = []
    required_tools: list[str] = []
    zone = "discovery"

    def __init__(self, cost_delta: float, status: str, feedback: str | None):
        self._cost_delta = cost_delta
        self._status = status
        self._feedback = feedback

    async def run(self, state, context):
        # Simulate the stage incurring cost during its run
        state["cost_tracker"].add_usage(
            tokens_in=100, tokens_out=50, cost=self._cost_delta
        )
        return StageResult(
            output={},
            status=self._status,
            next_hint="literature_review" if self._status == "backtrack" else None,
            reason="test",
            feedback=self._feedback,
        )


@pytest.mark.asyncio
async def test_backtrack_status_accumulates_cost_delta_and_writes_feedback():
    state = create_initial_state(
        session_id="s1", user_id="u1", research_topic="t"
    )
    state["current_stage"] = "experimentation"
    state["cost_tracker"] = CostTracker(total_cost=10.0)

    runner = StageRunner(
        _FakeStage(cost_delta=3.5, status="backtrack", feedback="need RL methods"),
        context=StageContext(settings={}, event_bus=None, registry=None),
    )
    update = await runner.run(state)

    assert update["backtrack_cost_spent"] == pytest.approx(3.5)
    assert update["backtrack_feedback"] == "need RL methods"


@pytest.mark.asyncio
async def test_non_backtrack_status_does_not_accumulate_or_write():
    state = create_initial_state(
        session_id="s1", user_id="u1", research_topic="t"
    )
    state["current_stage"] = "experimentation"
    state["cost_tracker"] = CostTracker(total_cost=10.0)

    runner = StageRunner(
        _FakeStage(cost_delta=5.0, status="done", feedback=None),
        context=StageContext(settings={}, event_bus=None, registry=None),
    )
    update = await runner.run(state)

    assert "backtrack_cost_spent" not in update
    assert "backtrack_feedback" not in update
```

- [ ] **Step 2: Run — verify fail**

Run: `uv run pytest tests/stages/test_runner_backtrack_cost.py -v`
Expected: FAIL — new behaviour absent.

- [ ] **Step 3: Update `StageRunner.run`**

In `agentlabx/stages/runner.py`, modify `run`:

- Just before calling `self.stage.run(...)`:

```python
        # Snapshot cost_tracker.total_cost for backtrack-cost accounting
        cost_tracker = state.get("cost_tracker")
        cost_at_entry = float(cost_tracker.total_cost) if cost_tracker else 0.0
```

- After a successful `result = await self.stage.run(...)`, inside the success branch (before emitting `stage_completed`):

```python
            # Backtrack-specific state plumbing (Plan 7A)
            if result.status == "backtrack":
                # Feedback handoff: the target stage will read this on re-entry
                update["backtrack_feedback"] = result.feedback

                # Cost attribution: the cost of this run led to the backtrack
                current_total = (
                    float(state["cost_tracker"].total_cost)
                    if state.get("cost_tracker") else 0.0
                )
                delta = max(0.0, current_total - cost_at_entry)
                prior = float(state.get("backtrack_cost_spent", 0.0))
                update["backtrack_cost_spent"] = prior + delta
```

- [ ] **Step 4: Run — verify pass**

Run: `uv run pytest tests/stages/test_runner_backtrack_cost.py -v`
Expected: 2 PASS.

- [ ] **Step 5: Run full stages suite for regression**

Run: `uv run pytest tests/stages/ -v`
Expected: all pass (update any pre-existing runner tests that asserted a keyset not containing these new keys — see pre-production principle).

- [ ] **Step 6: Commit**

```bash
git add agentlabx/stages/runner.py tests/stages/test_runner_backtrack_cost.py
git commit -m "feat(runner): plumb backtrack feedback + cost delta to state (Plan 7A T5)"
```

---

## Task 6: TransitionHandler — retry gate + escalation fallback + `Literal` action

**Files:**
- Modify: `agentlabx/stages/transition.py`
- Create: `tests/stages/test_transition_retry.py`

`TransitionDecision.action` tightens to a `Literal`. New priority 3 gate runs when the hint is a backtrack: if `backtrack_attempts[edge] >= max_per_edge` OR `cost_spent / total_cost >= max_fraction`, the handler escalates — but **it owns the fallback** by computing `_next_in_sequence(...)` itself and returning a concrete `next_stage` with `action="backtrack_limit_exceeded"`. `transition_node` just applies the decision (T8); no private-helper leak.

- [ ] **Step 1: Write failing test**

Create `tests/stages/test_transition_retry.py`:

```python
"""Retry gate: per-edge limit + cost fraction, with decide() owning fallback."""
from agentlabx.core.session import SessionPreferences
from agentlabx.core.state import CostTracker, create_initial_state
from agentlabx.stages.transition import TransitionHandler


def _state(current="experimentation", hint="literature_review"):
    s = create_initial_state(
        session_id="s1",
        user_id="u1",
        research_topic="t",
        default_sequence=[
            "literature_review",
            "plan_formulation",
            "experimentation",
            "peer_review",
        ],
    )
    s["current_stage"] = current
    s["next_stage"] = hint
    return s


def test_within_per_edge_limit_backtracks():
    s = _state()
    s["backtrack_attempts"] = {"experimentation->literature_review": 1}

    h = TransitionHandler(
        preferences=SessionPreferences(max_backtrack_attempts_per_edge=2)
    )
    d = h.decide(s)

    assert d.action == "backtrack"
    assert d.next_stage == "literature_review"


def test_at_per_edge_limit_escalates_with_concrete_fallback_target():
    s = _state()
    s["backtrack_attempts"] = {"experimentation->literature_review": 2}

    h = TransitionHandler(
        preferences=SessionPreferences(max_backtrack_attempts_per_edge=2)
    )
    d = h.decide(s)

    assert d.action == "backtrack_limit_exceeded"
    assert d.needs_approval is True
    assert d.next_stage == "peer_review"  # next-in-sequence after experimentation
    assert "per-edge" in d.reason.lower()


def test_cost_fraction_exceeded_escalates_with_fallback():
    s = _state()
    s["backtrack_attempts"] = {"experimentation->literature_review": 0}
    s["backtrack_cost_spent"] = 100.0
    s["cost_tracker"] = CostTracker(total_cost=200.0)  # 50% > 0.4

    h = TransitionHandler(
        preferences=SessionPreferences(
            max_backtrack_attempts_per_edge=5,
            max_backtrack_cost_fraction=0.4,
        )
    )
    d = h.decide(s)

    assert d.action == "backtrack_limit_exceeded"
    assert d.next_stage == "peer_review"
    assert "cost" in d.reason.lower()


def test_zero_budget_does_not_divide_by_zero():
    s = _state()
    s["backtrack_attempts"] = {}
    s["cost_tracker"] = CostTracker()  # total_cost = 0

    h = TransitionHandler(
        preferences=SessionPreferences(max_backtrack_cost_fraction=0.4)
    )
    d = h.decide(s)

    assert d.action == "backtrack"
    assert d.next_stage == "literature_review"
```

- [ ] **Step 2: Run — verify fail**

Run: `uv run pytest tests/stages/test_transition_retry.py -v`
Expected: FAIL.

- [ ] **Step 3: Update `transition.py`**

Tighten `TransitionDecision`:

```python
from typing import Literal


class TransitionDecision(BaseModel):
    next_stage: str | None
    action: Literal[
        "advance",
        "backtrack",
        "forced_advance",
        "complete",
        "human_override",
        "backtrack_limit_exceeded",
    ]
    reason: str
    needs_approval: bool = False
```

Update the `TransitionHandler` class docstring's priority list to reflect the new gate:

```
Priority:
1. human_override
2. total_iterations >= max_total_iterations → complete
3. backtrack requested + (per-edge attempts OR cost fraction exceeded)
   → backtrack_limit_exceeded (handler owns fallback, returns concrete next_stage)
4. stage iteration limit reached + next_stage hint → forced_advance
5. next_stage hint within stage limit → follow hint (backtrack or advance)
6. no hint → advance to next uncompleted stage in default_sequence
7. all stages complete → complete
```

Insert the new Priority 3 block between the existing Priority 2 and the "stage iteration limit" check. Inside `decide`:

```python
        # ── Priority 3: backtrack retry/cost gate (Plan 7A) ──────────────
        if next_hint is not None and self._is_backtrack(
            next_hint, current_stage, default_sequence
        ):
            edge_key = f"{current_stage}->{next_hint}"
            attempts = state.get("backtrack_attempts", {}).get(edge_key, 0)
            per_edge_limit = self.preferences.max_backtrack_attempts_per_edge

            escalate_reason: str | None = None
            if attempts >= per_edge_limit:
                escalate_reason = (
                    f"Per-edge backtrack limit reached for "
                    f"'{edge_key}' ({attempts}/{per_edge_limit})"
                )

            cost_tracker = state.get("cost_tracker")
            total_cost = float(cost_tracker.total_cost) if cost_tracker else 0.0
            cost_spent = float(state.get("backtrack_cost_spent", 0.0))
            if total_cost > 0.0 and escalate_reason is None:
                fraction = cost_spent / total_cost
                if fraction >= self.preferences.max_backtrack_cost_fraction:
                    escalate_reason = (
                        f"Cumulative backtrack cost fraction "
                        f"{fraction:.2f} >= limit "
                        f"{self.preferences.max_backtrack_cost_fraction:.2f}"
                    )

            if escalate_reason is not None:
                # Handler owns the fallback — compute next_in_sequence here
                # so transition_node just applies the decision.
                fallback = self._next_in_sequence(
                    current_stage, default_sequence, completed_stages
                )
                return TransitionDecision(
                    next_stage=fallback,
                    action="backtrack_limit_exceeded",
                    reason=escalate_reason,
                    needs_approval=True,
                )
```

- [ ] **Step 4: Run retry tests — verify pass**

Run: `uv run pytest tests/stages/test_transition_retry.py -v`
Expected: 4 PASS.

- [ ] **Step 5: Run full transition suite**

Run: `uv run pytest tests/stages/test_transition.py tests/stages/test_transition_retry.py -v`
Expected: all pass. If pre-existing tests relied on unconstrained `action` strings, update them (pre-production principle).

- [ ] **Step 6: Commit**

```bash
git add agentlabx/stages/transition.py tests/stages/test_transition_retry.py
git commit -m "feat(transition): retry gate + cost-fraction gate + Literal action (Plan 7A T6)"
```

---

## Task 7: Zone-aware HITL approval

**Files:**
- Modify: `agentlabx/stages/transition.py`
- Create: `tests/stages/test_transition_zone.py`

- [ ] **Step 1: Write failing test**

Create `tests/stages/test_transition_zone.py`:

```python
"""Zone-aware HITL approval (spec §3.3.3).

Defaults:
  within-zone forward/backtrack → silent (no approval)
  cross-zone forward             → silent (notify only, no approval)
  cross-zone backtrack           → approval required
Per-stage controls override ('approve'/'edit' always approve; 'auto' never).
"""
from agentlabx.core.session import SessionPreferences
from agentlabx.core.state import create_initial_state
from agentlabx.stages.transition import TransitionHandler


def _s(current, hint):
    s = create_initial_state(
        session_id="s1", user_id="u1", research_topic="t"
    )
    s["current_stage"] = current
    s["next_stage"] = hint
    return s


def test_within_zone_forward_no_approval():
    d = TransitionHandler().decide(_s("literature_review", "plan_formulation"))
    assert d.action == "advance"
    assert d.needs_approval is False


def test_within_zone_backtrack_no_approval():
    d = TransitionHandler().decide(_s("plan_formulation", "literature_review"))
    assert d.action == "backtrack"
    assert d.needs_approval is False


def test_cross_zone_backtrack_requires_approval():
    d = TransitionHandler().decide(_s("experimentation", "literature_review"))
    assert d.action == "backtrack"
    assert d.needs_approval is True


def test_cross_zone_forward_no_approval_by_default():
    d = TransitionHandler().decide(_s("plan_formulation", "data_exploration"))
    assert d.action == "advance"
    assert d.needs_approval is False


def test_stage_approve_control_wins_over_zone_default():
    prefs = SessionPreferences()
    prefs.stage_controls["literature_review"] = "approve"
    d = TransitionHandler(preferences=prefs).decide(
        _s("literature_review", "plan_formulation")
    )
    assert d.needs_approval is True


def test_stage_auto_control_wins_over_zone_default():
    prefs = SessionPreferences()
    prefs.stage_controls["experimentation"] = "auto"
    d = TransitionHandler(preferences=prefs).decide(
        _s("experimentation", "literature_review")
    )
    assert d.action == "backtrack"
    assert d.needs_approval is False
```

- [ ] **Step 2: Run — verify fail**

Run: `uv run pytest tests/stages/test_transition_zone.py -v`
Expected: several fail.

- [ ] **Step 3: Replace `_check_approval`**

In `agentlabx/stages/transition.py`:

```python
from agentlabx.core.zones import cross_zone


    def _check_approval(self, *, action: str, stage: str, target: str) -> bool:
        """Zone-aware HITL approval (spec §3.3.3).

        Per-stage control overrides (highest priority):
          "approve"/"edit" → always approve
          "auto"           → never approve
        Zone-aware defaults:
          advance          → no approval (notify only, even cross-zone)
          backtrack        → approve iff cross-zone OR backtrack_control=approve
        """
        sc = self.preferences.stage_controls.get(stage)
        if sc in ("approve", "edit"):
            return True
        if sc == "auto":
            return False

        if action == "backtrack":
            if self.preferences.backtrack_control == "approve":
                return True
            return cross_zone(stage, target)

        # advance / forced_advance / human_override default: no approval
        return False
```

- [ ] **Step 4: Run zone tests — verify pass**

Run: `uv run pytest tests/stages/test_transition_zone.py -v`
Expected: 6 PASS.

- [ ] **Step 5: Run full transition suite**

Run: `uv run pytest tests/stages/ -v`
Expected: all pass.

- [ ] **Step 6: Commit**

```bash
git add agentlabx/stages/transition.py tests/stages/test_transition_zone.py
git commit -m "feat(transition): zone-aware HITL approval via core/zones (Plan 7A T7)"
```

---

## Task 8: `transition_node` wiring — partial rollback, counter, log, feedback clear, escalation

**Files:**
- Modify: `agentlabx/core/pipeline.py`
- Create: `tests/core/test_pipeline_backtrack.py`

`transition_node` now:

1. Calls `handler.decide(state)`
2. On `backtrack` → merges `apply_partial_rollback(...)`, increments `backtrack_attempts[edge]`, does NOT clear `backtrack_feedback` (stage runner already wrote it)
3. On `advance` or `forced_advance` → clears `backtrack_feedback` and resets counters for edges originating at the now-completed stage
4. On `backtrack_limit_exceeded` → applies the concrete fallback from the decision (handler already owns it), logs an error
5. Appends one `Transition` record to `transition_log` on every decision (except `complete`)
6. Always appends `current` to `completed_stages`

- [ ] **Step 1: Write failing integration test**

Create `tests/core/test_pipeline_backtrack.py`:

```python
"""Backtrack round-trip: counter increment, partial rollback, transition_log."""
import pytest

from agentlabx.core.pipeline import PipelineBuilder
from agentlabx.core.registry import PluginRegistry
from agentlabx.core.session import SessionPreferences
from agentlabx.core.state import create_initial_state
from agentlabx.plugins import _builtin
from agentlabx.stages import runner as runner_mod
from agentlabx.stages.base import StageResult


@pytest.fixture
def registry():
    r = PluginRegistry()
    _builtin.register_builtin_plugins(r)
    return r


@pytest.mark.asyncio
async def test_backtrack_increments_counter_and_appends_transition_log(
    registry, monkeypatch
):
    # Stage 1: experimentation emits backtrack once, then done on re-run.
    calls = {"experimentation": 0}

    async def fake_run(self, state):
        name = self.stage.name
        update = {
            "current_stage": name,
            "stage_iterations": {
                **state.get("stage_iterations", {}),
                name: state.get("stage_iterations", {}).get(name, 0) + 1,
            },
            "total_iterations": state.get("total_iterations", 0) + 1,
        }
        if name == "experimentation":
            calls["experimentation"] += 1
            if calls["experimentation"] == 1:
                update["next_stage"] = "literature_review"
                update["backtrack_feedback"] = "need RL methods"
                return update
        update["next_stage"] = None
        return update

    monkeypatch.setattr(runner_mod.StageRunner, "run", fake_run)

    seq = ["literature_review", "plan_formulation", "experimentation"]
    graph = PipelineBuilder(
        registry=registry, preferences=SessionPreferences()
    ).build(stage_sequence=seq)

    state = create_initial_state(
        session_id="s1",
        user_id="u1",
        research_topic="t",
        default_sequence=seq,
        max_total_iterations=10,
    )

    result = await graph.ainvoke(
        state, config={"configurable": {"thread_id": "t1"}}
    )

    assert (
        result["backtrack_attempts"].get("experimentation->literature_review")
        == 1
    )
    # transition_log captures every transition including the backtrack
    kinds = [t.from_stage + "->" + t.to_stage for t in result["transition_log"]]
    assert "experimentation->literature_review" in kinds
```

- [ ] **Step 2: Run — verify fail**

Run: `uv run pytest tests/core/test_pipeline_backtrack.py -v`
Expected: FAIL.

- [ ] **Step 3: Replace `transition_node`**

In `agentlabx/core/pipeline.py` replace the `transition_node` function body:

```python
        def transition_node(state: PipelineState) -> dict[str, Any]:
            """Route to next stage; maintain counters, log, partial rollback."""
            from datetime import datetime

            from agentlabx.core.state import Transition, apply_partial_rollback

            decision = transition_handler.decide(state)
            current = state.get("current_stage", "")
            update: dict[str, Any] = {
                "next_stage": decision.next_stage,
                "human_override": None,
            }

            # completed_stages is a reducer (operator.add) field — append current
            if current:
                update["completed_stages"] = [current]

            if decision.action == "backtrack" and decision.next_stage:
                # Partial rollback: rewind current_stage + keep feedback; all
                # other state (hypotheses, experiment_log, etc.) preserved.
                rollback = apply_partial_rollback(
                    state,
                    target=decision.next_stage,
                    feedback=state.get("backtrack_feedback"),
                )
                update.update(rollback)

                # Per-edge counter increment
                edge_key = f"{current}->{decision.next_stage}"
                attempts = dict(state.get("backtrack_attempts", {}))
                attempts[edge_key] = attempts.get(edge_key, 0) + 1
                update["backtrack_attempts"] = attempts

            elif decision.action in ("advance", "forced_advance") and current:
                # Forward advance: clear any stale feedback, reset counters
                # for edges originating at the now-completed stage.
                update["backtrack_feedback"] = None
                attempts = dict(state.get("backtrack_attempts", {}))
                stale = [k for k in attempts if k.startswith(f"{current}->")]
                for k in stale:
                    attempts.pop(k, None)
                if stale:
                    update["backtrack_attempts"] = attempts

            elif decision.action == "backtrack_limit_exceeded":
                # Handler already computed a concrete fallback; apply it +
                # log an error explaining the escalation.
                update["backtrack_feedback"] = None
                from agentlabx.core.state import StageError

                update["errors"] = [
                    StageError(
                        stage=current,
                        error_type="backtrack_limit_exceeded",
                        message=decision.reason,
                        timestamp=datetime.now(),
                        recovered=False,
                    )
                ]

            # transition_log: append one entry per transition (except complete).
            if decision.action != "complete" and current and decision.next_stage:
                triggered_by_map = {
                    "human_override": "human",
                    "forced_advance": "system",
                    "backtrack_limit_exceeded": "system",
                    "advance": "agent",
                    "backtrack": "agent",
                }
                update["transition_log"] = [
                    Transition(
                        from_stage=current,
                        to_stage=decision.next_stage,
                        reason=decision.reason,
                        triggered_by=triggered_by_map.get(decision.action, "system"),
                        timestamp=datetime.now(),
                    )
                ]

            return update
```

- [ ] **Step 4: Run — verify pass**

Run: `uv run pytest tests/core/test_pipeline_backtrack.py -v`
Expected: PASS.

- [ ] **Step 5: Full-suite regression**

Run: `uv run pytest tests/ -x -q`
Expected: all pass. Update any pre-existing pipeline tests that asserted an empty `transition_log` or absence of the new keys (pre-production principle).

- [ ] **Step 6: Commit**

```bash
git add agentlabx/core/pipeline.py tests/core/test_pipeline_backtrack.py
git commit -m "feat(pipeline): partial rollback + counter + transition_log wiring (Plan 7A T8)"
```

---

## Task 9: Graph mapper — surface backtrack attempts on edges

**Files:**
- Modify: `agentlabx/core/graph_mapper.py`
- Modify: `tests/core/test_graph_mapper.py`

- [ ] **Step 1: Extend graph-mapper test**

Append to `tests/core/test_graph_mapper.py`:

```python
def test_graph_mapper_surfaces_backtrack_attempts_on_edges(
    compiled_graph_fixture,
):
    from agentlabx.core.state import create_initial_state

    state = create_initial_state(
        session_id="s1", user_id="u1", research_topic="t"
    )
    state["backtrack_attempts"] = {"experimentation->literature_review": 2}

    topo = build_topology(compiled_graph_fixture, state)

    backtrack_edges = [
        e for e in topo["edges"]
        if e.get("from") == "experimentation"
        and e.get("to") == "literature_review"
    ]
    assert backtrack_edges, "expected a backtrack edge to be surfaced"
    assert backtrack_edges[0].get("attempts") == 2
    assert backtrack_edges[0].get("kind") == "backtrack"
```

(If `compiled_graph_fixture` doesn't exist yet, add it — it should provide a compiled graph whose `get_graph()` yields nodes for the three stages used here. Mirror any existing fixture in the file.)

- [ ] **Step 2: Run — verify fail**

Run: `uv run pytest tests/core/test_graph_mapper.py::test_graph_mapper_surfaces_backtrack_attempts_on_edges -v`
Expected: FAIL.

- [ ] **Step 3: Update `build_topology`**

In `agentlabx/core/graph_mapper.py`, where the backtrack-edge overlay is constructed (the block that walks `state["transition_log"]`), also overlay any `backtrack_attempts` entries that don't already appear as a static edge — and for entries that do, annotate with `attempts` + `kind="backtrack"`:

```python
    attempts_map = state.get("backtrack_attempts") or {}
    for edge_key, count in attempts_map.items():
        try:
            src, dst = edge_key.split("->")
        except ValueError:
            continue
        # Merge with existing edge if one already matches; else append a new one.
        existing = next(
            (e for e in edges if e.get("from") == src and e.get("to") == dst),
            None,
        )
        if existing is not None:
            existing["attempts"] = count
            existing["kind"] = "backtrack"
        else:
            edges.append({
                "from": src,
                "to": dst,
                "kind": "backtrack",
                "attempts": count,
                "reason": None,
            })
```

- [ ] **Step 4: Run graph-mapper suite**

Run: `uv run pytest tests/core/test_graph_mapper.py -v`
Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add agentlabx/core/graph_mapper.py tests/core/test_graph_mapper.py
git commit -m "feat(graph): surface backtrack attempts on topology edges (Plan 7A T9)"
```

---

## Task 10: End-to-end integration test (replaces bash demo)

**Files:**
- Create: `tests/integration/test_plan7a_backtrack_governance.py`

One `pytest-asyncio` test that exercises the full backtrack loop via mock LLM: configure a stage to return two successive backtracks to the same target, assert the counter increments, assert the escalation fires on the third attempt with a concrete fallback target, assert `transition_log` + `errors` are populated.

- [ ] **Step 1: Write the test**

Create `tests/integration/test_plan7a_backtrack_governance.py`:

```python
"""End-to-end: backtrack governance — counter → escalation → fallback."""
import pytest

from agentlabx.core.pipeline import PipelineBuilder
from agentlabx.core.registry import PluginRegistry
from agentlabx.core.session import SessionPreferences
from agentlabx.core.state import create_initial_state
from agentlabx.plugins import _builtin
from agentlabx.stages import runner as runner_mod


@pytest.fixture
def registry():
    r = PluginRegistry()
    _builtin.register_builtin_plugins(r)
    return r


@pytest.mark.asyncio
async def test_per_edge_limit_escalates_and_forces_advance(registry, monkeypatch):
    # experimentation always requests backtrack to literature_review.
    async def fake_run(self, state):
        name = self.stage.name
        it = state.get("stage_iterations", {}).get(name, 0) + 1
        update = {
            "current_stage": name,
            "stage_iterations": {**state.get("stage_iterations", {}), name: it},
            "total_iterations": state.get("total_iterations", 0) + 1,
        }
        if name == "experimentation":
            update["next_stage"] = "literature_review"
            update["backtrack_feedback"] = "need more lit"
        else:
            update["next_stage"] = None
        return update

    monkeypatch.setattr(runner_mod.StageRunner, "run", fake_run)

    seq = [
        "literature_review",
        "plan_formulation",
        "experimentation",
        "peer_review",
    ]
    graph = PipelineBuilder(
        registry=registry,
        preferences=SessionPreferences(max_backtrack_attempts_per_edge=2),
    ).build(stage_sequence=seq)

    state = create_initial_state(
        session_id="s1",
        user_id="u1",
        research_topic="t",
        default_sequence=seq,
        max_total_iterations=30,
    )

    result = await graph.ainvoke(
        state, config={"configurable": {"thread_id": "t1"}}
    )

    # The per-edge gate must have escalated — errors contains the limit trip
    limit_errors = [
        e for e in result["errors"]
        if e.error_type == "backtrack_limit_exceeded"
    ]
    assert limit_errors, "expected a backtrack_limit_exceeded error"
    # The fallback target was peer_review — next in sequence after experimentation
    assert "peer_review" in result["completed_stages"]
```

- [ ] **Step 2: Run — verify pass**

Run: `uv run pytest tests/integration/test_plan7a_backtrack_governance.py -v`
Expected: PASS.

- [ ] **Step 3: Run full suite for final regression**

Run: `uv run pytest tests/ -x -q`
Expected: all pass.

- [ ] **Step 4: Commit**

```bash
git add tests/integration/test_plan7a_backtrack_governance.py
git commit -m "test(integration): end-to-end backtrack governance (Plan 7A T10)"
```

---

## Self-review checklist

- [ ] **Spec coverage**
  - §3.3.1 decision flow: new Priority 3 gate + `Literal` action (T6)
  - §3.3.2 partial rollback: helper (T3) + wired call (T8)
  - §3.3.3 zone-aware routing: `zone` on stages (T1), `core/zones.py` single source (T1), `_check_approval` rework (T7)
  - §3.3.7 retry governance: counters + cost-fraction + escalation fallback (T5, T6, T8)

- [ ] **No placeholders:** every step shows concrete code and concrete commands.

- [ ] **Type consistency:** `BaseStage.zone`, `ZoneName`, `TransitionDecision.action` `Literal` members, `SessionPreferences.max_backtrack_attempts_per_edge`, `apply_partial_rollback` signature — all referenced names match across tasks.

- [ ] **Pre-production principle honoured:** tests that pin old behaviour (empty `transition_log`, unconstrained `action` string) are updated in place rather than worked around.

---

## Execution

Ship 7A first and validate before writing 7B and 7C.

1. **Subagent-Driven (recommended)** — dispatch a fresh subagent per task with spec + code review after each
2. **Inline Execution** — batch execution in this session with checkpoints

Follow-ups:
- **Plan 7B** — StagePlan primitive + stages as LangGraph subgraphs (`enter → stage_plan → gate → work → evaluate → decide`) + `invocable_only` flag + lab_meeting exclusion from top-level wiring
- **Plan 7C** — PI advisor reconception: drop PIAgent-as-router; wire as ConfigAgent advisor at the four checkpoints; handle `backtrack_limit_exceeded` escalation (replace the default-sequence fallback with a PI consultation)
- **Plan 7D (frontend)** — production-line graph + subgraph drawer with recursive zoom; ChatView stage-grouped lazy-load; StagePlanCard; `StageSubgraphDrawer` with nested-invocation rendering (lab_meeting)
