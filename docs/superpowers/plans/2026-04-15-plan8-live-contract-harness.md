# Plan 8 — Live DFS Contract Harness Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build an opt-in live-model test harness that DFS-enumerates every pipeline decision path, verifies per-node input + output contracts against real Gemini-flash calls, and fixes the four known bugs (B1-B4) surfaced by the 2026-04-15 observation run plus any additional bugs the harness surfaces during authoring.

**Architecture:** Two-phase test suite under `tests/harness/`. Phase 1 builds a happy-path spine through all 8 stages with real state chaining, capturing per-station snapshots. Phase 2 loads snapshots and runs enumerated alternate-branch fork tests that steer via production HITL endpoint or context shaping. Contracts are pure functions over a `HarnessTrace` (events + state + HTTP + captured prompts). Marker `live_harness` gates all tests so default `pytest` invocation is unaffected.

**Tech Stack:** Python 3.11, pytest + pytest-asyncio, LiteLLM (Gemini provider via `AGENTLABX_LLM__DEFAULT_MODEL=gemini/gemini-2.5-flash`), httpx (WS + REST against FastAPI `TestClient` for the spine; real HTTP server for HITL forks), existing `PipelineExecutor` and event bus.

**Reference spec:** [2026-04-15-plan8-live-contract-harness-design.md](../specs/2026-04-15-plan8-live-contract-harness-design.md)

**Execution note:** Established AgentLabX pattern is to work on `main` with frequent commits. Follow that unless the executor requests a worktree.

**API-signature caveat for implementer.** Code sketches in this plan reference real modules but the exact signatures may have drifted since authoring. Before copying any sketch verbatim, check the current module (`agentlabx/server/executor.py`, `agentlabx/core/session.py`, `agentlabx/agents/config_agent.py`, `agentlabx/stages/subgraph.py`, etc.) for the actual method names and argument order. Signature mismatches are **mechanical auto-patches** — adjust the sketch, keep the test invariant, move on. Only the *intent* of each sketch (what contract/fixture/fix it implements) is load-bearing.

**Known module locations** (confirmed as of 2026-04-15):
- `PipelineExecutor` → `agentlabx/server/executor.py` (constructor takes `registry, session_manager, llm_provider, storage, checkpoint_db_path, event_forwarder`; starts session via `start_session(session: Session)` which runs pipeline in bg asyncio task)
- `Session` / `SessionManager` → `agentlabx/core/session.py`
- `StageContext` → `agentlabx/stages/base.py` (built inside executor's `start_session`)
- `build_pipeline` LangGraph builder → `agentlabx/core/pipeline.py` (the `run_pipeline` callable is an inner function at `server/executor.py:239`; completion logic — where B3 fix lives — is in the `finally`/exception-handling around that inner function)

**Halt-fix-retest discipline:** When a contract surfaces a bug (expected for B1-B4; likely for others):
- **Mechanical fix** (missing state pass-through, attribute access, closure capture, hardcoded default) → auto-patch inline, retest, commit fix + test together.
- **Architectural fix** (tool-capability gap, agent redesign, spec divergence) → halt, notify user with root-cause + 2-3 proposed directions, await decision.

---

## File structure overview

```
tests/harness/
├── __init__.py
├── conftest.py                       # live_harness marker, skip logic, trace fixture
├── contracts/
│   ├── __init__.py
│   ├── base.py                       # Contract, ContractResult, HarnessTrace dataclasses
│   ├── endpoints.py                  # /graph, /stage_plans, /cost, /pi/history contracts
│   ├── resolve_agent.py              # model-plumbing input contract
│   ├── stage_nodes.py                # enter/stage_plan/gate/work/evaluate/decide contracts
│   ├── transition.py                 # transition_node priority contracts
│   ├── pi_advisor.py                 # PI verdict contracts
│   └── hitl.py                       # /checkpoint/approve + paused_event contracts
├── harness/
│   ├── __init__.py
│   ├── session.py                    # session bootstrap + WS + HTTP client
│   ├── steering.py                   # HITL directive + context-shape helpers
│   ├── capture.py                    # agent_llm_request prompt/response capture
│   ├── snapshots.py                  # StateSnapshot capture/replay
│   └── trace.py                      # trace record + JSON artifact writer
├── test_spine.py                     # Phase 1 — end-to-end spine
├── test_stage_literature_review.py   # module test (dev aid)
├── test_stage_plan_formulation.py
├── test_stage_data_exploration.py
├── test_stage_data_preparation.py
├── test_stage_experimentation.py
├── test_stage_results_interpretation.py
├── test_stage_report_writing.py
├── test_stage_peer_review.py
├── test_stage_lab_meeting.py
├── forks/
│   ├── __init__.py
│   ├── test_fork_gate.py
│   ├── test_fork_evaluate.py
│   ├── test_fork_decide_hitl.py
│   ├── test_fork_transition.py
│   └── test_fork_pi_advisor.py
└── runs/                              # git-ignored; trace artifacts + snapshots
```

**Files modified outside `tests/harness/`:**
- `pyproject.toml` — register `live_harness` marker
- `.gitignore` — ignore `tests/harness/runs/`
- `agentlabx/stages/_helpers.py` — B2 fix (remove hardcoded model default)
- `agentlabx/stages/base.py` — B2 fix (add `StageContext.model` field)
- `agentlabx/server/executor.py` — B2 fix (populate `StageContext(model=...)` inside `start_session` from `session.config_overrides` / settings) **and** B3 fix (inside the inner `run_pipeline`, fail session if every ran stage errored)
- `agentlabx/core/graph_mapper.py` — B1 fix (`Transition.get` → attribute access)
- `agentlabx/stages/subgraph.py` — B4 fix (pass `stage.name` into `_emit_internal_node_changed`)

---

## Part A — Harness Infrastructure (Tasks 1-7)

### Task 1: Register `live_harness` marker and skip-if-no-API-key logic

**Files:**
- Modify: `pyproject.toml`
- Create: `tests/harness/__init__.py`
- Create: `tests/harness/conftest.py`
- Modify: `.gitignore`

- [ ] **Step 1: Register marker in `pyproject.toml`**

Find the `[tool.pytest.ini_options]` section and add to the `markers` list:
```toml
"live_harness: marks tests that require a live LLM provider (deselect with '-m \"not live_harness\"')",
```

- [ ] **Step 2: Create `tests/harness/__init__.py`** (empty file).

- [ ] **Step 3: Create `tests/harness/conftest.py`** with API-key skip logic:

```python
"""Harness suite conftest — skips every test unless a live provider is configured.

The harness tests require a real LLM provider. Skipping at collection time (not
test time) keeps `pytest` runs clean when env vars are absent.
"""
from __future__ import annotations

import os

import pytest


REQUIRED_MODEL_VAR = "AGENTLABX_LLM__DEFAULT_MODEL"

# Map provider prefix (before '/') → env var that must be set for that provider.
PROVIDER_KEY_VARS = {
    "gemini": "GEMINI_API_KEY",
    "anthropic": "ANTHROPIC_API_KEY",
    "openai": "OPENAI_API_KEY",
    "azure": "AZURE_API_KEY",
}


def _missing_requirements() -> str | None:
    model = os.environ.get(REQUIRED_MODEL_VAR)
    if not model:
        return f"{REQUIRED_MODEL_VAR} not set"
    prefix = model.split("/", 1)[0].lower()
    key_var = PROVIDER_KEY_VARS.get(prefix)
    if key_var is None:
        return f"Unknown provider prefix '{prefix}' in {REQUIRED_MODEL_VAR}"
    if not os.environ.get(key_var):
        return f"{key_var} not set (required for provider '{prefix}')"
    return None


def pytest_collection_modifyitems(config, items):
    """Skip any test marked live_harness when provider env vars are missing."""
    reason = _missing_requirements()
    if reason is None:
        return
    skip_marker = pytest.mark.skip(reason=f"live_harness skipped: {reason}")
    for item in items:
        if "live_harness" in item.keywords:
            item.add_marker(skip_marker)
```

- [ ] **Step 4: Add runs/ ignore in `.gitignore`**

Append a line:
```
tests/harness/runs/
```

- [ ] **Step 5: Verify marker registers cleanly**

Run: `uv run pytest tests/harness --collect-only -q`
Expected: `0 tests collected` (no tests yet, no errors).

Run: `uv run pytest --markers | grep live_harness`
Expected: One line showing the marker description.

- [ ] **Step 6: Commit**

```bash
git add pyproject.toml .gitignore tests/harness/__init__.py tests/harness/conftest.py
git commit -m "test(harness): register live_harness marker + API-key skip conftest (Plan 8 T1)"
```

---

### Task 2: Core dataclasses — Contract, ContractResult, HarnessTrace

**Files:**
- Create: `tests/harness/contracts/__init__.py`
- Create: `tests/harness/contracts/base.py`
- Create: `tests/stages/test_harness_contract_base.py`

- [ ] **Step 1: Create `tests/harness/contracts/__init__.py`** (empty).

- [ ] **Step 2: Write failing unit test** at `tests/stages/test_harness_contract_base.py`:

```python
"""Unit tests for contract base types — pure dataclass behavior, no live model."""
from __future__ import annotations

from tests.harness.contracts.base import Contract, ContractResult, HarnessTrace, Severity


def test_contract_result_ok():
    r = ContractResult.ok("enter_emits_event")
    assert r.passed is True
    assert r.contract_id == "enter_emits_event"
    assert r.severity is None


def test_contract_result_fail():
    r = ContractResult.fail(
        "enter_emits_event",
        severity=Severity.P1,
        actual="no event",
        expected="stage_internal_node_changed(enter)",
    )
    assert r.passed is False
    assert r.severity is Severity.P1
    assert "no event" in r.detail


def test_harness_trace_records_events():
    trace = HarnessTrace(test_id="t1")
    trace.record_event({"type": "stage_started", "stage": "literature_review"})
    assert len(trace.events) == 1
    assert trace.events[0]["type"] == "stage_started"


def test_harness_trace_records_prompt():
    trace = HarnessTrace(test_id="t1")
    trace.record_prompt(
        node="work",
        stage="literature_review",
        agent="phd_student",
        messages=[{"role": "user", "content": "hi"}],
    )
    assert len(trace.prompts) == 1
    assert trace.prompts[0]["node"] == "work"


def test_contract_invokes_check():
    def check(trace: HarnessTrace) -> ContractResult:
        if any(e.get("type") == "stage_started" for e in trace.events):
            return ContractResult.ok("stage_started_present")
        return ContractResult.fail("stage_started_present", severity=Severity.P1)

    c = Contract(id="stage_started_present", check=check)
    trace = HarnessTrace(test_id="t1")
    trace.record_event({"type": "stage_started"})
    result = c.run(trace)
    assert result.passed
```

- [ ] **Step 3: Run test to verify it fails**

Run: `uv run pytest tests/stages/test_harness_contract_base.py -v`
Expected: ImportError — `tests.harness.contracts.base` does not exist.

- [ ] **Step 4: Implement `tests/harness/contracts/base.py`**

```python
"""Contract base types — pure dataclasses, no live-model coupling."""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable


class Severity(str, Enum):
    P0 = "P0"  # blocker: deadlock, unbounded, non-terminating
    P1 = "P1"  # critical: wrong/missing context (system-side)
    P2 = "P2"  # second critical: model fails to follow directive
    P3 = "P3"  # observational: unexpected but defensible


@dataclass
class ContractResult:
    contract_id: str
    passed: bool
    severity: Severity | None = None
    actual: Any = None
    expected: Any = None
    detail: str = ""

    @classmethod
    def ok(cls, contract_id: str) -> "ContractResult":
        return cls(contract_id=contract_id, passed=True)

    @classmethod
    def fail(
        cls,
        contract_id: str,
        *,
        severity: Severity,
        actual: Any = None,
        expected: Any = None,
        detail: str = "",
    ) -> "ContractResult":
        parts = [detail] if detail else []
        if expected is not None or actual is not None:
            parts.append(f"expected={expected!r} actual={actual!r}")
        return cls(
            contract_id=contract_id,
            passed=False,
            severity=severity,
            actual=actual,
            expected=expected,
            detail=" | ".join(parts) or contract_id,
        )


@dataclass
class HarnessTrace:
    test_id: str
    events: list[dict[str, Any]] = field(default_factory=list)
    prompts: list[dict[str, Any]] = field(default_factory=list)
    http: list[dict[str, Any]] = field(default_factory=list)
    state_snapshots: dict[str, dict[str, Any]] = field(default_factory=dict)
    results: list[ContractResult] = field(default_factory=list)

    def record_event(self, event: dict[str, Any]) -> None:
        self.events.append(event)

    def record_prompt(
        self,
        *,
        node: str,
        stage: str,
        agent: str,
        messages: list[dict[str, Any]],
        system: str | None = None,
        tools: list[str] | None = None,
    ) -> None:
        self.prompts.append({
            "node": node,
            "stage": stage,
            "agent": agent,
            "messages": messages,
            "system": system,
            "tools": tools or [],
        })

    def record_http(self, *, method: str, path: str, status: int, body: Any) -> None:
        self.http.append({"method": method, "path": path, "status": status, "body": body})

    def snapshot(self, label: str, state: dict[str, Any]) -> None:
        self.state_snapshots[label] = dict(state)

    def events_of_type(self, event_type: str) -> list[dict[str, Any]]:
        return [e for e in self.events if e.get("type") == event_type]

    def prompts_for(self, *, node: str | None = None, stage: str | None = None) -> list[dict[str, Any]]:
        out = self.prompts
        if node:
            out = [p for p in out if p["node"] == node]
        if stage:
            out = [p for p in out if p["stage"] == stage]
        return out


@dataclass
class Contract:
    id: str
    check: Callable[[HarnessTrace], ContractResult]
    description: str = ""

    def run(self, trace: HarnessTrace) -> ContractResult:
        return self.check(trace)
```

- [ ] **Step 5: Run test to verify it passes**

Run: `uv run pytest tests/stages/test_harness_contract_base.py -v`
Expected: 5 passed.

- [ ] **Step 6: Commit**

```bash
git add tests/harness/contracts/__init__.py tests/harness/contracts/base.py tests/stages/test_harness_contract_base.py
git commit -m "test(harness): Contract/ContractResult/HarnessTrace base types (Plan 8 T2)"
```

---

### Task 3: Session bootstrap helper (boot PipelineExecutor + WS + HTTP client)

**Files:**
- Create: `tests/harness/harness/__init__.py`
- Create: `tests/harness/harness/session.py`
- Create: `tests/stages/test_harness_session.py`

- [ ] **Step 1: Create `tests/harness/harness/__init__.py`** (empty).

- [ ] **Step 2: Write failing unit test** at `tests/stages/test_harness_session.py`:

```python
"""Unit test for harness session bootstrap. Uses mock llm_provider (not live) to
verify wiring; live tests live under tests/harness/ behind the marker."""
from __future__ import annotations

import pytest

from tests.harness.harness.session import HarnessSession


@pytest.mark.asyncio
async def test_session_boots_and_exposes_state():
    async with HarnessSession.boot_mock(topic="diffusion priors") as session:
        assert session.session_id is not None
        assert session.executor is not None
        assert session.state["research_topic"] == "diffusion priors"


@pytest.mark.asyncio
async def test_session_collects_events():
    async with HarnessSession.boot_mock(topic="x") as session:
        await session.emit_synthetic_event({"type": "probe", "value": 1})
        assert any(e.get("type") == "probe" for e in session.events)
```

- [ ] **Step 3: Run test to verify it fails**

Run: `uv run pytest tests/stages/test_harness_session.py -v`
Expected: ImportError.

- [ ] **Step 4: Implement `tests/harness/harness/session.py`**

Orient yourself first — read `agentlabx/server/executor.py` and `agentlabx/core/session.py` to confirm the current constructor signatures before copying this sketch. Real API (as of 2026-04-15):
- `PipelineExecutor(registry, session_manager, llm_provider, storage=None, checkpoint_db_path=..., event_forwarder=None)`; call `await executor.initialize()` before `start_session`.
- `SessionManager` from `agentlabx/core/session.py` owns the Session objects; build one `Session` via the manager, then pass it to `executor.start_session(session)`.
- Session exposes `session.event_bus` (per-session bus); subscribe via `event_bus.subscribe()` or the existing async generator pattern in `test_websocket.py`.

```python
"""Harness session bootstrap. Wraps the production PipelineExecutor for
harness use, with an event collector that mirrors the session's event bus into
a list accessible to tests.

Two boot modes:
- boot_mock(): MockLLMProvider. Fast unit-test mode for the harness itself.
- boot_live(): LiteLLMProvider reading AGENTLABX_LLM__DEFAULT_MODEL from env.
  Requires provider API key; gated by live_harness marker.
"""
from __future__ import annotations

import asyncio
import contextlib
from typing import Any

# NOTE: verify these imports against current code before committing.
from agentlabx.core.config import load_settings
from agentlabx.core.registry import PluginRegistry
from agentlabx.core.session import SessionManager
from agentlabx.providers.llm.litellm_provider import LiteLLMProvider
from agentlabx.providers.llm.mock import MockLLMProvider
from agentlabx.server.executor import PipelineExecutor


class HarnessSession:
    def __init__(
        self,
        *,
        executor: PipelineExecutor,
        session_manager: SessionManager,
        session: Any,  # Session instance
    ) -> None:
        self.executor = executor
        self.session_manager = session_manager
        self.session = session
        self.session_id = session.session_id
        self.event_bus = session.event_bus
        self.events: list[dict[str, Any]] = []
        self._mirror_task: asyncio.Task | None = None

    @property
    def state(self) -> dict[str, Any]:
        running = self.executor.get_running(self.session_id)
        if running is None:
            return {}
        # RunningSession exposes current state; consult server/executor.py for field name.
        return dict(getattr(running, "state", {}) or {})

    async def emit_synthetic_event(self, event: dict[str, Any]) -> None:
        self.events.append(event)

    async def _mirror_bus(self) -> None:
        # Match the existing subscribe pattern used elsewhere
        # (tests/server/test_websocket.py or executor's internal forwarder).
        async for event in self.event_bus.subscribe():
            self.events.append(event if isinstance(event, dict) else {
                "type": event.type,
                "data": event.data,
                "source": event.source,
            })

    async def _start_mirror(self) -> None:
        self._mirror_task = asyncio.create_task(self._mirror_bus())

    async def _stop_mirror(self) -> None:
        if self._mirror_task is not None:
            self._mirror_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._mirror_task

    @classmethod
    async def _build_executor(
        cls,
        *,
        llm_provider: Any,
    ) -> tuple[PipelineExecutor, SessionManager]:
        registry = PluginRegistry()
        settings = load_settings()
        registry.load_from_settings(settings)
        session_manager = SessionManager()
        executor = PipelineExecutor(
            registry=registry,
            session_manager=session_manager,
            llm_provider=llm_provider,
        )
        await executor.initialize()
        return executor, session_manager

    @classmethod
    @contextlib.asynccontextmanager
    async def boot_mock(cls, *, topic: str = "test topic"):
        executor, manager = await cls._build_executor(llm_provider=MockLLMProvider())
        try:
            session = await manager.create_session(research_topic=topic, goals=[])
            running = await executor.start_session(session)
            h = cls(executor=executor, session_manager=manager, session=session)
            await h._start_mirror()
            try:
                yield h
            finally:
                await h._stop_mirror()
                await executor.cancel_session(session.session_id)
        finally:
            await executor.close()

    @classmethod
    @contextlib.asynccontextmanager
    async def boot_live(cls, *, topic: str = "live test topic"):
        executor, manager = await cls._build_executor(llm_provider=LiteLLMProvider())
        try:
            session = await manager.create_session(research_topic=topic, goals=[])
            running = await executor.start_session(session)
            h = cls(executor=executor, session_manager=manager, session=session)
            await h._start_mirror()
            try:
                yield h
            finally:
                await h._stop_mirror()
                await executor.cancel_session(session.session_id)
        finally:
            await executor.close()
```

**Implementer checklist before running the test:**
1. Confirm `SessionManager.create_session(research_topic=..., goals=[...])` signature — may be different.
2. Confirm `event_bus.subscribe()` yields dicts vs Event objects — adjust `_mirror_bus` if it's Event objects with `.type`/`.data` attrs.
3. Confirm `RunningSession.state` attribute name (could be `.context.state` or similar).
4. If `executor.start_session` runs the whole pipeline in a bg task immediately — that's expected. The mirror captures events as they fire.

If any of these are fundamentally different (e.g. `SessionManager` doesn't exist / has different name), that's a **P1 architectural mismatch** — escalate to user before patching (could be a newer refactor or a rename since authoring).

- [ ] **Step 5: Run test to verify it passes**

Run: `uv run pytest tests/stages/test_harness_session.py -v`
Expected: 2 passed.

If any import fails because a method signature differs from this sketch (e.g. `executor.create_session` takes different args, or `EventBus.subscribe` yields differently), adjust the implementation to match the existing code in `agentlabx/` — **this is a wiring fix, not a design change.** Consult `agentlabx/core/pipeline.py` and `agentlabx/core/events.py` for current signatures.

- [ ] **Step 6: Commit**

```bash
git add tests/harness/harness/__init__.py tests/harness/harness/session.py tests/stages/test_harness_session.py
git commit -m "test(harness): HarnessSession bootstrap (mock + live modes) (Plan 8 T3)"
```

---

### Task 4: Prompt/response capture via `agent_llm_request` event

**Files:**
- Create: `tests/harness/harness/capture.py`
- Create: `tests/stages/test_harness_capture.py`

The existing event bus emits `agent_llm_request` with the full serialized prompt (messages, system, tools) whenever an agent invokes the LLM. The harness subscribes to this event and records it into the trace so input contracts (§4.1) can assert what the model saw.

- [ ] **Step 1: Write failing unit test** at `tests/stages/test_harness_capture.py`:

```python
from __future__ import annotations

from tests.harness.contracts.base import HarnessTrace
from tests.harness.harness.capture import capture_llm_event


def test_capture_maps_llm_request_to_trace():
    trace = HarnessTrace(test_id="t1")
    event = {
        "type": "agent_llm_request",
        "stage": "literature_review",
        "agent": "phd_student",
        "node": "work",
        "messages": [{"role": "user", "content": "hello"}],
        "system": "You are a PhD student.",
        "tools": ["arxiv_search"],
    }
    capture_llm_event(event, trace)
    assert len(trace.prompts) == 1
    assert trace.prompts[0]["node"] == "work"
    assert trace.prompts[0]["agent"] == "phd_student"
    assert trace.prompts[0]["messages"][0]["content"] == "hello"


def test_capture_ignores_non_llm_events():
    trace = HarnessTrace(test_id="t1")
    capture_llm_event({"type": "stage_started"}, trace)
    assert len(trace.prompts) == 0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/stages/test_harness_capture.py -v`
Expected: ImportError.

- [ ] **Step 3: Implement `tests/harness/harness/capture.py`**

```python
"""Capture serialized LLM prompts from the event bus into a HarnessTrace.

Relies on the existing `agent_llm_request` event (emitted by ConfigAgent.inference
via the shared event bus). The event carries the full message list, system prompt,
and tool names — enough to assert input contracts without monkey-patching LiteLLM.
"""
from __future__ import annotations

from typing import Any

from tests.harness.contracts.base import HarnessTrace


def capture_llm_event(event: dict[str, Any], trace: HarnessTrace) -> None:
    """Map a single bus event to a trace prompt record if it's an LLM request."""
    if event.get("type") != "agent_llm_request":
        return
    trace.record_prompt(
        node=event.get("node", ""),
        stage=event.get("stage", ""),
        agent=event.get("agent", ""),
        messages=event.get("messages", []),
        system=event.get("system"),
        tools=event.get("tools", []),
    )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/stages/test_harness_capture.py -v`
Expected: 2 passed.

**Note to implementer:** If the actual event emitted by `ConfigAgent.inference` uses different field names (e.g. `prompt` instead of `messages`, or omits `node`/`stage`), adjust the `capture_llm_event` mapping and the test fixture to match reality — then this is a **mechanical auto-patch**. If the event is missing critical fields entirely (e.g. no `stage` at all), that's itself a **P1 finding**: escalate before patching. Inspect `agentlabx/providers/llm/traced.py` and `agentlabx/agents/config_agent.py` to confirm the event shape.

- [ ] **Step 5: Commit**

```bash
git add tests/harness/harness/capture.py tests/stages/test_harness_capture.py
git commit -m "test(harness): capture_llm_event → HarnessTrace prompts (Plan 8 T4)"
```

---

### Task 5: StateSnapshot capture and replay

**Files:**
- Create: `tests/harness/harness/snapshots.py`
- Create: `tests/stages/test_harness_snapshots.py`

Phase 1 captures state at each station boundary; Phase 2 loads these as starting points for fork tests.

- [ ] **Step 1: Write failing unit test** at `tests/stages/test_harness_snapshots.py`:

```python
from __future__ import annotations

import json
from pathlib import Path

import pytest

from tests.harness.harness.snapshots import SnapshotStore


def test_snapshot_round_trip(tmp_path: Path):
    store = SnapshotStore(root=tmp_path)
    state = {
        "research_topic": "x",
        "current_stage": "literature_review",
        "stage_plans": {"literature_review": {"items": [{"id": "a"}]}},
        "cost_tracker": {"usd": 0.01},
    }
    store.save("after_literature_review", state)

    loaded = store.load("after_literature_review")
    assert loaded["research_topic"] == "x"
    assert loaded["stage_plans"]["literature_review"]["items"][0]["id"] == "a"


def test_snapshot_missing_raises(tmp_path: Path):
    store = SnapshotStore(root=tmp_path)
    with pytest.raises(FileNotFoundError):
        store.load("nope")


def test_snapshot_list_sorted(tmp_path: Path):
    store = SnapshotStore(root=tmp_path)
    store.save("after_data_exploration", {"a": 1})
    store.save("after_literature_review", {"a": 1})
    assert store.list() == ["after_data_exploration", "after_literature_review"]


def test_snapshot_roundtrip_preserves_nested_lists_and_numbers(tmp_path: Path):
    """Fork tests rely on exact state reconstruction — verify no coercion."""
    store = SnapshotStore(root=tmp_path)
    state = {
        "transition_log": [
            {"from_stage": "literature_review", "to_stage": "plan_formulation", "turn": 0}
        ],
        "errors": [],
        "iteration_count": 3,
    }
    store.save("s", state)
    loaded = store.load("s")
    assert loaded == state
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/stages/test_harness_snapshots.py -v`
Expected: ImportError.

- [ ] **Step 3: Implement `tests/harness/harness/snapshots.py`**

```python
"""Snapshot store for Phase 1 → Phase 2 state handoff.

The spine captures a JSON snapshot of PipelineState at each station boundary.
Fork tests load the snapshot for the station where they want to deviate, rehydrate
it into a fresh PipelineExecutor, then drive the alternate branch.

State is plain JSON — any non-JSON fields (asyncio events, task handles) must be
filtered out before save and re-wired during load by the caller.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any


class SnapshotStore:
    def __init__(self, root: Path) -> None:
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)

    def _path(self, label: str) -> Path:
        return self.root / f"{label}.json"

    def save(self, label: str, state: dict[str, Any]) -> None:
        payload = _jsonable(state)
        self._path(label).write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")

    def load(self, label: str) -> dict[str, Any]:
        p = self._path(label)
        if not p.exists():
            msg = f"Snapshot '{label}' not found at {p}. Run Phase 1 spine first."
            raise FileNotFoundError(msg)
        return json.loads(p.read_text(encoding="utf-8"))

    def list(self) -> list[str]:
        return sorted(p.stem for p in self.root.glob("*.json"))


def _jsonable(state: dict[str, Any]) -> dict[str, Any]:
    """Drop non-JSON-serializable fields (paused_event, asyncio tasks, etc.)."""
    out: dict[str, Any] = {}
    for k, v in state.items():
        try:
            json.dumps(v)
            out[k] = v
        except (TypeError, ValueError):
            continue
    return out
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/stages/test_harness_snapshots.py -v`
Expected: 4 passed.

- [ ] **Step 5: Commit**

```bash
git add tests/harness/harness/snapshots.py tests/stages/test_harness_snapshots.py
git commit -m "test(harness): SnapshotStore for Phase 1→Phase 2 state handoff (Plan 8 T5)"
```

---

### Task 6: Steering helpers — HITL directive + context shaping

**Files:**
- Create: `tests/harness/harness/steering.py`
- Create: `tests/stages/test_harness_steering.py`

- [ ] **Step 1: Write failing unit test** at `tests/stages/test_harness_steering.py`:

```python
from __future__ import annotations

from tests.harness.harness.steering import (
    ContextShape,
    HitlDirective,
    apply_context_shape,
)


def test_hitl_directive_approve():
    d = HitlDirective.approve()
    assert d.action == "approve"
    assert d.payload() == {"action": "approve"}


def test_hitl_directive_redirect_with_note():
    d = HitlDirective.redirect(target_stage="plan_formulation", reason="need deeper lit review")
    payload = d.payload()
    assert payload["action"] == "redirect"
    assert payload["target_stage"] == "plan_formulation"
    assert payload["reason"] == "need deeper lit review"


def test_apply_context_shape_sets_max_iterations():
    state = {"current_stage": "experimentation"}
    shape = ContextShape(max_stage_iterations=2)
    out = apply_context_shape(state, shape)
    assert out["max_stage_iterations"] == 2


def test_apply_context_shape_clears_prior_artifact_to_force_gate_run():
    state = {"artifacts": {"literature_review": {"summary": "..."}}}
    shape = ContextShape(clear_artifacts=["literature_review"])
    out = apply_context_shape(state, shape)
    assert "literature_review" not in out.get("artifacts", {})


def test_apply_context_shape_does_not_mutate_input():
    state = {"artifacts": {"lr": {}}, "max_stage_iterations": 5}
    shape = ContextShape(max_stage_iterations=2, clear_artifacts=["lr"])
    apply_context_shape(state, shape)
    assert state["max_stage_iterations"] == 5
    assert "lr" in state["artifacts"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/stages/test_harness_steering.py -v`
Expected: ImportError.

- [ ] **Step 3: Implement `tests/harness/harness/steering.py`**

```python
"""Steering helpers — how fork tests push the model toward a specific branch.

Two channels:
- HitlDirective: wraps the production POST /checkpoint/approve payload. Used at
  decide/transition checkpoints where the production UI would submit an approval.
- ContextShape: mutations to PipelineState applied *before* a stage runs, to bias
  the model (remove prior artifacts to force gate=run, cap iterations to force
  evaluate=done, etc.).

These are the only two legitimate steering mechanisms. Mocking the model is not
allowed — if a branch is unreachable via these channels, that itself is a finding.
"""
from __future__ import annotations

import copy
from dataclasses import dataclass, field
from typing import Any


@dataclass
class HitlDirective:
    action: str  # "approve" | "reject" | "redirect" | "edit"
    target_stage: str | None = None
    reason: str | None = None
    edit: dict[str, Any] | None = None

    @classmethod
    def approve(cls) -> "HitlDirective":
        return cls(action="approve")

    @classmethod
    def reject(cls, reason: str) -> "HitlDirective":
        return cls(action="reject", reason=reason)

    @classmethod
    def redirect(cls, *, target_stage: str, reason: str) -> "HitlDirective":
        return cls(action="redirect", target_stage=target_stage, reason=reason)

    @classmethod
    def edit(cls, *, edit: dict[str, Any]) -> "HitlDirective":
        return cls(action="edit", edit=edit)

    def payload(self) -> dict[str, Any]:
        out: dict[str, Any] = {"action": self.action}
        if self.target_stage is not None:
            out["target_stage"] = self.target_stage
        if self.reason is not None:
            out["reason"] = self.reason
        if self.edit is not None:
            out["edit"] = self.edit
        return out


@dataclass
class ContextShape:
    """Deterministic mutations applied to PipelineState before running a station.

    All fields default to no-op. Only set the ones needed to steer the target branch.
    """
    max_stage_iterations: int | None = None
    clear_artifacts: list[str] = field(default_factory=list)
    set_artifacts: dict[str, Any] = field(default_factory=dict)
    backtrack_budget: int | None = None
    extra_state: dict[str, Any] = field(default_factory=dict)


def apply_context_shape(state: dict[str, Any], shape: ContextShape) -> dict[str, Any]:
    """Return a deep-copied state with the shape applied. Input is never mutated."""
    out = copy.deepcopy(state)
    if shape.max_stage_iterations is not None:
        out["max_stage_iterations"] = shape.max_stage_iterations
    if shape.backtrack_budget is not None:
        out["backtrack_budget"] = shape.backtrack_budget
    artifacts = out.setdefault("artifacts", {})
    for name in shape.clear_artifacts:
        artifacts.pop(name, None)
    for name, value in shape.set_artifacts.items():
        artifacts[name] = value
    for k, v in shape.extra_state.items():
        out[k] = v
    return out
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/stages/test_harness_steering.py -v`
Expected: 5 passed.

- [ ] **Step 5: Commit**

```bash
git add tests/harness/harness/steering.py tests/stages/test_harness_steering.py
git commit -m "test(harness): HitlDirective + ContextShape steering helpers (Plan 8 T6)"
```

---

### Task 7: Trace artifact writer (JSON)

**Files:**
- Create: `tests/harness/harness/trace.py`
- Create: `tests/stages/test_harness_trace_writer.py`

- [ ] **Step 1: Write failing unit test** at `tests/stages/test_harness_trace_writer.py`:

```python
from __future__ import annotations

import json
from pathlib import Path

from tests.harness.contracts.base import ContractResult, HarnessTrace, Severity
from tests.harness.harness.trace import write_trace_artifact


def test_writer_emits_json_with_all_sections(tmp_path: Path):
    trace = HarnessTrace(test_id="spine.literature_review")
    trace.record_event({"type": "stage_started", "stage": "literature_review"})
    trace.record_prompt(
        node="work",
        stage="literature_review",
        agent="phd_student",
        messages=[{"role": "user", "content": "..."}],
    )
    trace.record_http(method="GET", path="/graph", status=200, body={"nodes": []})
    trace.snapshot("after_literature_review", {"current_stage": "plan_formulation"})
    trace.results.append(ContractResult.ok("enter_emits_event"))
    trace.results.append(
        ContractResult.fail("work_sees_items", severity=Severity.P1, actual=0, expected=">=1")
    )

    path = write_trace_artifact(trace, root=tmp_path)
    assert path.exists()
    data = json.loads(path.read_text(encoding="utf-8"))
    assert data["test_id"] == "spine.literature_review"
    assert len(data["events"]) == 1
    assert len(data["prompts"]) == 1
    assert len(data["http"]) == 1
    assert "after_literature_review" in data["state_snapshots"]
    assert data["summary"]["total"] == 2
    assert data["summary"]["passed"] == 1
    assert data["summary"]["failed"] == 1
    assert data["summary"]["by_severity"] == {"P1": 1}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/stages/test_harness_trace_writer.py -v`
Expected: ImportError.

- [ ] **Step 3: Implement `tests/harness/harness/trace.py`**

```python
"""Trace artifact writer. Writes a stable JSON schema to tests/harness/runs/<ts>/<test_id>.json."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from tests.harness.contracts.base import HarnessTrace


def write_trace_artifact(trace: HarnessTrace, *, root: Path) -> Path:
    root = Path(root)
    root.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out_dir = root / ts
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"{trace.test_id}.json"

    by_sev: dict[str, int] = {}
    passed = 0
    failed = 0
    for r in trace.results:
        if r.passed:
            passed += 1
        else:
            failed += 1
            if r.severity is not None:
                by_sev[r.severity.value] = by_sev.get(r.severity.value, 0) + 1

    payload = {
        "test_id": trace.test_id,
        "events": trace.events,
        "prompts": trace.prompts,
        "http": trace.http,
        "state_snapshots": trace.state_snapshots,
        "results": [
            {
                "contract_id": r.contract_id,
                "passed": r.passed,
                "severity": r.severity.value if r.severity else None,
                "detail": r.detail,
            }
            for r in trace.results
        ],
        "summary": {
            "total": len(trace.results),
            "passed": passed,
            "failed": failed,
            "by_severity": by_sev,
        },
    }
    out_path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    return out_path
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/stages/test_harness_trace_writer.py -v`
Expected: 1 passed.

- [ ] **Step 5: Commit**

```bash
git add tests/harness/harness/trace.py tests/stages/test_harness_trace_writer.py
git commit -m "test(harness): trace JSON artifact writer (Plan 8 T7)"
```

---

## Part B — Contracts + known-bug fixes (Tasks 8-13)

### Task 8: Endpoint contracts + fix B1 (`/graph` 500)

**Files:**
- Create: `tests/harness/contracts/endpoints.py`
- Create: `tests/stages/test_endpoint_contracts.py`
- Modify: `agentlabx/core/graph_mapper.py` (B1 fix)

- [ ] **Step 1: Write failing test that exercises B1** at `tests/stages/test_endpoint_contracts.py`:

```python
"""Contract + regression test for /graph endpoint after transitions."""
from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from agentlabx.core.graph_mapper import graph_for_state
from agentlabx.core.state import Transition


def _state_with_one_transition():
    return {
        "current_stage": "plan_formulation",
        "transition_log": [
            Transition(
                from_stage="literature_review",
                to_stage="plan_formulation",
                turn=0,
                timestamp="2026-04-15T10:00:00Z",
                reason="default_sequence",
            )
        ],
        "errors": [],
        "stage_plans": {},
    }


def test_graph_for_state_after_one_transition_returns_structure():
    """B1 regression: graph_for_state must not crash on non-empty transition_log."""
    result = graph_for_state(_state_with_one_transition())
    assert "nodes" in result
    assert "edges" in result


def test_graph_for_state_edge_exposes_from_and_to():
    result = graph_for_state(_state_with_one_transition())
    edges = result["edges"]
    assert any(e["from"] == "literature_review" and e["to"] == "plan_formulation" for e in edges)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/stages/test_endpoint_contracts.py -v`
Expected: `AttributeError: 'Transition' object has no attribute 'get'` or similar — B1 reproduced.

- [ ] **Step 3: Fix B1 in `agentlabx/core/graph_mapper.py`**

Locate the transition-handling loop (around line 95-105 per the bug report). Replace any `.get("from_stage")` / `.get("to_stage")` / `.get("timestamp")` with attribute access: `t.from_stage`, `t.to_stage`, `t.timestamp`. Run `grep -n '\.get(' agentlabx/core/graph_mapper.py` first to enumerate all sites, then fix each one that references a `Transition` field.

Commit marker: this is a **mechanical auto-patch** per §5.1.

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/stages/test_endpoint_contracts.py -v`
Expected: 2 passed.

Also re-run the existing mapper tests to confirm no regression:
Run: `uv run pytest tests/core/test_graph_mapper.py -v`
Expected: All prior tests still pass.

- [ ] **Step 5: Implement harness contracts in `tests/harness/contracts/endpoints.py`**

```python
"""Endpoint output contracts — verify REST endpoints respond correctly as the
harness exercises them. Each contract is a pure function over a HarnessTrace
that has an `http` record for the endpoint of interest.
"""
from __future__ import annotations

from tests.harness.contracts.base import Contract, ContractResult, HarnessTrace, Severity


def _last_http(trace: HarnessTrace, *, method: str, path_suffix: str) -> dict | None:
    for record in reversed(trace.http):
        if record["method"] == method and record["path"].endswith(path_suffix):
            return record
    return None


def _graph_returns_200_after_transition(trace: HarnessTrace) -> ContractResult:
    cid = "endpoints.graph.200_after_transition"
    # Only assert when a transition has occurred during this trace
    transitions = trace.events_of_type("stage_transitioned")
    if not transitions:
        return ContractResult.ok(cid)  # nothing to check yet
    record = _last_http(trace, method="GET", path_suffix="/graph")
    if record is None:
        return ContractResult.fail(
            cid, severity=Severity.P1, detail="no GET /graph recorded after transition"
        )
    if record["status"] != 200:
        return ContractResult.fail(
            cid,
            severity=Severity.P0,  # unbounded 500 = pipeline effectively broken
            expected=200,
            actual=record["status"],
            detail=f"/graph returned {record['status']} after transition",
        )
    return ContractResult.ok(cid)


def _stage_plans_has_current_stage(trace: HarnessTrace) -> ContractResult:
    cid = "endpoints.stage_plans.current_stage_present"
    record = _last_http(trace, method="GET", path_suffix="/stage_plans")
    if record is None:
        return ContractResult.ok(cid)
    body = record["body"] or {}
    # body is expected to be a dict keyed by stage name with plan items
    if not isinstance(body, dict) or not body:
        return ContractResult.fail(
            cid,
            severity=Severity.P1,
            detail="/stage_plans returned empty or non-dict body",
            actual=body,
        )
    return ContractResult.ok(cid)


GRAPH_200_AFTER_TRANSITION = Contract(
    id="endpoints.graph.200_after_transition",
    check=_graph_returns_200_after_transition,
    description="/graph must return 200 after at least one stage transition (B1 regression)",
)

STAGE_PLANS_PRESENT = Contract(
    id="endpoints.stage_plans.current_stage_present",
    check=_stage_plans_has_current_stage,
    description="/stage_plans must return populated dict once a station has run",
)
```

- [ ] **Step 6: Add contract unit test** appending to `tests/stages/test_endpoint_contracts.py`:

```python
from tests.harness.contracts.base import HarnessTrace
from tests.harness.contracts.endpoints import GRAPH_200_AFTER_TRANSITION


def test_graph_contract_passes_when_http_200_after_transition():
    trace = HarnessTrace(test_id="t")
    trace.record_event({"type": "stage_transitioned"})
    trace.record_http(method="GET", path="/api/sessions/abc/graph", status=200, body={"nodes": [], "edges": []})
    result = GRAPH_200_AFTER_TRANSITION.run(trace)
    assert result.passed


def test_graph_contract_fails_on_500():
    trace = HarnessTrace(test_id="t")
    trace.record_event({"type": "stage_transitioned"})
    trace.record_http(method="GET", path="/api/sessions/abc/graph", status=500, body=None)
    result = GRAPH_200_AFTER_TRANSITION.run(trace)
    assert not result.passed
    assert result.severity.value == "P0"


def test_graph_contract_ok_when_no_transition_yet():
    trace = HarnessTrace(test_id="t")
    result = GRAPH_200_AFTER_TRANSITION.run(trace)
    assert result.passed
```

Run: `uv run pytest tests/stages/test_endpoint_contracts.py -v`
Expected: 5 passed (2 regression + 3 contract unit tests).

- [ ] **Step 7: Commit**

```bash
git add agentlabx/core/graph_mapper.py tests/harness/contracts/endpoints.py tests/stages/test_endpoint_contracts.py
git commit -m "fix(graph_mapper): Transition attribute access + endpoint contracts (Plan 8 T8, fixes B1)"
```

---

### Task 9: `resolve_agent` input contract + fix B2 (model plumbing)

**Files:**
- Modify: `agentlabx/stages/base.py` — add `StageContext.model` field
- Modify: `agentlabx/stages/_helpers.py` — remove hardcoded default; honor passed `model`; pass `context.model` from `resolve_agents_for_stage`
- Modify: `agentlabx/server/executor.py` — populate `StageContext(model=...)` inside `start_session` (around line 164) from `session.config_overrides.get("llm", {}).get("default_model")` with fallback to `load_settings().llm.default_model`
- Create: `tests/harness/contracts/resolve_agent.py`
- Create: `tests/stages/test_resolve_agent_model_plumbing.py`

- [ ] **Step 1: Write failing regression test** at `tests/stages/test_resolve_agent_model_plumbing.py`:

```python
"""B2 regression: StageContext.model is plumbed from settings.llm.default_model
and resolve_agent uses it instead of the hardcoded 'claude-sonnet-4-6'."""
from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from agentlabx.agents.config_agent import ConfigAgent
from agentlabx.agents.config_loader import AgentConfig
from agentlabx.core.registry import PluginRegistry, PluginType
from agentlabx.stages._helpers import resolve_agent, resolve_agents_for_stage
from agentlabx.stages.base import StageContext


def _make_registry_with_agent():
    reg = PluginRegistry()
    config = AgentConfig(
        name="test_agent",
        role="test",
        system_prompt="you are a test",
        memory_scope=[],
    )
    reg.register(PluginType.AGENT, "test_agent", config)
    return reg


def test_resolve_agent_uses_passed_model_not_hardcoded():
    reg = _make_registry_with_agent()
    agent = resolve_agent(reg, "test_agent", model="gemini/gemini-2.5-flash")
    assert isinstance(agent, ConfigAgent)
    assert agent.model == "gemini/gemini-2.5-flash"


def test_resolve_agent_no_default_model_when_none_passed():
    """When model is None, resolve_agent must NOT inject a hardcoded fallback.
    The ConfigAgent receives None and the caller is responsible for resolution."""
    reg = _make_registry_with_agent()
    agent = resolve_agent(reg, "test_agent", model=None)
    assert isinstance(agent, ConfigAgent)
    # ConfigAgent.model should be None — hardcoded fallback removed
    assert agent.model is None or agent.model == ""


def test_stage_context_has_model_field():
    ctx = StageContext(model="gemini/gemini-2.5-flash")
    assert ctx.model == "gemini/gemini-2.5-flash"


def test_resolve_agents_for_stage_passes_context_model():
    reg = _make_registry_with_agent()
    ctx = StageContext(registry=reg, model="gemini/gemini-2.5-flash")
    agents = resolve_agents_for_stage(ctx, ["test_agent"])
    assert agents["test_agent"].model == "gemini/gemini-2.5-flash"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/stages/test_resolve_agent_model_plumbing.py -v`
Expected: fails on `StageContext.model` missing AND fails on model being the hardcoded `"claude-sonnet-4-6"` default.

- [ ] **Step 3: Fix B2**

Add to `agentlabx/stages/base.py` inside the `StageContext` class (alongside `settings`, `event_bus`, etc.):
```python
    model: str | None = None  # Resolved default LLM model for this stage's agent calls
```
And update the docstring to document the field.

Edit `agentlabx/stages/_helpers.py::resolve_agent` signature — change `model: str = "claude-sonnet-4-6"` to `model: str | None = None`. Keep the rest of the body unchanged (ConfigAgent already accepts the model kwarg; if agent.model is None the implementer must check ConfigAgent behavior — if ConfigAgent requires a non-None model, raise explicitly rather than falling back).

Edit `agentlabx/stages/_helpers.py::resolve_agents_for_stage` to pass `model=context.model` into the `resolve_agent` call.

Edit `agentlabx/server/executor.py` — inside `PipelineExecutor.start_session` where `StageContext(...)` is constructed (currently around line 164), add a `model=` kwarg. Source priority: `session.config_overrides.get("llm", {}).get("default_model")` → fallback to `load_settings().llm.default_model` → else `None`. If there is a second construction site for `StageContext` elsewhere in `agentlabx/` (grep `StageContext(` to confirm), update both consistently.

Commit marker: **mechanical auto-patch** (plumbing only).

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/stages/test_resolve_agent_model_plumbing.py -v`
Expected: 4 passed.

Also re-run existing agent + stage tests to confirm no regression:
Run: `uv run pytest tests/agents tests/stages -q`
Expected: no new failures (there may be pre-existing flakes; compare against the pre-fix baseline).

**Escalate if:** any real stage test starts failing because `ConfigAgent.model=None` breaks LiteLLM invocation. That means the fix needs to choose: raise loudly at construction or require the caller to always pass a model. Ask the user which direction.

- [ ] **Step 5: Implement harness contract in `tests/harness/contracts/resolve_agent.py`**

```python
"""resolve_agent input contract — verify the agent that just ran used the
configured provider+model, not a hardcoded fallback."""
from __future__ import annotations

from tests.harness.contracts.base import Contract, ContractResult, HarnessTrace, Severity


def _model_matches_expected(trace: HarnessTrace, *, expected_prefix: str) -> ContractResult:
    cid = "resolve_agent.model_plumbed"
    for event in trace.events_of_type("agent_llm_request"):
        model = event.get("model", "")
        if not model:
            return ContractResult.fail(
                cid,
                severity=Severity.P1,
                detail=f"agent_llm_request event missing 'model' field: {event}",
            )
        if not model.startswith(expected_prefix):
            return ContractResult.fail(
                cid,
                severity=Severity.P1,
                expected=f"{expected_prefix}*",
                actual=model,
                detail=f"agent used wrong model — likely hardcoded fallback (B2 regression)",
            )
    return ContractResult.ok(cid)


def model_plumbed_contract(*, expected_prefix: str) -> Contract:
    return Contract(
        id="resolve_agent.model_plumbed",
        check=lambda trace: _model_matches_expected(trace, expected_prefix=expected_prefix),
        description=f"Every agent_llm_request must use a model starting with '{expected_prefix}'",
    )
```

**Note:** `agent_llm_request` event must carry a `model` field for this contract to work. If the event doesn't include model (check `agentlabx/agents/config_agent.py::inference`), add it — this is a **mechanical auto-patch** to the event emission. Verify by grepping `model=` occurrences in the inference method.

- [ ] **Step 6: Commit**

```bash
git add agentlabx/stages/base.py agentlabx/stages/_helpers.py agentlabx/server/executor.py tests/harness/contracts/resolve_agent.py tests/stages/test_resolve_agent_model_plumbing.py
git commit -m "fix(stages): plumb settings.llm.default_model through StageContext (Plan 8 T9, fixes B2)"
```

If `config_agent.py` was also modified to emit `model` in `agent_llm_request`, include it in this commit with a noted message addition.

---

### Task 10: Stage-node contracts + fix B4 (stale `stage_internal_node_changed.stage`)

**Files:**
- Modify: `agentlabx/stages/subgraph.py` — pass `stage.name` into each `_emit_internal_node_changed` call
- Create: `tests/harness/contracts/stage_nodes.py`
- Create: `tests/stages/test_subgraph_stage_name_propagation.py`

- [ ] **Step 1: Write failing regression test** at `tests/stages/test_subgraph_stage_name_propagation.py`:

```python
"""B4 regression: stage_internal_node_changed events carry the correct stage name
(not empty, not the previous stage's name)."""
from __future__ import annotations

import pytest

from agentlabx.stages.literature_review import LiteratureReviewStage
from agentlabx.stages.subgraph import StageSubgraphBuilder


@pytest.mark.asyncio
async def test_internal_node_events_include_current_stage_name():
    stage = LiteratureReviewStage()
    graph = StageSubgraphBuilder(stage).compile()
    state = {
        "research_topic": "x",
        "current_stage": "literature_review",
        "goals": [],
        "artifacts": {},
        "stage_plans": {},
    }

    events_seen: list[dict] = []

    class StubBus:
        async def publish(self, session_id, event):
            events_seen.append(event)

    bus = StubBus()
    wrapped = {"state": state, "event_bus": bus, "session_id": "s1"}

    # Run the graph and collect events
    await graph.ainvoke(wrapped)

    internal = [e for e in events_seen if e.get("type") == "stage_internal_node_changed"]
    assert internal, "expected at least one stage_internal_node_changed event"
    for e in internal:
        assert e.get("stage") == "literature_review", f"stale/empty stage field: {e}"
```

**Note:** the exact shape of `graph.ainvoke`'s input and the bus stub may differ from this sketch — inspect `agentlabx/stages/subgraph.py` to see how `_SubgraphState` is constructed and adjust. The *assertion* (stage name correct on every internal event) is the invariant that must hold.

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/stages/test_subgraph_stage_name_propagation.py -v`
Expected: fails with empty or stale stage names in the captured events.

- [ ] **Step 3: Fix B4 in `agentlabx/stages/subgraph.py`**

Locate `_emit_internal_node_changed` and its callers in the five internal node functions. Instead of reading `s["state"].get("current_stage")` (stale at subgraph entry), capture `stage.name` in the closure via `StageSubgraphBuilder.compile(stage)` and pass it explicitly. Refactor the helper signature:

```python
async def _emit_internal_node_changed(s, node_name: str, *, stage_name: str) -> None:
    ...
    await event_bus.publish(session_id, {
        "type": "stage_internal_node_changed",
        "stage": stage_name,
        "node": node_name,
    })
```

Update all five callers (enter, stage_plan, gate, work, evaluate, decide — six total) to pass `stage_name=stage.name` from the enclosing closure.

Commit marker: **mechanical auto-patch** (closure fix).

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/stages/test_subgraph_stage_name_propagation.py -v`
Expected: 1 passed.

Re-run the existing subgraph tests:
Run: `uv run pytest tests/stages/test_subgraph.py tests/stages/test_subgraph_internal_cursor.py -v`
Expected: all previously-passing tests still pass.

- [ ] **Step 5: Implement stage-node contracts** at `tests/harness/contracts/stage_nodes.py`:

```python
"""Input + output contracts for each internal subgraph node: enter, stage_plan,
gate, work, evaluate, decide.

Input contracts verify the model saw the correct context at this node (prompt
includes required fields). Output contracts verify the node emitted the right
events and wrote the right state.
"""
from __future__ import annotations

from tests.harness.contracts.base import Contract, ContractResult, HarnessTrace, Severity


# -------- ENTER ----------

def _enter_emits_event_for_stage(trace: HarnessTrace, *, stage_name: str) -> ContractResult:
    cid = f"stage_nodes.enter.emits_event[{stage_name}]"
    events = [
        e for e in trace.events_of_type("stage_internal_node_changed")
        if e.get("node") == "enter" and e.get("stage") == stage_name
    ]
    if not events:
        return ContractResult.fail(
            cid,
            severity=Severity.P1,
            detail=f"no stage_internal_node_changed(enter,{stage_name}) event",
        )
    empty_stage = any(not e.get("stage") for e in events)
    if empty_stage:
        return ContractResult.fail(
            cid, severity=Severity.P1,
            detail="enter event has empty 'stage' field (B4 regression)",
        )
    return ContractResult.ok(cid)


def enter_emits_event(*, stage_name: str) -> Contract:
    return Contract(
        id=f"stage_nodes.enter.emits_event[{stage_name}]",
        check=lambda t: _enter_emits_event_for_stage(t, stage_name=stage_name),
    )


# -------- STAGE_PLAN ----------

def _stage_plan_persists_plan(trace: HarnessTrace, *, stage_name: str) -> ContractResult:
    cid = f"stage_nodes.stage_plan.persisted[{stage_name}]"
    events = [
        e for e in trace.events_of_type("stage_plan_persisted")
        if e.get("stage") == stage_name
    ]
    if not events:
        return ContractResult.fail(
            cid, severity=Severity.P1,
            detail=f"no stage_plan_persisted for {stage_name}",
        )
    return ContractResult.ok(cid)


def stage_plan_persisted(*, stage_name: str) -> Contract:
    return Contract(
        id=f"stage_nodes.stage_plan.persisted[{stage_name}]",
        check=lambda t: _stage_plan_persists_plan(t, stage_name=stage_name),
    )


def _stage_plan_prompt_has_goals(trace: HarnessTrace, *, stage_name: str) -> ContractResult:
    cid = f"stage_nodes.stage_plan.prompt_includes_goals[{stage_name}]"
    prompts = trace.prompts_for(node="stage_plan", stage=stage_name)
    if not prompts:
        return ContractResult.fail(
            cid, severity=Severity.P1,
            detail=f"no captured prompt at stage_plan/{stage_name}",
        )
    for p in prompts:
        blob = (p.get("system") or "") + " ".join(m.get("content", "") for m in p.get("messages", []))
        if "goal" not in blob.lower() and "objective" not in blob.lower():
            return ContractResult.fail(
                cid, severity=Severity.P2,
                detail="stage_plan prompt lacks any goals/objectives reference",
            )
    return ContractResult.ok(cid)


def stage_plan_prompt_includes_goals(*, stage_name: str) -> Contract:
    return Contract(
        id=f"stage_nodes.stage_plan.prompt_includes_goals[{stage_name}]",
        check=lambda t: _stage_plan_prompt_has_goals(t, stage_name=stage_name),
    )


# -------- WORK ----------

def _work_prompt_includes_plan_items(trace: HarnessTrace, *, stage_name: str) -> ContractResult:
    cid = f"stage_nodes.work.prompt_includes_plan_items[{stage_name}]"
    prompts = trace.prompts_for(node="work", stage=stage_name)
    if not prompts:
        return ContractResult.fail(
            cid, severity=Severity.P1,
            detail=f"no captured prompt at work/{stage_name}",
        )
    # Look up plan from state snapshots (the spine fixture records it)
    snap_key = f"before_{stage_name}_work"
    snap = trace.state_snapshots.get(snap_key, {})
    plan = (snap.get("stage_plans") or {}).get(stage_name) or {}
    items = plan.get("items") or []
    if not items:
        return ContractResult.ok(cid)  # nothing to check if no plan items recorded
    blob = " ".join(
        (p.get("system") or "") + " ".join(m.get("content", "") for m in p.get("messages", []))
        for p in prompts
    )
    missing = [item.get("id") for item in items if item.get("id") and item.get("id") not in blob]
    if missing:
        return ContractResult.fail(
            cid, severity=Severity.P1,
            detail=f"work prompt missing plan item ids: {missing}",
        )
    return ContractResult.ok(cid)


def work_prompt_includes_plan_items(*, stage_name: str) -> Contract:
    return Contract(
        id=f"stage_nodes.work.prompt_includes_plan_items[{stage_name}]",
        check=lambda t: _work_prompt_includes_plan_items(t, stage_name=stage_name),
    )


def _work_emits_agent_turn(trace: HarnessTrace, *, stage_name: str) -> ContractResult:
    cid = f"stage_nodes.work.emits_agent_turn[{stage_name}]"
    starts = [
        e for e in trace.events_of_type("agent_turn_started")
        if e.get("stage") == stage_name
    ]
    if not starts:
        return ContractResult.fail(
            cid, severity=Severity.P1,
            detail=f"no agent_turn_started during {stage_name}.work",
        )
    return ContractResult.ok(cid)


def work_emits_agent_turn(*, stage_name: str) -> Contract:
    return Contract(
        id=f"stage_nodes.work.emits_agent_turn[{stage_name}]",
        check=lambda t: _work_emits_agent_turn(t, stage_name=stage_name),
    )


# -------- EVALUATE ----------

def _evaluate_respects_iteration_bound(trace: HarnessTrace, *, stage_name: str) -> ContractResult:
    cid = f"stage_nodes.evaluate.respects_iteration_bound[{stage_name}]"
    snap = trace.state_snapshots.get(f"after_{stage_name}", {})
    max_iter = snap.get("max_stage_iterations", 10)
    iters = [
        e for e in trace.events_of_type("stage_internal_node_changed")
        if e.get("node") == "evaluate" and e.get("stage") == stage_name
    ]
    if len(iters) > max_iter:
        return ContractResult.fail(
            cid, severity=Severity.P0,
            detail=f"evaluate ran {len(iters)} times; max_stage_iterations={max_iter} (unbounded)",
        )
    return ContractResult.ok(cid)


def evaluate_respects_iteration_bound(*, stage_name: str) -> Contract:
    return Contract(
        id=f"stage_nodes.evaluate.respects_iteration_bound[{stage_name}]",
        check=lambda t: _evaluate_respects_iteration_bound(t, stage_name=stage_name),
    )


# -------- DECIDE ----------

def _decide_pause_clears_event_and_emits_checkpoint(trace: HarnessTrace, *, stage_name: str) -> ContractResult:
    cid = f"stage_nodes.decide.pause_contract[{stage_name}]"
    checkpoints = [
        e for e in trace.events_of_type("checkpoint_reached")
        if e.get("stage") == stage_name
    ]
    # If no checkpoint was requested, nothing to check
    snap = trace.state_snapshots.get(f"after_{stage_name}", {})
    needs_approval = snap.get("needs_approval", False)
    if not needs_approval:
        return ContractResult.ok(cid)
    if not checkpoints:
        return ContractResult.fail(
            cid, severity=Severity.P1,
            detail="decide said needs_approval=True but no checkpoint_reached emitted",
        )
    for e in checkpoints:
        if "control_mode" not in e.get("data", {}):
            return ContractResult.fail(
                cid, severity=Severity.P2,
                detail="checkpoint_reached missing control_mode field (Plan 7E C1 regression)",
            )
    return ContractResult.ok(cid)


def decide_pause_contract(*, stage_name: str) -> Contract:
    return Contract(
        id=f"stage_nodes.decide.pause_contract[{stage_name}]",
        check=lambda t: _decide_pause_clears_event_and_emits_checkpoint(t, stage_name=stage_name),
    )
```

- [ ] **Step 6: Add contract unit tests** to `tests/stages/test_subgraph_stage_name_propagation.py`:

```python
from tests.harness.contracts.base import HarnessTrace
from tests.harness.contracts.stage_nodes import enter_emits_event


def test_enter_contract_passes_when_event_has_correct_stage():
    trace = HarnessTrace(test_id="t")
    trace.record_event({
        "type": "stage_internal_node_changed",
        "node": "enter",
        "stage": "literature_review",
    })
    c = enter_emits_event(stage_name="literature_review")
    assert c.run(trace).passed


def test_enter_contract_fails_on_empty_stage():
    trace = HarnessTrace(test_id="t")
    trace.record_event({
        "type": "stage_internal_node_changed",
        "node": "enter",
        "stage": "",
    })
    c = enter_emits_event(stage_name="literature_review")
    assert not c.run(trace).passed
```

Run: `uv run pytest tests/stages/test_subgraph_stage_name_propagation.py -v`
Expected: all passed (1 regression + 2 contract unit).

- [ ] **Step 7: Commit**

```bash
git add agentlabx/stages/subgraph.py tests/harness/contracts/stage_nodes.py tests/stages/test_subgraph_stage_name_propagation.py
git commit -m "fix(subgraph): propagate stage.name via closure + stage_node contracts (Plan 8 T10, fixes B4)"
```

---

### Task 11: `transition_node` contracts + fix B3 (session completes on all-fail)

**Files:**
- Modify: `agentlabx/server/executor.py` — B3 fix: inside the inner `run_pipeline` function (around line 239) or its `finally`, inspect `state["errors"]` and call `session.fail()` instead of `session.complete()` when every ran stage errored
- Create: `tests/harness/contracts/transition.py`
- Create: `tests/stages/test_pipeline_fail_on_total_failure.py`

- [ ] **Step 1: Write failing regression test** at `tests/stages/test_pipeline_fail_on_total_failure.py`:

```python
"""B3 regression: when every stage in a session fails (e.g. AuthenticationError),
session resolves to 'failed', not 'completed'."""
from __future__ import annotations

import pytest

from agentlabx.core.pipeline import PipelineExecutor
from agentlabx.core.config import AppSettings
from agentlabx.core.events import EventBus
from agentlabx.core.registry import PluginRegistry


class AlwaysFailingProvider:
    """LLM provider stub that raises on every invocation."""
    async def ainvoke(self, *args, **kwargs):
        raise RuntimeError("simulated LLM auth failure")
    async def invoke(self, *args, **kwargs):
        raise RuntimeError("simulated LLM auth failure")


@pytest.mark.asyncio
async def test_session_fails_when_every_stage_errors():
    settings = AppSettings()
    # Restrict default sequence to 2 stages for speed
    settings.pipeline.default_sequence = ["literature_review", "plan_formulation"]
    settings.pipeline.max_total_iterations = 3

    event_bus = EventBus()
    registry = PluginRegistry()
    registry.load_from_settings(settings)
    executor = PipelineExecutor(
        registry=registry,
        settings=settings,
        event_bus=event_bus,
        llm_provider=AlwaysFailingProvider(),
    )
    session_id = "fail-test"
    await executor.create_session(session_id=session_id, research_topic="x", goals=[])
    await executor.start_session(session_id=session_id)
    await executor.await_completion(session_id=session_id, timeout=30.0)

    session = await executor.get_session(session_id=session_id)
    assert session.status == "failed", (
        f"expected failed, got {session.status} — B3: all-stages-errored resolved to completed"
    )
```

**Note:** the `await_completion(session_id=..., timeout=...)` helper may not exist on `PipelineExecutor` — `start_session` currently runs the pipeline in a bg asyncio task. Either (a) add a thin `await_completion` helper on `PipelineExecutor` that awaits the `_running[session_id].task` (mechanical, one-screen addition), or (b) await `RunningSession.task` directly in the test. Either is acceptable; pick whichever matches the existing pattern most closely.

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/stages/test_pipeline_fail_on_total_failure.py -v`
Expected: session status is `completed`, test fails.

- [ ] **Step 3: Fix B3 in `agentlabx/server/executor.py`**

Inside `PipelineExecutor.start_session`, locate the inner `async def run_pipeline()` function (around line 239) and its exit point — wherever `session.complete()` (or equivalent) is awaited. At that resolution point, inspect the final pipeline state's `errors` field:

```python
# After the pipeline's main loop exits, before calling session.complete():
errors = state.get("errors") or []
ran_stages = state.get("transition_log") or []
if errors and len(errors) >= max(1, len(ran_stages)):
    # Every stage that ran raised an error → this is a failure, not a success.
    reason = errors[-1].message if errors else "all stages errored"
    await session.fail(reason=reason)
    return
await session.complete()
```

**Architectural concern — may require escalation:** the exact threshold for "failed vs completed" might need a user decision. Current proposal: fail if every attempted stage errored. Alternative: fail if *any* fatal-category error (auth, config). If the mechanical rule above causes existing tests to start failing because some tests *expect* a session to `complete` with some errors (e.g. recoverable warnings), **escalate** to the user with the test name(s) and propose which rule to adopt.

Commit marker: **mechanical** if the simple threshold works; **escalate** if existing tests disagree on the threshold.

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/stages/test_pipeline_fail_on_total_failure.py -v`
Expected: 1 passed.

Re-run full pipeline + integration tests:
Run: `uv run pytest tests/integration tests/stages/test_runner.py -q`
Expected: no new failures.

- [ ] **Step 5: Implement transition contracts** at `tests/harness/contracts/transition.py`:

```python
"""transition_node output contracts — priority resolution + fail-not-complete."""
from __future__ import annotations

from tests.harness.contracts.base import Contract, ContractResult, HarnessTrace, Severity


def _session_completes_requires_success(trace: HarnessTrace) -> ContractResult:
    cid = "transition.session_completion_requires_success"
    completions = trace.events_of_type("session_completed")
    failed_stages = trace.events_of_type("stage_failed")
    if completions and failed_stages:
        # If every ran-stage emitted stage_failed, completion is a B3 regression
        started = trace.events_of_type("stage_started")
        if started and len(failed_stages) >= len(started):
            return ContractResult.fail(
                cid, severity=Severity.P1,
                detail=f"session completed with {len(failed_stages)} stage_failed events "
                       f"({len(started)} stages started) — B3 regression",
            )
    return ContractResult.ok(cid)


SESSION_COMPLETION_REQUIRES_SUCCESS = Contract(
    id="transition.session_completion_requires_success",
    check=_session_completes_requires_success,
    description="Session must not complete if every ran stage failed (B3 regression)",
)


def _transition_priorities_deterministic(trace: HarnessTrace) -> ContractResult:
    """Priority 1-6 resolution per platform-design §3.2.1. For every stage_transitioned
    event, verify the chosen target is consistent with the preceding evaluate output."""
    cid = "transition.priority_resolution_deterministic"
    # Lightweight shape check — the spine test asserts specific priority-1 defaults;
    # fork tests assert non-default priorities. Here we just check the event is
    # well-formed (has from/to/reason).
    for e in trace.events_of_type("stage_transitioned"):
        if not all(k in e for k in ("from_stage", "to_stage", "reason")):
            return ContractResult.fail(
                cid, severity=Severity.P1,
                detail=f"stage_transitioned event missing keys: {e}",
            )
    return ContractResult.ok(cid)


TRANSITION_PRIORITIES_DETERMINISTIC = Contract(
    id="transition.priority_resolution_deterministic",
    check=_transition_priorities_deterministic,
    description="Every stage_transitioned event carries from_stage, to_stage, reason",
)
```

- [ ] **Step 6: Commit**

```bash
git add agentlabx/server/executor.py tests/harness/contracts/transition.py tests/stages/test_pipeline_fail_on_total_failure.py
git commit -m "fix(executor): fail session when every stage errored + transition contracts (Plan 8 T11, fixes B3)"
```

---

### Task 12: PI advisor contracts

**Files:**
- Create: `tests/harness/contracts/pi_advisor.py`
- Create: `tests/stages/test_pi_advisor_contracts_unit.py`

No bug fix expected here — PI advisor is new in Plan 7 and not yet known-broken. Contracts capture the expected behavior so the spine/fork tests surface any drift.

- [ ] **Step 1: Write failing unit test** at `tests/stages/test_pi_advisor_contracts_unit.py`:

```python
from __future__ import annotations

from tests.harness.contracts.base import HarnessTrace
from tests.harness.contracts.pi_advisor import (
    PI_VERDICT_IN_VOCAB,
    PI_EMITS_AGENT_TURN,
)


def test_verdict_contract_passes_on_approve():
    trace = HarnessTrace(test_id="t")
    trace.record_event({"type": "pi_verdict", "verdict": "approve"})
    assert PI_VERDICT_IN_VOCAB.run(trace).passed


def test_verdict_contract_fails_on_garbage():
    trace = HarnessTrace(test_id="t")
    trace.record_event({"type": "pi_verdict", "verdict": "sure thing boss"})
    assert not PI_VERDICT_IN_VOCAB.run(trace).passed


def test_turn_contract_passes_when_present():
    trace = HarnessTrace(test_id="t")
    trace.record_event({"type": "pi_agent_turn_started"})
    trace.record_event({"type": "pi_agent_turn_completed"})
    assert PI_EMITS_AGENT_TURN.run(trace).passed
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/stages/test_pi_advisor_contracts_unit.py -v`
Expected: ImportError.

- [ ] **Step 3: Implement `tests/harness/contracts/pi_advisor.py`**

```python
"""PI advisor contracts — verdict vocabulary, turn emission, history persistence."""
from __future__ import annotations

from tests.harness.contracts.base import Contract, ContractResult, HarnessTrace, Severity


VALID_VERDICTS = {"approve", "revise", "replan"}


def _verdict_in_vocab(trace: HarnessTrace) -> ContractResult:
    cid = "pi_advisor.verdict_in_vocab"
    for e in trace.events_of_type("pi_verdict"):
        v = e.get("verdict")
        if v not in VALID_VERDICTS:
            return ContractResult.fail(
                cid, severity=Severity.P2,
                expected=sorted(VALID_VERDICTS),
                actual=v,
                detail=f"PI advisor produced unparseable verdict: {v!r}",
            )
    return ContractResult.ok(cid)


def _emits_agent_turn(trace: HarnessTrace) -> ContractResult:
    cid = "pi_advisor.emits_agent_turn"
    verdicts = trace.events_of_type("pi_verdict")
    if not verdicts:
        return ContractResult.ok(cid)
    starts = trace.events_of_type("pi_agent_turn_started")
    completes = trace.events_of_type("pi_agent_turn_completed")
    if not starts or not completes:
        return ContractResult.fail(
            cid, severity=Severity.P1,
            detail=f"pi_verdict emitted but missing pi_agent_turn_started/completed "
                   f"(starts={len(starts)}, completes={len(completes)})",
        )
    return ContractResult.ok(cid)


def _prompt_includes_failures(trace: HarnessTrace) -> ContractResult:
    cid = "pi_advisor.prompt_includes_failures"
    prompts = [p for p in trace.prompts if p["agent"] in ("pi_advisor", "principal_investigator")]
    verdicts = trace.events_of_type("pi_verdict")
    if not verdicts or not prompts:
        return ContractResult.ok(cid)
    for p in prompts:
        blob = (p.get("system") or "") + " ".join(m.get("content", "") for m in p.get("messages", []))
        if "error" not in blob.lower() and "fail" not in blob.lower():
            return ContractResult.fail(
                cid, severity=Severity.P1,
                detail="PI advisor prompt lacks any failure/error context "
                       "— advisor can't deliberate without the failure history",
            )
    return ContractResult.ok(cid)


PI_VERDICT_IN_VOCAB = Contract(
    id="pi_advisor.verdict_in_vocab",
    check=_verdict_in_vocab,
    description="PI verdict must be one of approve/revise/replan",
)

PI_EMITS_AGENT_TURN = Contract(
    id="pi_advisor.emits_agent_turn",
    check=_emits_agent_turn,
    description="Every pi_verdict must be preceded by pi_agent_turn_started/completed",
)

PI_PROMPT_INCLUDES_FAILURES = Contract(
    id="pi_advisor.prompt_includes_failures",
    check=_prompt_includes_failures,
    description="PI advisor prompt must include failure/error context",
)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/stages/test_pi_advisor_contracts_unit.py -v`
Expected: 3 passed.

- [ ] **Step 5: Commit**

```bash
git add tests/harness/contracts/pi_advisor.py tests/stages/test_pi_advisor_contracts_unit.py
git commit -m "test(harness): PI advisor contracts (verdict vocab, turn, failure context) (Plan 8 T12)"
```

---

### Task 13: HITL checkpoint contracts

**Files:**
- Create: `tests/harness/contracts/hitl.py`
- Create: `tests/stages/test_hitl_contracts_unit.py`

- [ ] **Step 1: Write failing unit test** at `tests/stages/test_hitl_contracts_unit.py`:

```python
from __future__ import annotations

from tests.harness.contracts.base import HarnessTrace
from tests.harness.contracts.hitl import (
    CHECKPOINT_REACHED_INCLUDES_CONTROL_MODE,
    CHECKPOINT_APPROVE_ROUND_TRIP,
    APPROVE_409_WHEN_NO_EXECUTOR,
)


def test_control_mode_contract_passes():
    trace = HarnessTrace(test_id="t")
    trace.record_event({
        "type": "checkpoint_reached",
        "stage": "experimentation",
        "data": {"control_mode": "approve"},
    })
    assert CHECKPOINT_REACHED_INCLUDES_CONTROL_MODE.run(trace).passed


def test_control_mode_contract_fails_when_missing():
    trace = HarnessTrace(test_id="t")
    trace.record_event({
        "type": "checkpoint_reached",
        "stage": "experimentation",
        "data": {},
    })
    assert not CHECKPOINT_REACHED_INCLUDES_CONTROL_MODE.run(trace).passed


def test_round_trip_contract_passes():
    trace = HarnessTrace(test_id="t")
    trace.record_event({"type": "checkpoint_reached"})
    trace.record_http(
        method="POST",
        path="/api/sessions/abc/checkpoint/approve",
        status=200,
        body={"ok": True},
    )
    trace.record_event({"type": "pipeline_resumed"})
    assert CHECKPOINT_APPROVE_ROUND_TRIP.run(trace).passed


def test_409_when_no_executor_contract():
    trace = HarnessTrace(test_id="t")
    trace.record_http(
        method="POST",
        path="/api/sessions/abc/checkpoint/approve",
        status=409,
        body={"detail": "no executor"},
    )
    assert APPROVE_409_WHEN_NO_EXECUTOR.run(trace).passed
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/stages/test_hitl_contracts_unit.py -v`
Expected: ImportError.

- [ ] **Step 3: Implement `tests/harness/contracts/hitl.py`**

```python
"""HITL contracts — /checkpoint/approve round-trip, 409 guards, control_mode field."""
from __future__ import annotations

from tests.harness.contracts.base import Contract, ContractResult, HarnessTrace, Severity


def _control_mode_present(trace: HarnessTrace) -> ContractResult:
    cid = "hitl.checkpoint_reached_includes_control_mode"
    for e in trace.events_of_type("checkpoint_reached"):
        data = e.get("data") or {}
        if "control_mode" not in data:
            return ContractResult.fail(
                cid, severity=Severity.P2,
                detail=f"checkpoint_reached missing control_mode: {e}",
            )
    return ContractResult.ok(cid)


def _approve_round_trip(trace: HarnessTrace) -> ContractResult:
    cid = "hitl.approve_round_trip"
    # If no checkpoint was hit, nothing to check
    if not trace.events_of_type("checkpoint_reached"):
        return ContractResult.ok(cid)
    approve_calls = [
        r for r in trace.http
        if r["method"] == "POST" and r["path"].endswith("/checkpoint/approve") and r["status"] == 200
    ]
    if not approve_calls:
        return ContractResult.ok(cid)  # some checkpoints intentionally not approved
    resumes = trace.events_of_type("pipeline_resumed")
    if not resumes:
        return ContractResult.fail(
            cid, severity=Severity.P1,
            detail="approve POST returned 200 but no pipeline_resumed event followed "
                   "(paused_event.set() likely not called)",
        )
    return ContractResult.ok(cid)


def _approve_409_when_no_executor(trace: HarnessTrace) -> ContractResult:
    cid = "hitl.approve_409_when_no_executor"
    bad_calls = [
        r for r in trace.http
        if r["method"] == "POST" and r["path"].endswith("/checkpoint/approve")
        and r["status"] == 200 and isinstance(r.get("body"), dict)
        and r["body"].get("detail") == "no executor"
    ]
    if bad_calls:
        return ContractResult.fail(
            cid, severity=Severity.P1,
            detail="approve returned 200 when it should have returned 409 (no executor)",
        )
    return ContractResult.ok(cid)


CHECKPOINT_REACHED_INCLUDES_CONTROL_MODE = Contract(
    id="hitl.checkpoint_reached_includes_control_mode",
    check=_control_mode_present,
)

CHECKPOINT_APPROVE_ROUND_TRIP = Contract(
    id="hitl.approve_round_trip",
    check=_approve_round_trip,
)

APPROVE_409_WHEN_NO_EXECUTOR = Contract(
    id="hitl.approve_409_when_no_executor",
    check=_approve_409_when_no_executor,
)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/stages/test_hitl_contracts_unit.py -v`
Expected: 4 passed.

- [ ] **Step 5: Commit**

```bash
git add tests/harness/contracts/hitl.py tests/stages/test_hitl_contracts_unit.py
git commit -m "test(harness): HITL checkpoint contracts (control_mode, round-trip, 409) (Plan 8 T13)"
```

---

## Part C — Phase 1 Spine (Tasks 14-21)

Phase 1 runs every station in order with real LLM calls, chained via shared state. Each station's test asserts its contracts and captures a post-station snapshot. Run under the `live_harness` marker against Gemini flash.

**Discipline for every Task 14-21:**
- If a contract fails with a **mechanical** cause (plumbing, attribute access, missing field), auto-patch inline, re-run the spine from this station, commit the fix + test together.
- If a contract fails with an **architectural** cause (tool capability missing, agent design problem), halt and notify the user per §5.1.

**Common spine fixture** (referenced by all spine tests): defined inside `test_spine.py` using `pytest-asyncio` session scope. It boots `HarnessSession.boot_live()`, hooks the event bus to populate a shared `HarnessTrace`, and exposes a `run_station(stage_name)` helper that drives the executor to run one station and captures a snapshot.

### Task 14: Spine — `literature_review`

**Files:**
- Create: `tests/harness/test_spine.py` (initial with fixture + first station)

- [ ] **Step 1: Write spine fixture + literature_review test:**

```python
"""Phase 1 spine — end-to-end happy-path through every station with live LLM.

Fixture establishes a session-scoped HarnessSession (boot_live) and runs stations
sequentially; each task below asserts its station's contracts before the next one runs.
"""
from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from tests.harness.contracts.base import HarnessTrace
from tests.harness.contracts.endpoints import GRAPH_200_AFTER_TRANSITION
from tests.harness.contracts.resolve_agent import model_plumbed_contract
from tests.harness.contracts.stage_nodes import (
    enter_emits_event,
    stage_plan_persisted,
    stage_plan_prompt_includes_goals,
    work_prompt_includes_plan_items,
    work_emits_agent_turn,
    evaluate_respects_iteration_bound,
)
from tests.harness.contracts.transition import (
    SESSION_COMPLETION_REQUIRES_SUCCESS,
    TRANSITION_PRIORITIES_DETERMINISTIC,
)
from tests.harness.harness.capture import capture_llm_event
from tests.harness.harness.session import HarnessSession
from tests.harness.harness.snapshots import SnapshotStore
from tests.harness.harness.trace import write_trace_artifact


SNAPSHOT_ROOT = Path(__file__).parent / "runs" / "snapshots"
TRACE_ROOT = Path(__file__).parent / "runs" / "traces"


@pytest.fixture(scope="session")
def snapshot_store() -> SnapshotStore:
    return SnapshotStore(root=SNAPSHOT_ROOT)


@pytest.fixture(scope="session")
def harness_trace() -> HarnessTrace:
    return HarnessTrace(test_id="spine")


@pytest.fixture(scope="session")
async def live_session(harness_trace):
    async with HarnessSession.boot_live(topic="image super-resolution with diffusion priors") as s:
        # Mirror every bus event into the trace
        async def mirror():
            async for event in s.event_bus.subscribe(s.session_id):
                harness_trace.record_event(event)
                capture_llm_event(event, harness_trace)
        mirror_task = asyncio.create_task(mirror())
        try:
            yield s
        finally:
            mirror_task.cancel()
            try:
                await mirror_task
            except asyncio.CancelledError:
                pass
            write_trace_artifact(harness_trace, root=TRACE_ROOT)


async def _run_station(session: HarnessSession, stage_name: str) -> dict:
    """Drive the executor to complete one station. Returns the state snapshot after."""
    await session.executor.start_session(session_id=session.session_id)
    # Wait for the stage_transitioned event that marks this station done,
    # or a terminal session event. The spine runs stations one-at-a-time by
    # the pipeline's natural order; each _run_station awaits the next transition.
    # Implementation note: consult core/pipeline.py for the exact "run until next
    # transition" primitive. If none exists, this is a harness-side wait-loop on
    # the event stream.
    ...  # implemented per actual executor API
    return dict(session.state)


@pytest.mark.live_harness
@pytest.mark.asyncio
async def test_spine_literature_review(live_session, harness_trace, snapshot_store):
    state = await _run_station(live_session, "literature_review")
    snapshot_store.save("after_literature_review", state)
    harness_trace.snapshot("after_literature_review", state)

    contracts = [
        enter_emits_event(stage_name="literature_review"),
        stage_plan_persisted(stage_name="literature_review"),
        stage_plan_prompt_includes_goals(stage_name="literature_review"),
        work_prompt_includes_plan_items(stage_name="literature_review"),
        work_emits_agent_turn(stage_name="literature_review"),
        evaluate_respects_iteration_bound(stage_name="literature_review"),
        model_plumbed_contract(expected_prefix="gemini/"),
        TRANSITION_PRIORITIES_DETERMINISTIC,
        SESSION_COMPLETION_REQUIRES_SUCCESS,
    ]
    failures = []
    for c in contracts:
        r = c.run(harness_trace)
        harness_trace.results.append(r)
        if not r.passed:
            failures.append(r)
    assert not failures, f"Contract failures: {[(f.contract_id, f.severity, f.detail) for f in failures]}"
```

- [ ] **Step 2: Export `GEMINI_API_KEY` + `AGENTLABX_LLM__DEFAULT_MODEL=gemini/gemini-2.5-flash` and run the test:**

```bash
uv run pytest tests/harness/test_spine.py::test_spine_literature_review -m live_harness -v
```

- [ ] **Step 3: Triage every failing contract.**

- If it's a **mechanical** contract miss (e.g. `agent_llm_request` event lacks `node` field): patch it inline in `agentlabx/`, re-run this test, commit the fix + the passing test.
- If it's an **architectural** gap (e.g. `stage_plan_persisted` event is never emitted by the `stage_plan` node — the whole concept is missing): halt, ask the user.

Repeat until `test_spine_literature_review` passes cleanly.

- [ ] **Step 4: Commit**

```bash
git add tests/harness/test_spine.py agentlabx/  # agentlabx/ if mechanical fixes applied
git commit -m "test(harness): spine — literature_review station green (Plan 8 T14)"
```

---

### Task 15: Spine — `plan_formulation` + `lab_meeting` interstitial

**Files:**
- Modify: `tests/harness/test_spine.py` (add plan_formulation test)

- [ ] **Step 1: Append plan_formulation test to `test_spine.py`:**

```python
@pytest.mark.live_harness
@pytest.mark.asyncio
async def test_spine_plan_formulation(live_session, harness_trace, snapshot_store):
    state = await _run_station(live_session, "plan_formulation")
    snapshot_store.save("after_plan_formulation", state)
    harness_trace.snapshot("after_plan_formulation", state)

    contracts = [
        enter_emits_event(stage_name="plan_formulation"),
        stage_plan_persisted(stage_name="plan_formulation"),
        stage_plan_prompt_includes_goals(stage_name="plan_formulation"),
        work_prompt_includes_plan_items(stage_name="plan_formulation"),
        work_emits_agent_turn(stage_name="plan_formulation"),
        evaluate_respects_iteration_bound(stage_name="plan_formulation"),
    ]
    # lab_meeting interstitial fires after plan_formulation (per default config).
    # Assert it emitted stage_started + stage_completed.
    lab_meeting_events = [
        e for e in harness_trace.events_of_type("stage_started")
        if e.get("stage") == "lab_meeting"
    ]
    lab_meeting_completes = [
        e for e in harness_trace.events_of_type("stage_completed")
        if e.get("stage") == "lab_meeting"
    ]

    failures = []
    for c in contracts:
        r = c.run(harness_trace)
        harness_trace.results.append(r)
        if not r.passed:
            failures.append(r)

    if not lab_meeting_events:
        failures.append(
            f"lab_meeting interstitial did not fire after plan_formulation"
        )
    if not lab_meeting_completes:
        failures.append(
            f"lab_meeting started but did not complete"
        )
    assert not failures, f"Contract/interstitial failures: {failures}"
```

- [ ] **Step 2: Run the test**

Run: `uv run pytest tests/harness/test_spine.py::test_spine_plan_formulation -m live_harness -v`

- [ ] **Step 3: Triage failures per §5.1 (mechanical vs architectural).**

**Expected known gap:** `lab_meeting` subgraph body is not yet built (deferred from Plan 7E backlog). If it's configured to fire but has no implementation, this test will surface that — **architectural finding**, escalate: "lab_meeting subgraph body missing; options (a) skip lab_meeting in Plan 8 and defer to a future plan, (b) build a minimal body now, (c) temporarily remove it from the default sequence." Proceed per user decision.

- [ ] **Step 4: Commit**

```bash
git add tests/harness/test_spine.py  # + any stages/ fixes if mechanical
git commit -m "test(harness): spine — plan_formulation + lab_meeting station green (Plan 8 T15)"
```

---

### Task 16: Spine — `data_exploration`

**Files:**
- Modify: `tests/harness/test_spine.py`

- [ ] **Step 1: Append test with the same structure as T14 but targeting `data_exploration`.** Use the identical 6 stage_nodes contracts plus transition + session contracts. Snapshot as `after_data_exploration`.

- [ ] **Step 2: Run**

`uv run pytest tests/harness/test_spine.py::test_spine_data_exploration -m live_harness -v`

- [ ] **Step 3: Triage failures.** Mechanical → patch + retest; architectural → escalate.

- [ ] **Step 4: Commit**

```bash
git commit -m "test(harness): spine — data_exploration station green (Plan 8 T16)"
```

---

### Task 17: Spine — `data_preparation`

**Files:**
- Modify: `tests/harness/test_spine.py`

Same shape as T16. Snapshot `after_data_preparation`.

- [ ] **Step 1:** Add `test_spine_data_preparation`.
- [ ] **Step 2:** Run + triage.
- [ ] **Step 3:** Commit with message `test(harness): spine — data_preparation station green (Plan 8 T17)`.

---

### Task 18: Spine — `experimentation`

**Files:**
- Modify: `tests/harness/test_spine.py`

Same shape. Snapshot `after_experimentation`. Because experimentation has prior-bypass tags per stage item (Plan 7E B2), verify each item's prompt correctly honors or ignores the bypass markers.

- [ ] **Step 1:** Add `test_spine_experimentation` with an extra contract asserting no item's prompt contains a bypass-target's prior-stage output when the item is marked `bypass=True` (the input contract for experimentation).
- [ ] **Step 2:** Run + triage.
- [ ] **Step 3:** Commit: `test(harness): spine — experimentation station green (Plan 8 T18)`.

---

### Task 19: Spine — `results_interpretation`

Same shape as T16. Snapshot `after_results_interpretation`.

- [ ] **Step 1:** Add test.
- [ ] **Step 2:** Run + triage.
- [ ] **Step 3:** Commit: `test(harness): spine — results_interpretation station green (Plan 8 T19)`.

---

### Task 20: Spine — `report_writing`

Same shape. Snapshot `after_report_writing`. Per Plan 7E B3, this stage has 6 section items with per-section prior-bypass; assert each section's prompt observes its bypass config.

- [ ] **Step 1:** Add test.
- [ ] **Step 2:** Run + triage.
- [ ] **Step 3:** Commit: `test(harness): spine — report_writing station green (Plan 8 T20)`.

---

### Task 21: Spine — `peer_review` → `session.complete`

Same shape. Snapshot `after_peer_review`. Additionally assert:
- `session_completed` event emitted (not `session_failed`)
- `SESSION_COMPLETION_REQUIRES_SUCCESS` passes
- `/graph` endpoint returns 200 after the final transition (`GRAPH_200_AFTER_TRANSITION`)

- [ ] **Step 1:** Add `test_spine_peer_review_and_complete`.

Extra steps inside the test body:
```python
# After peer_review snapshot, request /graph and verify 200
async with live_session.http_client() as client:
    resp = await client.get(f"/api/sessions/{live_session.session_id}/graph")
    harness_trace.record_http(method="GET", path=resp.url.path, status=resp.status_code, body=resp.json() if resp.status_code==200 else None)
r = GRAPH_200_AFTER_TRANSITION.run(harness_trace)
harness_trace.results.append(r)
assert r.passed
```

- [ ] **Step 2:** Run + triage.
- [ ] **Step 3:** Commit: `test(harness): spine — peer_review + session completion green (Plan 8 T21)`.

**Gate:** Before proceeding to Part D forks, verify all 8 spine tests pass in one clean run:

```bash
uv run pytest tests/harness/test_spine.py -m live_harness -v
```

Expected: 8 passed. If any are still failing (even intermittently), fix the root cause first; forks depend on these snapshots.

---

## Part D — Phase 2 Fork tests (Tasks 22-26)

Each fork test file covers one decision-node family. Tests load the appropriate spine snapshot, apply a `ContextShape` or issue an `HitlDirective`, and assert the target-branch contracts hold.

### Task 22: Fork tests — `gate=skip`

**Files:**
- Create: `tests/harness/forks/__init__.py`
- Create: `tests/harness/forks/test_fork_gate.py`

- [ ] **Step 1: Create empty `__init__.py`.**

- [ ] **Step 2: Write `test_fork_gate.py`** with one fork per station where `gate=skip` is meaningful (e.g. re-entering `literature_review` after a completed run — `gate` should see prior artifacts and return `skip`):

```python
"""Fork tests — gate=skip branch.

Setup: load snapshot AFTER each station has run. Construct a fresh session
rehydrated to that state. Re-enter the station's subgraph; assert gate returns
skip and no work/evaluate/decide nodes run.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from tests.harness.contracts.base import HarnessTrace
from tests.harness.harness.session import HarnessSession
from tests.harness.harness.snapshots import SnapshotStore


SNAPSHOT_ROOT = Path(__file__).parent.parent / "runs" / "snapshots"


@pytest.mark.live_harness
@pytest.mark.asyncio
async def test_fork_gate_skip_literature_review():
    store = SnapshotStore(root=SNAPSHOT_ROOT)
    snapshot = store.load("after_literature_review")
    # Rehydrate: boot session with this state, re-enter literature_review subgraph
    async with HarnessSession.boot_live_from_state(state=snapshot, target_stage="literature_review") as s:
        trace = HarnessTrace(test_id="fork.gate.skip.literature_review")
        # Mirror events
        import asyncio
        async def mirror():
            async for e in s.event_bus.subscribe(s.session_id):
                trace.record_event(e)
        mt = asyncio.create_task(mirror())
        try:
            await s.run_station("literature_review")
        finally:
            mt.cancel()
            try: await mt
            except asyncio.CancelledError: pass

        # Assert gate=skip path
        internal = [e for e in trace.events_of_type("stage_internal_node_changed")
                    if e.get("stage") == "literature_review"]
        nodes_seen = [e.get("node") for e in internal]
        assert "gate" in nodes_seen
        assert "work" not in nodes_seen, (
            "gate should have returned skip but work ran — prior artifacts ignored"
        )
```

**Note to implementer:** `HarnessSession.boot_live_from_state` is a new helper. Add it to `tests/harness/harness/session.py` — rehydrate executor state from a dict (same shape as snapshot), set `current_stage` to the target, then yield. If rehydration isn't straightforward (e.g. `PipelineExecutor` has no public rehydration API), that's itself an **architectural finding**: escalate with either "add a rehydrate method" or "change fork strategy to always run from root."

- [ ] **Step 3:** Run + triage: `uv run pytest tests/harness/forks/test_fork_gate.py -m live_harness -v`

- [ ] **Step 4:** Commit: `test(harness): fork — gate=skip from post-station snapshots (Plan 8 T22)`.

---

### Task 23: Fork tests — `evaluate=iterate-again`

**Files:**
- Create: `tests/harness/forks/test_fork_evaluate.py`

For each station where `evaluate` can meaningfully iterate (primarily `experimentation` and `report_writing`), force `iterate-again` by seeding the state with `items_done=[]` (nothing accomplished yet) and `max_stage_iterations=2` (bounded to prevent runaway):

- [ ] **Step 1:** Write fork tests that load the snapshot *before* the target station (e.g. `after_data_preparation` for the `experimentation` fork), apply `ContextShape(max_stage_iterations=2)` + clear items-done markers, then run experimentation and assert:
  - At least 2 `stage_internal_node_changed(node=evaluate)` events for the stage
  - `evaluate_respects_iteration_bound` contract passes (no more than 2)
  - Second-iteration prompt includes items-done marks from first iteration (input contract)

- [ ] **Step 2:** Run + triage.

- [ ] **Step 3:** Commit: `test(harness): fork — evaluate=iterate-again for experimentation + report_writing (Plan 8 T23)`.

---

### Task 24: Fork tests — `decide=needs_approval` + full HITL round-trip

**Files:**
- Create: `tests/harness/forks/test_fork_decide_hitl.py`

These forks exercise the production HITL path end-to-end: stage pauses, harness POSTs `/checkpoint/approve`, pipeline resumes. This is the most critical fork family because Plan 7E surfaced that this path had been broken since Plan 7C.

- [ ] **Step 1:** Write forks that:
  1. Load snapshot before a stage that can be configured for `needs_approval=True` (e.g. `report_writing`, `peer_review`)
  2. Apply `ContextShape` that sets `control_mode="approve"` on the stage
  3. Run the stage; await `checkpoint_reached` event
  4. POST to `/api/sessions/{id}/checkpoint/approve` with `HitlDirective.approve().payload()` via real HTTP
  5. Assert `pipeline_resumed` event fires, final stage transition happens

Target the critical contracts:
- `CHECKPOINT_REACHED_INCLUDES_CONTROL_MODE`
- `CHECKPOINT_APPROVE_ROUND_TRIP`
- `APPROVE_409_WHEN_NO_EXECUTOR` (as a separate test with no session → should 409)

Include a second test exercising `HitlDirective.reject(reason="...")` and assert the pipeline transitions to `session_failed` or an equivalent rejected state.

- [ ] **Step 2:** Run + triage.

- [ ] **Step 3:** Commit: `test(harness): fork — HITL approve/reject round-trip (Plan 8 T24)`.

---

### Task 25: Fork tests — transition backtrack

**Files:**
- Create: `tests/harness/forks/test_fork_transition.py`

Backtrack is triggered when `evaluate` returns `status="backtrack"` (the model decides the current stage's work is untenable and a prior stage must be redone).

- [ ] **Step 1:** Write forks:
  - Load `after_experimentation` snapshot
  - Apply `ContextShape(extra_state={"backtrack_budget": 2})` to ensure budget exists
  - Force `evaluate` to produce backtrack: shape by injecting empty/contradictory experiment results into state (context shaping, not mock), so the model's `evaluate` prompt sees unusable results
  - Run; assert:
    - `stage_transitioned` event with `to_stage="data_preparation"` (or whichever is the backtrack target)
    - `reason` field mentions backtrack
    - `backtrack_budget` decremented
    - PI advisor consulted on the N+1th consecutive backtrack (if budget=2, confirm PI fires on second backtrack)

- [ ] **Step 2:** Run + triage. If the model refuses to backtrack even with shaped context, that's a P2 finding — document which context shaping failed to steer, and escalate.

- [ ] **Step 3:** Commit: `test(harness): fork — transition backtrack + PI consultation (Plan 8 T25)`.

---

### Task 26: Fork tests — PI advisor `revise` + `replan` verdicts

**Files:**
- Create: `tests/harness/forks/test_fork_pi_advisor.py`

- [ ] **Step 1:** Two forks:
  - **revise:** Force PI consultation by triggering a negative-result escalation. Shape the state so the PI advisor sees minor failures and outputs `revise` (continue current stage with feedback). Assert `pi_verdict.verdict == "revise"`, feedback gets folded into next `work` iteration's prompt.
  - **replan:** Shape a scenario with severe/repeated failures so PI outputs `replan` (abandon current plan, go back to plan_formulation). Assert `pi_verdict.verdict == "replan"`, transition to `plan_formulation`, `stage_plan` re-runs with the original failures in its context.

- [ ] **Step 2:** Run + triage. Steering the PI toward a specific verdict is the hardest steering problem (model-behavior sensitive). If the natural model output diverges repeatedly after ~5 retries with different context shapes, that's a P2 finding: escalate with "PI cannot be reliably steered to X verdict via context shaping alone — options: (a) add an explicit verdict-override HITL channel, (b) accept observed-verdict-only coverage for this branch, (c) refine PI system prompt for more predictable verdict selection."

- [ ] **Step 3:** Commit: `test(harness): fork — PI advisor revise/replan verdicts (Plan 8 T26)`.

---

## Part E — Per-stage module tests + Finishing (Tasks 27-29)

### Task 27: Per-stage standalone module tests (dev aid)

**Files:**
- Create: `tests/harness/test_stage_literature_review.py` (and 8 siblings)

Each file is a thin wrapper that boots `HarnessSession.boot_live` and runs just that one stage's subgraph, asserting the same stage_nodes contracts as the spine test. Useful for fast iteration on a single stage without running the full spine.

- [ ] **Step 1:** Write one module test per stage using a shared helper:

```python
"""Standalone module test for literature_review. Dev aid — not authoritative.
The spine (test_spine.py) is the source of truth because it runs with real chained state."""
from __future__ import annotations

import pytest

from tests.harness.test_spine import _run_station  # reuse helper
from tests.harness.harness.session import HarnessSession
from tests.harness.contracts.base import HarnessTrace
from tests.harness.contracts.stage_nodes import (
    enter_emits_event,
    stage_plan_persisted,
    work_emits_agent_turn,
    evaluate_respects_iteration_bound,
)


@pytest.mark.live_harness
@pytest.mark.asyncio
async def test_module_literature_review_standalone():
    async with HarnessSession.boot_live(topic="test") as s:
        trace = HarnessTrace(test_id="module.literature_review")
        # minimal mirror
        import asyncio
        async def m():
            async for e in s.event_bus.subscribe(s.session_id):
                trace.record_event(e)
        mt = asyncio.create_task(m())
        try:
            await _run_station(s, "literature_review")
        finally:
            mt.cancel()
            try: await mt
            except asyncio.CancelledError: pass

        contracts = [
            enter_emits_event(stage_name="literature_review"),
            stage_plan_persisted(stage_name="literature_review"),
            work_emits_agent_turn(stage_name="literature_review"),
            evaluate_respects_iteration_bound(stage_name="literature_review"),
        ]
        for c in contracts:
            r = c.run(trace)
            assert r.passed, f"{r.contract_id}: {r.detail}"
```

Replicate for all 8 real stages + `lab_meeting` (skip if lab_meeting body was deferred in T15).

- [ ] **Step 2:** Run each: `uv run pytest tests/harness/test_stage_<name>.py -m live_harness -v`

- [ ] **Step 3:** Commit once all pass:

```bash
git add tests/harness/test_stage_*.py
git commit -m "test(harness): standalone per-stage module tests as dev aid (Plan 8 T27)"
```

---

### Task 28: Example trace artifact

**Files:**
- Create: `tests/harness/examples/spine-YYYYMMDD-green.json` (committed; real artifact from a green run)

- [ ] **Step 1:** Run a full clean spine:

```bash
uv run pytest tests/harness/test_spine.py -m live_harness -v
```

- [ ] **Step 2:** Pick the resulting `spine.json` artifact from `tests/harness/runs/<ts>/spine.json`, copy to `tests/harness/examples/spine-YYYYMMDD-green.json`. Scrub any API keys or PII from the content (search for `api_key`, `Bearer`, etc. — none expected, but verify).

- [ ] **Step 3:** Commit:

```bash
git add tests/harness/examples/spine-YYYYMMDD-green.json
git commit -m "docs(harness): committed example spine trace artifact (Plan 8 T28)"
```

---

### Task 29: Final clean run + plan-complete tag

- [ ] **Step 1:** Run the full harness end-to-end:

```bash
uv run pytest tests/harness -m live_harness -v
```

Expected:
- 8 spine tests pass
- All fork tests pass (counts vary by branch coverage)
- All 9 standalone module tests pass
- Zero P0/P1/P2 violations in the aggregated trace

- [ ] **Step 2:** Run the full suite (including non-harness) to verify no collateral regressions:

```bash
uv run pytest -q
```

Expected: all prior tests still pass (modulo pre-existing flakes noted in Plan 7E backlog: `test_server_e2e.py::TestFullSessionLifecycle` timeouts, `SessionCreatePage` flakes).

- [ ] **Step 3:** Tag the completion:

```bash
git tag plan8-complete
git log --oneline plan7e-complete..plan8-complete
```

- [ ] **Step 4:** Summary commit (optional — include metrics):

If any trace artifact grew during the clean run, re-run T28's commit step to update `tests/harness/examples/`.

---

## Self-review checklist (for the plan author — run before executing)

- [ ] Every task in Part A-E references exact file paths
- [ ] Every task has TDD steps (test first, then impl)
- [ ] All referenced types (`Contract`, `HarnessTrace`, `HitlDirective`, `ContextShape`, `SnapshotStore`, `HarnessSession`) are defined in earlier tasks
- [ ] All four known bugs (B1 T8, B2 T9, B3 T11, B4 T10) have dedicated fix steps
- [ ] Severity classifications match the spec (§5)
- [ ] Mechanical-vs-architectural calls noted at every known escalation point (T9, T11, T15, T22, T25, T26)
- [ ] File paths in the overview match file paths used in tasks
- [ ] Each task ends in a commit with a Plan 8 task-number tag

## Spec coverage self-check

Mapping spec §s → plan tasks:
- **§1 Purpose (B1-B4 bugs must be fixed):** T8 (B1), T9 (B2), T10 (B4), T11 (B3) ✓
- **§2 Design summary (live, DFS enumeration, HITL+context steering, contract pass/fail, retry-3-halt, halt-fix-retest, backend-only):** T3 (live via `boot_live`), T3-7 (steering + capture + trace), T8-13 (contracts), T14-26 (enumerated paths as individual tests), halt-fix-retest enforced at T14-26 per §5.1 ✓
- **§3.1 Decision-point taxonomy (gate/evaluate/decide/transition/PI/HITL):** contracts in T10, T11, T12, T13 ✓
- **§3.2 DFS enumeration (planning-time):** fork tests in T22-26 each correspond to an enumerated path ✓
- **§3.3 Bounds (max_depth=6, max_leaves_per_root=20):** enforced implicitly by bounded fork count in T22-26 ✓
- **§4 Two-dimension contracts (input + output):** every stage_nodes contract in T10 has both input (prompt capture) and output (event/state) assertions ✓
- **§5 Severity:** Severity enum in T2; severities assigned in T8-13 contracts ✓
- **§5.1 Auto-patch vs escalate:** explicit per-task notes at T9, T11, T15, T22, T25, T26 ✓
- **§6 Error policy (retry 3 + halt):** harness session wiring T3 (the executor already has LiteLLM retry; ensure its retry count is 3 or document if different — note for implementer to verify); halt-fix-retest in T14-26 ✓
- **§7 File layout:** matches plan's "File structure overview" section ✓
- **§8 Spine-first execution:** Part C (T14-21) = Phase 1, Part D (T22-26) = Phase 2 ✓
- **§9 Known-bug fix slots:** T8 (B1), T9 (B2), T10 (B4), T11 (B3) ✓
- **§10 Spec alignment:** halt-fix-retest §5.1 rule covers spec divergence ✓
- **§11 Out of scope:** frontend, nightly CI, record/replay, cost gating, model benchmarking — none included ✓
- **§12 Deliverables (contracts module, helpers, spine, forks, fixes, pyproject marker, example trace):** T1 (marker), T2-7 (helpers + base), T8-13 (contracts + fixes), T14-21 (spine), T22-26 (forks), T27 (module aid), T28 (example), T29 (final run) ✓
- **§13 Success criteria:** T29 full clean run covers all ✓

All spec sections covered.
