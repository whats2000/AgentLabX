# Plan 6B: Event Plane + Endpoints Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Wire turn-grained event emission through every agent/tool/LLM hot path, populate `agent_turns`, and expose 8 observability REST endpoints. At the end of Plan 6B the backend is fully observable via REST + WebSocket with zero frontend changes — a `--mock-llm` run can be validated end-to-end with curl and websocat.

**Architecture:** A `contextvars`-backed `TurnContext` correlates every event a single `ConfigAgent.inference()` call produces. `TracedLLMProvider` and `TracedTool` wrap the provider/tool boundary, reading the active turn context and emitting `agent_llm_request/response` + `agent_tool_call/result` events with matching `agent_turns` rows. `ConfigAgent.inference()` emits `agent_turn_started/completed` bookends with `system_prompt_hash`, `assembled_context_keys`, `memory_scope_applied`, and `is_mock`. `PIAgent.decide()` emits `pi_decision` and appends to `state["pi_decisions"]`. `ExperimentationStage` appends `ExperimentAttempt` to `state["experiment_log"]`. `results_interpretation` emits `hypothesis_update`. A graph topology mapper flattens LangGraph's compiled structure + runtime state into our owned `{nodes, edges, cursor, subgraphs}` shape.

**Tech Stack:** Python 3.12, FastAPI, contextvars (asyncio-safe per-task correlation), Pydantic v2 response models, pytest + httpx.AsyncClient.

**Companion spec:** `docs/superpowers/specs/2026-04-13-plan6-observability-design.md` §3.2–§3.5.
**Depends on:** Plan 6A complete (`PipelineState.agent_memory`, `experiment_log`, `pi_decisions`; `agent_turns` table; `BaseAgent` dirty-flag tracking).
**Unblocks:** Plan 6C (frontend UI).

---

## File Structure Map

**Created:**
```
agentlabx/core/turn_context.py                # TurnContext + ContextVar
agentlabx/core/graph_mapper.py                # owned topology builder
agentlabx/providers/llm/traced.py             # TracedLLMProvider
agentlabx/tools/traced.py                     # TracedTool
tests/core/test_turn_context.py
tests/core/test_graph_mapper.py
tests/providers/llm/test_traced.py
tests/tools/test_traced.py
tests/agents/test_config_agent_events.py
tests/agents/test_pi_agent_events.py
tests/stages/test_experimentation_log.py
tests/stages/test_results_interpretation_events.py
tests/server/test_event_types.py
tests/server/test_observability_endpoints.py
tests/integration/test_mock_llm_event_stream.py
```

**Modified:**
```
agentlabx/server/events.py                    # new event taxonomy; drop AGENT_THINKING
agentlabx/server/deps.py                      # wrap llm_provider with TracedLLMProvider
agentlabx/server/routes/sessions.py           # +8 observability endpoints
agentlabx/stages/_helpers.py                  # resolve_tool returns TracedTool
agentlabx/agents/config_agent.py              # turn lifecycle emission
agentlabx/agents/pi_agent.py                  # pi_decision emission + state persist
agentlabx/stages/experimentation.py           # ExperimentAttempt append + exit_code/stdout/stderr forward
agentlabx/stages/results_interpretation.py    # hypothesis_update emission
agentlabx/core/state.py                       # ExperimentResult gains exit_code/stdout/stderr/execution_time
```

---

### Task B1: New event type constants

**Files:**
- Modify: `agentlabx/server/events.py`
- Test: `tests/server/test_event_types.py`

- [ ] **Step 1: Write failing test.**

```python
# tests/server/test_event_types.py
def test_event_type_constants():
    from agentlabx.server.events import EventTypes
    for name in (
        "STAGE_STARTED", "STAGE_COMPLETED", "STAGE_FAILED",
        "AGENT_TURN_STARTED", "AGENT_TURN_COMPLETED",
        "AGENT_LLM_REQUEST", "AGENT_LLM_RESPONSE",
        "AGENT_TOOL_CALL", "AGENT_TOOL_RESULT",
        "AGENT_DIALOGUE", "PI_DECISION", "HYPOTHESIS_UPDATE",
        "CHECKPOINT_REACHED", "COST_UPDATE", "ERROR",
    ):
        assert hasattr(EventTypes, name), f"missing {name}"

def test_deprecated_event_type_removed():
    from agentlabx.server.events import EventTypes
    assert not hasattr(EventTypes, "AGENT_THINKING"), "legacy name must be removed"
```

- [ ] **Step 2: Run; verify fail.**

- [ ] **Step 3: Update `agentlabx/server/events.py`.** Replace current constants with:

```python
class EventTypes:
    # Stage lifecycle
    STAGE_STARTED = "stage_started"
    STAGE_COMPLETED = "stage_completed"
    STAGE_FAILED = "stage_failed"

    # Agent turn (Plan 6)
    AGENT_TURN_STARTED = "agent_turn_started"
    AGENT_TURN_COMPLETED = "agent_turn_completed"
    AGENT_LLM_REQUEST = "agent_llm_request"
    AGENT_LLM_RESPONSE = "agent_llm_response"
    AGENT_TOOL_CALL = "agent_tool_call"
    AGENT_TOOL_RESULT = "agent_tool_result"
    AGENT_DIALOGUE = "agent_dialogue"

    # Pipeline / research
    PI_DECISION = "pi_decision"
    HYPOTHESIS_UPDATE = "hypothesis_update"
    CHECKPOINT_REACHED = "checkpoint_reached"

    # Observability
    COST_UPDATE = "cost_update"
    ERROR = "error"
```

Search the codebase for any references to `AGENT_THINKING`, `agent_thinking` and remove or update them to the new taxonomy.

```bash
uv run pytest -v   # will surface any remaining references
```

- [ ] **Step 4: Run tests; verify pass.**

- [ ] **Step 5: Commit.**

```bash
git add agentlabx/server/events.py tests/server/test_event_types.py
git commit -m "feat(events): new turn-grained event taxonomy; drop legacy AGENT_THINKING"
```

### Task B2: TurnContext + ContextVar

**Files:**
- Create: `agentlabx/core/turn_context.py`
- Test: `tests/core/test_turn_context.py`

- [ ] **Step 1: Write failing test.**

```python
# tests/core/test_turn_context.py
import asyncio
from agentlabx.core.turn_context import TurnContext, current_turn, push_turn

def test_push_turn_sets_and_clears():
    assert current_turn() is None
    ctx = TurnContext(turn_id="t1", agent="a", stage="s", is_mock=False)
    with push_turn(ctx):
        assert current_turn() is ctx
    assert current_turn() is None

async def test_turn_context_isolated_per_task():
    async def worker(label):
        ctx = TurnContext(turn_id=f"t-{label}", agent="a", stage="s", is_mock=False)
        with push_turn(ctx):
            await asyncio.sleep(0)
            return current_turn().turn_id

    r = await asyncio.gather(worker("a"), worker("b"))
    assert set(r) == {"t-a", "t-b"}
```

- [ ] **Step 2: Run; verify fail.**

- [ ] **Step 3: Implement.**

```python
# agentlabx/core/turn_context.py
from __future__ import annotations
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
from typing import Iterator

@dataclass
class TurnContext:
    turn_id: str
    agent: str
    stage: str
    is_mock: bool
    parent_turn_id: str | None = None
    system_prompt_hash: str | None = None
    session_id: str | None = None
    tokens_in: int = 0
    tokens_out: int = 0
    cost_usd: float = 0.0
    tool_call_count: int = 0

_current: ContextVar[TurnContext | None] = ContextVar("current_turn", default=None)

def current_turn() -> TurnContext | None:
    return _current.get()

@contextmanager
def push_turn(ctx: TurnContext) -> Iterator[TurnContext]:
    token = _current.set(ctx)
    try:
        yield ctx
    finally:
        _current.reset(token)
```

- [ ] **Step 4: Run tests; verify pass.**

- [ ] **Step 5: Commit.**

```bash
git add agentlabx/core/turn_context.py tests/core/test_turn_context.py
git commit -m "feat(core): add TurnContext dataclass and asyncio-safe ContextVar for turn correlation"
```

### Task B3: TracedLLMProvider wrapper

**Files:**
- Create: `agentlabx/providers/llm/traced.py`
- Test: `tests/providers/llm/test_traced.py`

- [ ] **Step 1: Write failing test.**

```python
# tests/providers/llm/test_traced.py
import pytest
from unittest.mock import AsyncMock, MagicMock
from agentlabx.core.turn_context import TurnContext, push_turn
from agentlabx.providers.llm.traced import TracedLLMProvider
from agentlabx.providers.llm.base import LLMResponse

@pytest.fixture
def inner():
    p = MagicMock()
    p.is_mock = False
    p.query = AsyncMock(return_value=LLMResponse(
        content="hi", tokens_in=5, tokens_out=3, model="m", cost=0.01))
    return p

async def test_traced_provider_emits_events_around_query(inner):
    emitted = []
    bus = MagicMock()
    bus.emit = AsyncMock(side_effect=lambda ev: emitted.append(ev))
    storage = MagicMock()
    storage.append_agent_turn = AsyncMock(return_value=1)

    t = TracedLLMProvider(inner=inner, event_bus=bus, storage=storage)

    ctx = TurnContext(turn_id="T1", agent="phd", stage="lit", is_mock=False, session_id="s1")
    with push_turn(ctx):
        resp = await t.query(model="m", prompt="p", system_prompt="sp", temperature=0.2)
    assert resp.content == "hi"
    types = [e.type for e in emitted]
    assert types == ["agent_llm_request", "agent_llm_response"]
    assert ctx.tokens_in == 5 and ctx.tokens_out == 3
    assert storage.append_agent_turn.await_count == 2

async def test_traced_provider_bypasses_when_no_turn(inner):
    """If there is no current_turn, provider calls through without tracing."""
    bus = MagicMock(); bus.emit = AsyncMock()
    storage = MagicMock(); storage.append_agent_turn = AsyncMock()
    t = TracedLLMProvider(inner=inner, event_bus=bus, storage=storage)
    await t.query(model="m", prompt="p")
    bus.emit.assert_not_called()
    storage.append_agent_turn.assert_not_called()
```

- [ ] **Step 2: Run; verify fail.**

- [ ] **Step 3: Implement.**

```python
# agentlabx/providers/llm/traced.py
from __future__ import annotations
from agentlabx.core.events import Event
from agentlabx.core.turn_context import current_turn
from agentlabx.providers.llm.base import BaseLLMProvider, LLMResponse
from agentlabx.providers.storage.base import AgentTurnRecord
from agentlabx.server.events import EventTypes

class TracedLLMProvider(BaseLLMProvider):
    """Wraps any LLMProvider; emits agent_llm_request/response events
    and writes agent_turns rows when a TurnContext is active."""

    def __init__(self, inner: BaseLLMProvider, event_bus, storage):
        self._inner = inner
        self._bus = event_bus
        self._storage = storage
        self.is_mock = getattr(inner, "is_mock", False)

    @property
    def name(self) -> str:
        return getattr(self._inner, "name", "traced")

    async def query(self, *, model: str, prompt: str, system_prompt: str = "", temperature: float = 0.0) -> LLMResponse:
        ctx = current_turn()
        if ctx is None:
            return await self._inner.query(model=model, prompt=prompt, system_prompt=system_prompt, temperature=temperature)

        req_payload = {
            "model": model, "prompt": prompt, "system_prompt": system_prompt,
            "temperature": temperature, "is_mock": self.is_mock,
            "turn_id": ctx.turn_id, "parent_turn_id": ctx.parent_turn_id,
        }
        await self._bus.emit(Event(type=EventTypes.AGENT_LLM_REQUEST, data=req_payload, source=ctx.agent))
        if ctx.session_id:
            await self._storage.append_agent_turn(AgentTurnRecord(
                session_id=ctx.session_id, turn_id=ctx.turn_id, parent_turn_id=ctx.parent_turn_id,
                agent=ctx.agent, stage=ctx.stage, kind="llm_request", payload=req_payload,
                system_prompt_hash=ctx.system_prompt_hash, is_mock=self.is_mock,
            ))

        resp = await self._inner.query(model=model, prompt=prompt, system_prompt=system_prompt, temperature=temperature)

        resp_payload = {
            "turn_id": ctx.turn_id, "content": resp.content,
            "tokens_in": resp.tokens_in, "tokens_out": resp.tokens_out,
            "cost_usd": resp.cost, "model": resp.model, "is_mock": self.is_mock,
        }
        ctx.tokens_in += resp.tokens_in or 0
        ctx.tokens_out += resp.tokens_out or 0
        ctx.cost_usd += resp.cost or 0.0

        await self._bus.emit(Event(type=EventTypes.AGENT_LLM_RESPONSE, data=resp_payload, source=ctx.agent))
        if ctx.session_id:
            await self._storage.append_agent_turn(AgentTurnRecord(
                session_id=ctx.session_id, turn_id=ctx.turn_id, parent_turn_id=ctx.parent_turn_id,
                agent=ctx.agent, stage=ctx.stage, kind="llm_response", payload=resp_payload,
                tokens_in=resp.tokens_in, tokens_out=resp.tokens_out, cost_usd=resp.cost,
                is_mock=self.is_mock,
            ))
        return resp
```

- [ ] **Step 4: Run tests; verify pass.**

- [ ] **Step 5: Commit.**

```bash
git add agentlabx/providers/llm/traced.py tests/providers/llm/test_traced.py
git commit -m "feat(llm): TracedLLMProvider emits agent_llm_request/response and writes agent_turns"
```

### Task B4: TracedTool wrapper

**Files:**
- Create: `agentlabx/tools/traced.py`
- Test: `tests/tools/test_traced.py`

- [ ] **Step 1: Write failing test.**

```python
# tests/tools/test_traced.py
import pytest
from unittest.mock import AsyncMock, MagicMock
from agentlabx.core.turn_context import TurnContext, push_turn
from agentlabx.tools.traced import TracedTool

class _FakeResult:
    def __init__(self, success=True, data=None, error=None):
        self.success, self.data, self.error = success, data, error

@pytest.fixture
def inner():
    t = MagicMock()
    t.name = "arxiv_search"
    t.execute = AsyncMock(return_value=_FakeResult(success=True, data={"hits": 3}))
    return t

async def test_traced_tool_emits_call_and_result(inner):
    emitted = []
    bus = MagicMock(); bus.emit = AsyncMock(side_effect=lambda e: emitted.append(e))
    storage = MagicMock(); storage.append_agent_turn = AsyncMock(return_value=1)
    tt = TracedTool(inner=inner, event_bus=bus, storage=storage)

    ctx = TurnContext(turn_id="T1", agent="phd", stage="lit", is_mock=False, session_id="s")
    with push_turn(ctx):
        r = await tt.execute(query="LLM")
    assert r.success
    assert [e.type for e in emitted] == ["agent_tool_call", "agent_tool_result"]
    assert ctx.tool_call_count == 1
    assert storage.append_agent_turn.await_count == 2
```

- [ ] **Step 2: Run; verify fail.**

- [ ] **Step 3: Implement.**

```python
# agentlabx/tools/traced.py
from __future__ import annotations
from agentlabx.core.events import Event
from agentlabx.core.turn_context import current_turn
from agentlabx.providers.storage.base import AgentTurnRecord
from agentlabx.server.events import EventTypes

class TracedTool:
    """Wraps any BaseTool; emits agent_tool_call / agent_tool_result
    and writes agent_turns when a TurnContext is active."""

    def __init__(self, inner, event_bus, storage):
        self._inner = inner
        self._bus = event_bus
        self._storage = storage

    def __getattr__(self, item):
        # Delegate anything not explicitly overridden (name, description, schemas).
        return getattr(self._inner, item)

    async def execute(self, **kwargs):
        ctx = current_turn()
        if ctx is None:
            return await self._inner.execute(**kwargs)

        ctx.tool_call_count += 1
        call_payload = {
            "turn_id": ctx.turn_id, "parent_turn_id": ctx.parent_turn_id,
            "tool": self._inner.name, "args": _safe_preview(kwargs),
        }
        await self._bus.emit(Event(type=EventTypes.AGENT_TOOL_CALL, data=call_payload, source=ctx.agent))
        if ctx.session_id:
            await self._storage.append_agent_turn(AgentTurnRecord(
                session_id=ctx.session_id, turn_id=ctx.turn_id, parent_turn_id=ctx.parent_turn_id,
                agent=ctx.agent, stage=ctx.stage, kind="tool_call", payload=call_payload,
                is_mock=ctx.is_mock,
            ))

        result = await self._inner.execute(**kwargs)
        success = bool(getattr(result, "success", True))
        preview = _safe_preview(getattr(result, "data", None))
        err = getattr(result, "error", None)

        res_payload = {
            "turn_id": ctx.turn_id, "tool": self._inner.name,
            "success": success, "result_preview": preview, "error": err,
        }
        await self._bus.emit(Event(type=EventTypes.AGENT_TOOL_RESULT, data=res_payload, source=ctx.agent))
        if ctx.session_id:
            await self._storage.append_agent_turn(AgentTurnRecord(
                session_id=ctx.session_id, turn_id=ctx.turn_id, parent_turn_id=ctx.parent_turn_id,
                agent=ctx.agent, stage=ctx.stage, kind="tool_result", payload=res_payload,
                is_mock=ctx.is_mock,
            ))
        return result


def _safe_preview(obj, limit: int = 8000):
    import json
    try:
        s = json.dumps(obj, default=str)
    except Exception:
        s = str(obj)
    return s if len(s) <= limit else s[:limit] + "…"
```

- [ ] **Step 4: Run tests; verify pass.**

- [ ] **Step 5: Commit.**

```bash
git add agentlabx/tools/traced.py tests/tools/test_traced.py
git commit -m "feat(tools): TracedTool emits agent_tool_call/agent_tool_result around execute()"
```

### Task B5: Wire wrappers into dependency injection

**Files:**
- Modify: `agentlabx/server/deps.py`
- Modify: `agentlabx/stages/_helpers.py` (tool resolution returns traced wrapper)

- [ ] **Step 1: Wrap `llm_provider` at startup.** In `server/deps.py`, after constructing `llm_provider` and `storage`, replace assignment to `AppContext.llm_provider` with:

```python
from agentlabx.providers.llm.traced import TracedLLMProvider

_traced_llm = TracedLLMProvider(inner=llm_provider, event_bus=event_bus, storage=storage)
ctx.llm_provider = _traced_llm
```

Register both under their existing registry key so existing lookups resolve to the traced wrapper. Keep the raw `is_mock` propagation intact.

- [ ] **Step 2: Update `resolve_tool` in `stages/_helpers.py` to return wrapped tools.**

```python
from agentlabx.tools.traced import TracedTool

def resolve_tool(registry, name, *, event_bus=None, storage=None):
    raw = registry.get(PluginType.TOOL, name)
    if event_bus is not None and storage is not None:
        return TracedTool(inner=raw, event_bus=event_bus, storage=storage)
    return raw
```

Threading `event_bus` and `storage` through call sites: prefer passing via `StageContext` which stages already receive. Update stage call sites that invoke `resolve_tool(...)` to pass `event_bus=context.event_bus, storage=context.storage`.

- [ ] **Step 3: Integration smoke.**

```bash
uv run pytest tests/integration/ -v
```

- [ ] **Step 4: Commit.**

```bash
git add agentlabx/server/deps.py agentlabx/stages/_helpers.py agentlabx/stages/
git commit -m "feat(wiring): wrap LLM provider and tools with TracedLLMProvider/TracedTool at DI boundary"
```

### Task B6: ConfigAgent.inference emits turn lifecycle

**Files:**
- Modify: `agentlabx/agents/config_agent.py`
- Test: `tests/agents/test_config_agent_events.py`

- [ ] **Step 1: Write failing test.**

```python
# tests/agents/test_config_agent_events.py
import pytest
from unittest.mock import AsyncMock, MagicMock
from agentlabx.agents.config_agent import ConfigAgent
from agentlabx.agents.config_loader import AgentConfig
from agentlabx.agents.context import AgentContext, MemoryScope
from agentlabx.providers.llm.base import LLMResponse

@pytest.fixture
def cfg():
    return AgentConfig(
        name="phd_student", role="phd", system_prompt="sp",
        memory_scope=MemoryScope(read=["*"], summarize={}, write=[]),
        tools=[], phases=[],
    )

async def test_inference_emits_turn_started_and_completed(cfg):
    bus = MagicMock(); bus.emit = AsyncMock()
    storage = MagicMock(); storage.append_agent_turn = AsyncMock()
    llm = MagicMock()
    llm.is_mock = False
    llm.query = AsyncMock(return_value=LLMResponse(content="ok", tokens_in=1, tokens_out=1, model="m", cost=0.0))

    a = ConfigAgent(cfg, llm_provider=llm, event_bus=bus, storage=storage)
    actx = AgentContext(session_id="s1", stage="lit", state={})
    await a.inference("what?", actx)

    types = [c.args[0].type for c in bus.emit.await_args_list]
    assert types[0] == "agent_turn_started"
    assert types[-1] == "agent_turn_completed"
    assert a.turn_count == 1
    assert a.dirty is True
```

- [ ] **Step 2: Run; verify fail.**

- [ ] **Step 3: Implement in `ConfigAgent`.**

Extend the `__init__` signature with `event_bus=None, storage=None`. Rework `inference` to wrap the existing LLM-call body in a `push_turn(...)`:

```python
import hashlib, time, uuid
from agentlabx.core.events import Event
from agentlabx.core.turn_context import TurnContext, push_turn
from agentlabx.server.events import EventTypes

class ConfigAgent(BaseAgent):
    def __init__(self, cfg, llm_provider=None, model="claude-sonnet-4-6",
                 cost_tracker=None, mock_responses=None, event_bus=None, storage=None):
        super().__init__(...)  # existing initialisation
        self._event_bus = event_bus
        self._storage = storage
        # ... existing ...

    async def inference(self, prompt: str, context: AgentContext) -> str:
        turn_id = uuid.uuid4().hex
        sp_hash = hashlib.sha1(self.system_prompt.encode()).hexdigest()[:12]
        is_mock = bool(getattr(self._llm_provider, "is_mock", False)) or bool(self._mock_responses)

        ctx = TurnContext(
            turn_id=turn_id, agent=self.name, stage=context.stage,
            is_mock=is_mock, session_id=context.session_id,
            system_prompt_hash=sp_hash,
        )
        ctx_keys = sorted(list(context.state.keys())) if context.state else []

        start_payload = {
            "turn_id": turn_id, "agent": self.name, "stage": context.stage,
            "system_prompt_hash": sp_hash,
            "system_prompt_preview": self.system_prompt[:500],
            "assembled_context_keys": ctx_keys,
            "memory_scope_applied": {
                "read": list(self.memory_scope.read),
                "summarize": dict(self.memory_scope.summarize),
                "write": list(self.memory_scope.write),
            },
            "is_mock": is_mock,
        }
        if self._event_bus is not None:
            await self._event_bus.emit(Event(type=EventTypes.AGENT_TURN_STARTED, data=start_payload, source=self.name))

        self.turn_count += 1
        self.last_active_stage = context.stage
        self.dirty = True
        _t0 = time.perf_counter()

        with push_turn(ctx):
            content = await self._run_inference_body(prompt, context)
        # conversation_history append stays as before

        end_payload = {
            "turn_id": turn_id, "agent": self.name, "stage": context.stage,
            "elapsed_ms": int((time.perf_counter() - _t0) * 1000),
            "tokens_in_total": ctx.tokens_in,
            "tokens_out_total": ctx.tokens_out,
            "cost_usd": ctx.cost_usd,
        }
        if self._event_bus is not None:
            await self._event_bus.emit(Event(type=EventTypes.AGENT_TURN_COMPLETED, data=end_payload, source=self.name))
        return content
```

Refactor the old inference logic into `_run_inference_body` (preserving mock→provider→stub precedence).

- [ ] **Step 4: Update DI wiring.** `resolve_agent` in `stages/_helpers.py` forwards `event_bus` and `storage` from `StageContext` to `ConfigAgent(...)`.

- [ ] **Step 5: Run tests; verify pass.**

```bash
uv run pytest tests/agents/test_config_agent_events.py -v
```

- [ ] **Step 6: Commit.**

```bash
git add agentlabx/agents/config_agent.py agentlabx/stages/_helpers.py tests/agents/test_config_agent_events.py
git commit -m "feat(agents): ConfigAgent.inference emits turn_started/completed with rich metadata"
```

### Task B7: PIAgent emits pi_decision and persists

**Files:**
- Modify: `agentlabx/agents/pi_agent.py`
- Test: `tests/agents/test_pi_agent_events.py`

- [ ] **Step 1: Write failing test.**

```python
# tests/agents/test_pi_agent_events.py
import pytest
from unittest.mock import AsyncMock, MagicMock
from agentlabx.agents.pi_agent import PIAgent, PIDecision

async def test_decide_emits_pi_decision_and_appends_to_state():
    bus = MagicMock(); bus.emit = AsyncMock()
    pi = PIAgent(llm_provider=None, event_bus=bus)
    state = {"pi_decisions": [], "current_stage": "plan_formulation",
             "default_sequence": ["plan_formulation", "experimentation"],
             "completed_stages": [], "stage_iterations": {}, "total_iterations": 0,
             "cost_tracker": MagicMock(total_cost=0.0)}
    from agentlabx.core.config import SessionPreferences
    prefs = SessionPreferences()
    decision = await pi.decide(state, prefs, budget_warning=False)
    assert isinstance(decision, PIDecision)
    assert any(c.args[0].type == "pi_decision" for c in bus.emit.await_args_list)
    assert len(state["pi_decisions"]) == 1
    persisted = state["pi_decisions"][0]
    assert persisted["action"] == decision.action
    assert "decision_id" in persisted
```

- [ ] **Step 2: Run; verify fail.**

- [ ] **Step 3: Modify PIAgent.decide.** Accept `event_bus` in `__init__`. After computing the `PIDecision` and before returning:

```python
import uuid
from datetime import datetime
from agentlabx.core.events import Event
from agentlabx.server.events import EventTypes

        decision_dict = decision.model_dump()
        decision_dict["decision_id"] = uuid.uuid4().hex
        decision_dict["ts"] = datetime.utcnow().isoformat()
        state.setdefault("pi_decisions", []).append(decision_dict)
        self.decision_history.append(decision)
        if self._event_bus is not None:
            await self._event_bus.emit(Event(type=EventTypes.PI_DECISION, data=decision_dict, source="pi_agent"))
        return decision
```

Thread `event_bus` through wherever PIAgent is instantiated (executor or transition handler).

- [ ] **Step 4: Run tests; verify pass.**

- [ ] **Step 5: Commit.**

```bash
git add agentlabx/agents/pi_agent.py tests/agents/test_pi_agent_events.py
git commit -m "feat(pi-agent): emit pi_decision event and persist to state.pi_decisions"
```

### Task B8: ExperimentationStage appends ExperimentAttempt

**Files:**
- Modify: `agentlabx/stages/experimentation.py`
- Modify: `agentlabx/core/state.py` (ExperimentResult fields)
- Test: `tests/stages/test_experimentation_log.py`

- [ ] **Step 1: Write failing test.**

```python
# tests/stages/test_experimentation_log.py
import pytest
from agentlabx.stages.experimentation import ExperimentationStage

async def test_attempt_appended_per_run(stage_context, state_with_plan):
    """After one baseline + one main run, experiment_log has entries with
    approach_summary, outcome, and linked_hypothesis_id populated."""
    stage = ExperimentationStage()
    state = dict(state_with_plan, experiment_log=[])
    result = await stage.run(state, stage_context)
    log = state.get("experiment_log") or result.output.get("experiment_log") or []
    assert len(log) >= 2
    assert log[0]["outcome"] in ("success", "failure", "inconclusive")
    assert "attempt_id" in log[0]
```

Fixtures `stage_context`, `state_with_plan` live in `tests/stages/conftest.py`.

- [ ] **Step 2: Run; verify fail.**

- [ ] **Step 3: Extend ExperimentResult to carry execution metadata.** `ExecutionResult` from `SubprocessBackend` has `exit_code`, `stdout`, `stderr`, `execution_time` — currently consumed for metrics parsing then discarded. Add optional fields to `ExperimentResult` in `core/state.py`:

```python
    exit_code: int | None = None
    stdout: str | None = None
    stderr: str | None = None
    execution_time: float | None = None
```

ExperimentationStage populates them when building each `ExperimentResult`.

- [ ] **Step 4: Implement attempt classification and append.**

```python
import uuid
from datetime import datetime

def _classify_outcome(er) -> tuple[str, str | None]:
    if er.exit_code not in (0, None):
        return "failure", f"non-zero exit {er.exit_code}"
    if not er.metrics:
        return "inconclusive", "no metrics produced"
    return "success", None

    # In ExperimentationStage.run(), after building each ExperimentResult `er`:
    outcome, reason = _classify_outcome(er)
    attempt = {
        "attempt_id": uuid.uuid4().hex,
        "approach_summary": er.description[:500] if er.description else "",
        "outcome": outcome,
        "failure_reason": reason,
        "learnings": [],
        "linked_hypothesis_id": er.hypothesis_id,
        "ts": datetime.utcnow(),
    }
    state.setdefault("experiment_log", []).append(attempt)
```

`experiment_log` in state uses `operator.add`; the state reducer merges across nodes. In-stage appends write directly to the local dict.

- [ ] **Step 5: Run tests; verify pass.**

- [ ] **Step 6: Commit.**

```bash
git add agentlabx/stages/experimentation.py agentlabx/core/state.py tests/stages/test_experimentation_log.py
git commit -m "feat(stages): ExperimentationStage appends ExperimentAttempt; ExperimentResult carries exit_code/stdout/stderr"
```

### Task B9: results_interpretation emits hypothesis_update

**Files:**
- Modify: `agentlabx/stages/results_interpretation.py`
- Test: `tests/stages/test_results_interpretation_events.py`

- [ ] **Step 1: Write failing test.**

```python
# tests/stages/test_results_interpretation_events.py
import pytest
from agentlabx.stages.results_interpretation import ResultsInterpretationStage

async def test_emits_hypothesis_update_per_change(stage_context, state_with_hypotheses):
    bus = stage_context.event_bus
    stage = ResultsInterpretationStage()
    await stage.run(state_with_hypotheses, stage_context)
    emitted_types = [c.args[0].type for c in bus.emit.await_args_list]
    assert "hypothesis_update" in emitted_types
```

- [ ] **Step 2: Run; verify fail.**

- [ ] **Step 3: Implement.** In `ResultsInterpretationStage.run()`, where the postdoc's JSON `hypothesis_updates` is applied, after mutating each hypothesis emit an event:

```python
from agentlabx.core.events import Event
from agentlabx.server.events import EventTypes

for upd in hypothesis_updates:
    # ... existing mutation ...
    await context.event_bus.emit(Event(
        type=EventTypes.HYPOTHESIS_UPDATE,
        data={"hypothesis_id": upd["id"], "new_status": upd["new_status"], "evidence_link": upd.get("evidence")},
        source="postdoc",
    ))
```

- [ ] **Step 4: Run tests; verify pass.**

- [ ] **Step 5: Commit.**

```bash
git add agentlabx/stages/results_interpretation.py tests/stages/test_results_interpretation_events.py
git commit -m "feat(stages): emit hypothesis_update event per applied postdoc change in results_interpretation"
```

### Task B10: Graph topology mapper

**Files:**
- Create: `agentlabx/core/graph_mapper.py`
- Test: `tests/core/test_graph_mapper.py`

- [ ] **Step 1: Write failing test.**

```python
# tests/core/test_graph_mapper.py
from agentlabx.core.graph_mapper import build_topology

def test_topology_reflects_skip_stages():
    class _N:
        def __init__(self, id): self.id = id
    class _E:
        def __init__(self, s, t): self.source, self.target = s, t
    class _G:
        def __init__(self): self.nodes = {n: _N(n) for n in ["literature_review","plan_formulation","__end__"]}
        def edges(self): return [_E("literature_review","plan_formulation"), _E("plan_formulation","__end__")]
    class _C:
        def get_graph(self, xray=0): return _G()

    state = {
        "current_stage": "plan_formulation",
        "completed_stages": ["literature_review"],
        "stage_iterations": {"plan_formulation": 2},
        "stage_config": {"skip_stages": ["peer_review"]},
    }
    topo = build_topology(_C(), state)
    ids = {n["id"] for n in topo["nodes"]}
    assert "plan_formulation" in ids
    pf = next(n for n in topo["nodes"] if n["id"] == "plan_formulation")
    assert pf["status"] == "active"
    assert pf["iteration_count"] == 2
    lr = next(n for n in topo["nodes"] if n["id"] == "literature_review")
    assert lr["status"] == "complete"
    assert topo["cursor"]["node_id"] == "plan_formulation"
```

- [ ] **Step 2: Run; verify fail.**

- [ ] **Step 3: Implement.**

```python
# agentlabx/core/graph_mapper.py
from __future__ import annotations
from typing import Any

STAGE_ZONES = {
    "literature_review": "discovery", "plan_formulation": "discovery",
    "data_exploration": "implementation", "data_preparation": "implementation",
    "experimentation": "implementation",
    "results_interpretation": "synthesis", "report_writing": "synthesis",
    "peer_review": "synthesis",
}

def build_topology(compiled_graph, state: dict) -> dict[str, Any]:
    g = compiled_graph.get_graph()
    skip = set((state.get("stage_config") or {}).get("skip_stages", []))
    completed = set(state.get("completed_stages") or [])
    current = state.get("current_stage")
    iters = state.get("stage_iterations") or {}

    def _status(node_id):
        if node_id in skip:           return "skipped"
        if node_id in completed:      return "complete"
        if node_id == current:        return "active"
        return "pending"

    nodes = []
    for nid in g.nodes:
        if nid in ("__start__", "__end__", "transition"):
            kind = "transition" if nid == "transition" else "stage"
            nodes.append({
                "id": nid, "type": kind, "label": nid, "zone": None,
                "status": "meta", "iteration_count": 0, "skipped": False,
            })
            continue
        nodes.append({
            "id": nid, "type": "stage", "label": nid.replace("_", " ").title(),
            "zone": STAGE_ZONES.get(nid),
            "status": _status(nid),
            "iteration_count": int(iters.get(nid, 0)),
            "skipped": nid in skip,
        })

    edges = [{"from": e.source, "to": e.target, "kind": "sequential", "reason": None}
             for e in g.edges()]

    for t in state.get("transition_log") or []:
        if t.get("from_stage") and t.get("to_stage"):
            if _edge_idx(edges, t["from_stage"], t["to_stage"]) == -1:
                edges.append({
                    "from": t["from_stage"], "to": t["to_stage"],
                    "kind": "backtrack", "reason": t.get("reason"),
                })

    cursor = {"node_id": current, "agent": None, "started_at": None} if current else None
    return {"nodes": nodes, "edges": edges, "cursor": cursor, "subgraphs": []}

def _edge_idx(edges, s, t):
    for i, e in enumerate(edges):
        if e["from"] == s and e["to"] == t:
            return i
    return -1
```

- [ ] **Step 4: Run tests; verify pass.**

- [ ] **Step 5: Commit.**

```bash
git add agentlabx/core/graph_mapper.py tests/core/test_graph_mapper.py
git commit -m "feat(core): graph_mapper builds owned topology shape with skip/completed/current overlays"
```

### Task B11: Observability endpoints

**Files:**
- Modify: `agentlabx/server/routes/sessions.py`
- Test: `tests/server/test_observability_endpoints.py`

- [ ] **Step 1: Write failing tests.**

```python
# tests/server/test_observability_endpoints.py
import pytest
from httpx import AsyncClient

async def test_graph_endpoint_returns_owned_shape(app, created_session):
    async with AsyncClient(app=app, base_url="http://test") as ac:
        r = await ac.get(f"/api/sessions/{created_session}/graph")
    assert r.status_code == 200
    data = r.json()
    assert set(data.keys()) >= {"nodes", "edges", "cursor", "subgraphs"}

async def test_agents_endpoint_lists_registered(app, created_session):
    async with AsyncClient(app=app, base_url="http://test") as ac:
        r = await ac.get(f"/api/sessions/{created_session}/agents")
    assert r.status_code == 200
    assert isinstance(r.json(), list)

async def test_agent_history_endpoint_paginates(app, created_session):
    async with AsyncClient(app=app, base_url="http://test") as ac:
        r = await ac.get(f"/api/sessions/{created_session}/agents/phd_student/history?limit=50")
    assert r.status_code == 200
    body = r.json()
    assert "turns" in body
    assert isinstance(body["turns"], list)

async def test_pi_history_endpoint(app, created_session):
    async with AsyncClient(app=app, base_url="http://test") as ac:
        r = await ac.get(f"/api/sessions/{created_session}/pi/history")
    assert r.status_code == 200
    assert isinstance(r.json(), list)

async def test_requests_endpoint(app, created_session):
    async with AsyncClient(app=app, base_url="http://test") as ac:
        r = await ac.get(f"/api/sessions/{created_session}/requests")
    assert r.status_code == 200
    data = r.json()
    assert set(data.keys()) == {"pending", "completed"}

async def test_experiments_endpoint(app, created_session):
    async with AsyncClient(app=app, base_url="http://test") as ac:
        r = await ac.get(f"/api/sessions/{created_session}/experiments")
    assert r.status_code == 200
    data = r.json()
    assert set(data.keys()) >= {"runs", "log"}

async def test_missing_session_returns_404(app):
    async with AsyncClient(app=app, base_url="http://test") as ac:
        r = await ac.get("/api/sessions/does-not-exist/graph")
    assert r.status_code == 404
```

- [ ] **Step 2: Run; verify fail.**

- [ ] **Step 3: Implement endpoints.** In `agentlabx/server/routes/sessions.py`, add:

```python
from pydantic import BaseModel
from fastapi import HTTPException, Request
from agentlabx.core.graph_mapper import build_topology
from agentlabx.agents.context import ContextAssembler

class TurnOut(BaseModel):
    turn_id: str
    parent_turn_id: str | None = None
    agent: str
    stage: str
    kind: str
    payload: dict
    system_prompt_hash: str | None = None
    tokens_in: int | None = None
    tokens_out: int | None = None
    cost_usd: float | None = None
    is_mock: bool
    ts: str

class HistoryOut(BaseModel):
    turns: list[TurnOut]
    next_cursor: str | None = None

async def _require_state(request: Request, session_id: str) -> dict:
    """Load latest checkpoint state or raise 404."""
    ctx = request.app.state.context
    state = await ctx.session_manager.load_state(session_id)
    if state is None:
        raise HTTPException(status_code=404, detail=f"session {session_id} not found")
    return state

@router.get("/{session_id}/graph")
async def get_graph(session_id: str, request: Request):
    state = await _require_state(request, session_id)
    compiled = request.app.state.context.pipeline_compiled
    return build_topology(compiled, state)

@router.get("/{session_id}/agents")
async def list_agents(session_id: str, request: Request):
    state = await _require_state(request, session_id)
    registry = request.app.state.context.registry
    out = []
    for name, rec in (state.get("agent_memory") or {}).items():
        cfg = registry.get(PluginType.AGENT, name, default=None)
        out.append({
            "name": name,
            "role": getattr(cfg, "role", name),
            "turn_count": rec.get("turn_count", 0),
            "last_active_stage": rec.get("last_active_stage"),
        })
    return out

@router.get("/{session_id}/agents/{name}/context")
async def get_agent_context(session_id: str, name: str, request: Request):
    state = await _require_state(request, session_id)
    registry = request.app.state.context.registry
    cfg = registry.get(PluginType.AGENT, name, default=None)
    if cfg is None:
        raise HTTPException(status_code=404, detail=f"agent {name} not found")
    assembler = ContextAssembler(cfg.memory_scope)
    preview = assembler.assemble(state, cfg.name)
    return {
        "keys": sorted(list(preview.keys())),
        "preview": preview,
        "scope": {
            "read": list(cfg.memory_scope.read),
            "summarize": dict(cfg.memory_scope.summarize),
            "write": list(cfg.memory_scope.write),
        },
    }

@router.get("/{session_id}/agents/{name}/history", response_model=HistoryOut)
async def get_agent_history(session_id: str, name: str, request: Request, limit: int = 200, after_ts: str | None = None):
    storage = request.app.state.context.storage
    from datetime import datetime
    after = datetime.fromisoformat(after_ts) if after_ts else None
    rows = await storage.list_agent_turns(session_id, agent=name, after_ts=after, limit=limit)
    return HistoryOut(turns=[TurnOut(**{**r.__dict__, "ts": r.ts.isoformat()}) for r in rows])

@router.get("/{session_id}/agents/{name}/memory")
async def get_agent_memory(session_id: str, name: str, request: Request):
    state = await _require_state(request, session_id)
    return (state.get("agent_memory") or {}).get(name) or {
        "working_memory": {}, "notes": [], "last_active_stage": "", "turn_count": 0,
    }

@router.get("/{session_id}/pi/history")
async def get_pi_history(session_id: str, request: Request):
    state = await _require_state(request, session_id)
    return state.get("pi_decisions") or []

@router.get("/{session_id}/requests")
async def get_requests(session_id: str, request: Request):
    state = await _require_state(request, session_id)
    return {
        "pending": state.get("pending_requests") or [],
        "completed": state.get("completed_requests") or [],
    }

@router.get("/{session_id}/experiments")
async def get_experiments(session_id: str, request: Request):
    state = await _require_state(request, session_id)
    runs = []
    for idx, er in enumerate(state.get("experiment_results") or []):
        runs.append({
            "index": idx,
            **(er if isinstance(er, dict) else er.model_dump() if hasattr(er, "model_dump") else {}),
        })
    return {"runs": runs, "log": state.get("experiment_log") or []}
```

- [ ] **Step 4: Run tests; verify pass.**

- [ ] **Step 5: Commit.**

```bash
git add agentlabx/server/routes/sessions.py tests/server/test_observability_endpoints.py
git commit -m "feat(server): 8 observability endpoints — graph, agents, agent context/history/memory, pi history, requests, experiments"
```

### Task B12: Integration test — mock-LLM end-to-end event stream

**Files:**
- Create: `tests/integration/test_mock_llm_event_stream.py`

- [ ] **Step 1: Write the test.**

```python
# tests/integration/test_mock_llm_event_stream.py
import pytest
from httpx import AsyncClient

async def test_mock_llm_pipeline_produces_full_event_stream(app, mock_llm_pipeline, wait_for_completion):
    """Create a session with MockLLMProvider; after one stage runs, verify
    agent_turn_started/llm_request/llm_response/turn_completed fire in order
    with correlated turn_ids, and agent_turns table has matching rows."""
    async with AsyncClient(app=app, base_url="http://test") as ac:
        created = await ac.post("/api/sessions", json={
            "topic": "MATH benchmark scaling study with detailed baselines",
            "user_id": "default",
            "config": {"pipeline": {"skip_stages": [
                "data_exploration","data_preparation","experimentation",
                "results_interpretation","report_writing","peer_review",
            ]}},
        })
        sid = created.json()["session_id"]
        await ac.post(f"/api/sessions/{sid}/start")
        await wait_for_completion(ac, sid)

        h = await ac.get(f"/api/sessions/{sid}/agents/phd_student/history")
    turns = h.json()["turns"]
    kinds = [t["kind"] for t in turns]
    assert "llm_request" in kinds
    assert "llm_response" in kinds
    assert all(t["is_mock"] for t in turns)
```

The `wait_for_completion` fixture (add to `tests/integration/conftest.py`) polls `GET /api/sessions/{id}` until `status == "completed"` or a timeout.

- [ ] **Step 2: Run; verify pass or debug.**

```bash
uv run pytest tests/integration/test_mock_llm_event_stream.py -v
```

- [ ] **Step 3: Commit.**

```bash
git add tests/integration/test_mock_llm_event_stream.py tests/integration/conftest.py
git commit -m "test(integration): mock-LLM pipeline emits full agent turn event stream"
```

### Task B13: Plan 6B checkpoint

- [ ] **Step 1: Run full suite.**

```bash
uv run pytest -v
uv run ruff check agentlabx/
```
Expected: all pass, clean lint.

- [ ] **Step 2: Manual smoke — start server, run `--mock-llm`, curl endpoints.**

```bash
uv run agentlabx serve --mock-llm &
sleep 3
# create a session, then:
curl http://localhost:8000/api/sessions/<sid>/graph | jq '.nodes | length'
curl http://localhost:8000/api/sessions/<sid>/agents | jq
curl http://localhost:8000/api/sessions/<sid>/agents/phd_student/history | jq '.turns | length'
curl http://localhost:8000/api/sessions/<sid>/pi/history | jq
```

- [ ] **Step 3: WebSocket smoke with websocat.**

```bash
websocat ws://localhost:8000/ws/sessions/<sid>
# Create and start a new session in another terminal; observe agent_turn_started,
# agent_llm_request, agent_llm_response, agent_turn_completed events stream.
```

- [ ] **Step 4: Tag Plan 6B complete.**

```bash
git tag plan6b-complete
```

---

## Summary

Plan 6B complete when:
- 14 event types defined in `EventTypes`; `AGENT_THINKING` legacy name removed
- `TurnContext` + ContextVar correlate per-turn events asyncio-safely
- `TracedLLMProvider` + `TracedTool` wrap provider/tool boundaries; emit request/response/call/result events; write `agent_turns` rows
- `ConfigAgent.inference()` emits `agent_turn_started/completed` with rich metadata (system_prompt_hash, assembled_context_keys, memory_scope_applied, is_mock)
- `PIAgent.decide()` emits `pi_decision`, appends to `state["pi_decisions"]`
- `ExperimentationStage` appends `ExperimentAttempt` with outcome classification; `ExperimentResult` carries `exit_code`, `stdout`, `stderr`, `execution_time`
- `results_interpretation` emits `hypothesis_update` per change
- `graph_mapper.build_topology` returns the owned `{nodes, edges, cursor, subgraphs}` shape
- 8 observability endpoints return real data; 404 on missing session
- End-to-end mock-LLM integration test asserts full event stream
- `websocat` + `curl` smoke shows backend fully observable

Next: Plan 6C (frontend UI — graph canvas, chat view, agent monitor, experiments tab).
