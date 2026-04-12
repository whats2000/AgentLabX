# Plan 6A: Data Plane Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Land the persistence substrate for observability — agent memory survives across stages, three new state keys exist, `agent_turns` append-only table is populated-capable, binding spec edits land.

**Architecture:** Split agent memory into two stores: scratchpad (working_memory, notes, turn_count, last_active_stage) lives in `PipelineState.agent_memory` and rides the LangGraph checkpoint; conversation turns live in a new `agent_turns` SQLAlchemy table with `(session_id, agent, ts)` + `(session_id, stage, ts)` indexes. Extend `BaseStorageBackend` with `append_agent_turn` / `list_agent_turns`. Extend `BaseAgent` with dirty-flag tracking and snapshot/load helpers. `resolve_agent` hydrates from state on instantiation; a new `sync_agent_memory_to_state` helper writes dirty agents back at stage boundaries. No events, no endpoints, no UI.

**Tech Stack:** Python 3.12, SQLAlchemy 2 async, Pydantic v2 (for TypedDict additions), pytest.

**Companion spec:** `docs/superpowers/specs/2026-04-13-plan6-observability-design.md` §3.1.
**Depends on:** nothing — Plan 6A is the first phase of the observability rollout.
**Unblocks:** Plan 6B (event plane + endpoints).

---

## File Structure Map

**Created:**
```
tests/core/test_state.py                      # state keys + type shapes
tests/storage/test_agent_turns_model.py       # AgentTurn columns + indexes
tests/storage/test_agent_turns.py             # append + list with filters
tests/providers/llm/test_is_mock.py
tests/agents/test_base_memory.py
tests/stages/test_resolve_agent_memory.py
tests/stages/test_base_on_exit_memory_sync.py
```

**Modified:**
```
docs/superpowers/specs/2026-04-12-agentlabx-platform-design.md   # binding edits (Task A0)
agentlabx/core/state.py                       # +agent_memory, +experiment_log, +pi_decisions, +types
agentlabx/providers/storage/base.py           # +AgentTurnRecord, +append_agent_turn, +list_agent_turns
agentlabx/providers/storage/models.py         # +AgentTurn model
agentlabx/providers/storage/sqlite_backend.py # implement new methods
agentlabx/providers/llm/base.py               # +is_mock class attr
agentlabx/providers/llm/mock_provider.py      # is_mock=True
agentlabx/agents/base.py                      # +dirty flag, +notes, +snapshot/load
agentlabx/stages/_helpers.py                  # resolve_agent hydrates from state
agentlabx/stages/base.py                      # +sync_agent_memory_to_state helper
agentlabx/stages/*.py                         # opt-in memory write-back in each stage
tests/conftest.py                             # +sample_agent_config, +sample_registry fixtures
```

---

### Task A0: Binding spec edits to platform design

**Files:**
- Modify: `docs/superpowers/specs/2026-04-12-agentlabx-platform-design.md`

- [ ] **Step 1: Apply §3.4 state edits.** Open the spec and under §3.4's `PipelineState` TypedDict block, append after `errors: list[StageError]`:

```python
# Agent observability (Plan 6)
agent_memory: dict[str, AgentMemoryRecord]   # per-agent scratchpad
experiment_log: list[ExperimentAttempt]      # cross-agent failure memory
pi_decisions: list[dict]                     # PIDecision.model_dump() list
```

- [ ] **Step 2: Apply §3.x new type definitions.** Add under §3.5 (before §3.6):

```python
class AgentMemoryRecord(TypedDict):
    working_memory: dict[str, Any]
    notes: list[str]
    last_active_stage: str
    turn_count: int

class ExperimentAttempt(TypedDict):
    attempt_id: str
    approach_summary: str
    outcome: Literal["success", "failure", "inconclusive"]
    failure_reason: str | None
    learnings: list[str]
    linked_hypothesis_id: str | None
    ts: datetime
```

- [ ] **Step 3: Replace §4.3 Working Memory text.** Replace the current §4.3 body with the concretized mechanism from the design companion §2.3. Exact text is in `docs/superpowers/specs/2026-04-13-plan6-observability-design.md` §2.3 (two-paragraph form).

- [ ] **Step 4: Extend §7.1 REST API table.** Add 8 rows from design companion §2.4 verbatim.

- [ ] **Step 5: Replace §7.2 event taxonomy.** Replace the existing server→client event list with the full table from design companion §2.5 (14 events). Client→server actions unchanged.

- [ ] **Step 6: Update §8.2 Session Detail paragraph** to the stacked-canvas description from design companion §2.6.

- [ ] **Step 7: Update §8.3 component list.** Remove `PipelineGraph`. Add `GraphTopology`, `ChatView`, `AgentMonitor`, `AgentScopeCard`, `AgentContextPreview`, `AgentMemoryCard`, `AgentHistoryCard`, `ExperimentsTab`, `ExperimentDetail`, `ExperimentDiffView`, `PIDecisionLog`.

- [ ] **Step 8: Commit.**

```bash
git add docs/superpowers/specs/2026-04-12-agentlabx-platform-design.md
git commit -m "docs(spec): apply Plan 6 binding edits — state keys, endpoints, event taxonomy, UI reframe"
```

### Task A1: Add state types and keys

**Files:**
- Modify: `agentlabx/core/state.py`
- Test: `tests/core/test_state.py` (if exists; otherwise create)

- [ ] **Step 1: Write failing test.**

```python
# tests/core/test_state.py
def test_pipeline_state_has_observability_keys():
    from agentlabx.core.state import PipelineState, AgentMemoryRecord, ExperimentAttempt

    ann = PipelineState.__annotations__
    assert "agent_memory" in ann
    assert "experiment_log" in ann
    assert "pi_decisions" in ann

def test_agent_memory_record_shape():
    from agentlabx.core.state import AgentMemoryRecord

    rec: AgentMemoryRecord = {
        "working_memory": {"foo": "bar"},
        "notes": ["note1"],
        "last_active_stage": "plan_formulation",
        "turn_count": 3,
    }
    assert rec["turn_count"] == 3

def test_experiment_attempt_shape():
    from agentlabx.core.state import ExperimentAttempt
    from datetime import datetime

    att: ExperimentAttempt = {
        "attempt_id": "att-1",
        "approach_summary": "CoT with 5-shot",
        "outcome": "failure",
        "failure_reason": "timeout",
        "learnings": ["too slow"],
        "linked_hypothesis_id": "H1",
        "ts": datetime.now(),
    }
    assert att["outcome"] == "failure"
```

- [ ] **Step 2: Run tests; verify they fail.**

```bash
uv run pytest tests/core/test_state.py -v
```
Expected: ImportError on `AgentMemoryRecord` / `ExperimentAttempt`.

- [ ] **Step 3: Add types and keys to state.**

```python
# At the top of agentlabx/core/state.py (alongside other TypedDict definitions)
from typing import Literal

class AgentMemoryRecord(TypedDict):
    working_memory: dict[str, Any]
    notes: list[str]
    last_active_stage: str
    turn_count: int

class ExperimentAttempt(TypedDict):
    attempt_id: str
    approach_summary: str
    outcome: Literal["success", "failure", "inconclusive"]
    failure_reason: str | None
    learnings: list[str]
    linked_hypothesis_id: str | None
    ts: datetime
```

Then in the `PipelineState` TypedDict, after `errors: Annotated[list[StageError], operator.add]`, append:

```python
    # Observability (Plan 6)
    # agent_memory is dict merge via last-write-wins; use custom reducer below.
    agent_memory: dict[str, AgentMemoryRecord]
    experiment_log: Annotated[list[ExperimentAttempt], operator.add]
    pi_decisions: Annotated[list[dict], operator.add]
```

- [ ] **Step 4: Run tests; verify they pass.**

```bash
uv run pytest tests/core/test_state.py -v
```
Expected: 3 passed.

- [ ] **Step 5: Also update the initial-state builder.** Find the function that initializes `PipelineState` (search `state.py` for `def create_initial_state` or similar). Add default empties:

```python
    "agent_memory": {},
    "experiment_log": [],
    "pi_decisions": [],
```

- [ ] **Step 6: Commit.**

```bash
git add agentlabx/core/state.py tests/core/test_state.py
git commit -m "feat(state): add agent_memory, experiment_log, pi_decisions keys with TypedDict records"
```

### Task A2: Add AgentTurn SQLAlchemy model

**Files:**
- Modify: `agentlabx/providers/storage/models.py`
- Test: `tests/storage/test_agent_turns_model.py`

- [ ] **Step 1: Write failing test.**

```python
# tests/storage/test_agent_turns_model.py
def test_agent_turn_model_columns():
    from agentlabx.providers.storage.models import AgentTurn

    cols = {c.name for c in AgentTurn.__table__.columns}
    assert cols >= {
        "id", "session_id", "turn_id", "parent_turn_id",
        "agent", "stage", "kind", "payload_json",
        "system_prompt_hash", "tokens_in", "tokens_out",
        "cost_usd", "is_mock", "ts",
    }

def test_agent_turn_indexes():
    from agentlabx.providers.storage.models import AgentTurn

    idx_names = {idx.name for idx in AgentTurn.__table__.indexes}
    assert "ix_agent_turns_session_agent_ts" in idx_names
    assert "ix_agent_turns_session_stage_ts" in idx_names
```

- [ ] **Step 2: Run; verify fail** (`ImportError: cannot import name 'AgentTurn'`).

- [ ] **Step 3: Add the model.** Append to `agentlabx/providers/storage/models.py`:

```python
class AgentTurn(Base):
    __tablename__ = "agent_turns"
    __table_args__ = (
        Index("ix_agent_turns_session_agent_ts", "session_id", "agent", "ts"),
        Index("ix_agent_turns_session_stage_ts", "session_id", "stage", "ts"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    session_id: Mapped[str] = mapped_column(String, nullable=False, index=True)
    turn_id: Mapped[str] = mapped_column(String, nullable=False)
    parent_turn_id: Mapped[str | None] = mapped_column(String, nullable=True)
    agent: Mapped[str] = mapped_column(String, nullable=False)
    stage: Mapped[str] = mapped_column(String, nullable=False)
    kind: Mapped[str] = mapped_column(String, nullable=False)
    payload_json: Mapped[str] = mapped_column(Text, nullable=False)
    system_prompt_hash: Mapped[str | None] = mapped_column(String, nullable=True)
    tokens_in: Mapped[int | None] = mapped_column(Integer, nullable=True)
    tokens_out: Mapped[int | None] = mapped_column(Integer, nullable=True)
    cost_usd: Mapped[float | None] = mapped_column(Float, nullable=True)
    is_mock: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    ts: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)
```

Add imports at top if missing: `from sqlalchemy import Index, Text, Float, Boolean`.

- [ ] **Step 4: Run tests; verify pass.**

```bash
uv run pytest tests/storage/test_agent_turns_model.py -v
```

- [ ] **Step 5: Commit.**

```bash
git add agentlabx/providers/storage/models.py tests/storage/test_agent_turns_model.py
git commit -m "feat(storage): add AgentTurn SQLAlchemy model with session/agent and session/stage indexes"
```

### Task A3: Extend BaseStorageBackend ABC

**Files:**
- Modify: `agentlabx/providers/storage/base.py`

- [ ] **Step 1: Add a `AgentTurnRecord` dataclass at the top of `base.py`:**

```python
from dataclasses import dataclass
from datetime import datetime
from typing import Literal

AgentTurnKind = Literal["llm_request", "llm_response", "tool_call", "tool_result", "dialogue"]

@dataclass
class AgentTurnRecord:
    session_id: str
    turn_id: str
    agent: str
    stage: str
    kind: AgentTurnKind
    payload: dict
    parent_turn_id: str | None = None
    system_prompt_hash: str | None = None
    tokens_in: int | None = None
    tokens_out: int | None = None
    cost_usd: float | None = None
    is_mock: bool = False
    ts: datetime | None = None   # filled by backend if None
```

- [ ] **Step 2: Append two abstract methods to `BaseStorageBackend`:**

```python
    @abstractmethod
    async def append_agent_turn(self, record: AgentTurnRecord) -> int:
        """Insert one agent turn. Returns the row id."""

    @abstractmethod
    async def list_agent_turns(
        self,
        session_id: str,
        *,
        agent: str | None = None,
        stage: str | None = None,
        after_ts: datetime | None = None,
        limit: int = 200,
    ) -> list[AgentTurnRecord]:
        """List turns ordered by ts ascending. Filters optional."""
```

- [ ] **Step 3: Commit.**

```bash
git add agentlabx/providers/storage/base.py
git commit -m "feat(storage): extend BaseStorageBackend with append_agent_turn and list_agent_turns"
```

### Task A4: Implement agent turns on SQLiteBackend

**Files:**
- Modify: `agentlabx/providers/storage/sqlite_backend.py`
- Test: `tests/storage/test_agent_turns.py`

- [ ] **Step 1: Write failing test.**

```python
# tests/storage/test_agent_turns.py
import pytest
from datetime import datetime, timedelta
from agentlabx.providers.storage.base import AgentTurnRecord
from agentlabx.providers.storage.sqlite_backend import SQLiteBackend

@pytest.fixture
async def backend(tmp_path):
    b = SQLiteBackend(db_path=str(tmp_path / "test.db"), artifacts_path=str(tmp_path / "art"))
    await b.initialize()
    yield b
    await b.close()

async def test_append_and_list_turn(backend):
    rec = AgentTurnRecord(
        session_id="s1", turn_id="t1", agent="phd_student",
        stage="literature_review", kind="llm_request",
        payload={"model": "gpt-4o", "prompt": "hi"},
    )
    row_id = await backend.append_agent_turn(rec)
    assert row_id > 0

    rows = await backend.list_agent_turns("s1")
    assert len(rows) == 1
    assert rows[0].turn_id == "t1"
    assert rows[0].payload["model"] == "gpt-4o"

async def test_list_filters_by_agent(backend):
    await backend.append_agent_turn(AgentTurnRecord(
        session_id="s1", turn_id="t1", agent="a1", stage="x", kind="llm_request", payload={}))
    await backend.append_agent_turn(AgentTurnRecord(
        session_id="s1", turn_id="t2", agent="a2", stage="x", kind="llm_request", payload={}))

    only_a1 = await backend.list_agent_turns("s1", agent="a1")
    assert len(only_a1) == 1 and only_a1[0].agent == "a1"

async def test_list_filters_by_stage_and_after_ts(backend):
    t0 = datetime.utcnow()
    await backend.append_agent_turn(AgentTurnRecord(
        session_id="s1", turn_id="t1", agent="a1", stage="s1stage",
        kind="llm_request", payload={}, ts=t0))
    await backend.append_agent_turn(AgentTurnRecord(
        session_id="s1", turn_id="t2", agent="a1", stage="s2stage",
        kind="llm_request", payload={}, ts=t0 + timedelta(seconds=1)))

    rows = await backend.list_agent_turns("s1", stage="s1stage")
    assert len(rows) == 1

    rows = await backend.list_agent_turns("s1", after_ts=t0)
    assert len(rows) == 1 and rows[0].turn_id == "t2"
```

- [ ] **Step 2: Run; verify fail** (`NotImplementedError` or attribute error).

- [ ] **Step 3: Implement on SQLiteBackend.** Add methods:

```python
from agentlabx.providers.storage.models import AgentTurn
from agentlabx.providers.storage.base import AgentTurnRecord
import json
from sqlalchemy import select

    async def append_agent_turn(self, record: AgentTurnRecord) -> int:
        async with self._session_factory() as session:
            row = AgentTurn(
                session_id=record.session_id,
                turn_id=record.turn_id,
                parent_turn_id=record.parent_turn_id,
                agent=record.agent,
                stage=record.stage,
                kind=record.kind,
                payload_json=json.dumps(record.payload, default=str),
                system_prompt_hash=record.system_prompt_hash,
                tokens_in=record.tokens_in,
                tokens_out=record.tokens_out,
                cost_usd=record.cost_usd,
                is_mock=record.is_mock,
                ts=record.ts or datetime.utcnow(),
            )
            session.add(row)
            await session.commit()
            await session.refresh(row)
            return row.id

    async def list_agent_turns(
        self, session_id, *, agent=None, stage=None, after_ts=None, limit=200,
    ) -> list[AgentTurnRecord]:
        async with self._session_factory() as session:
            stmt = select(AgentTurn).where(AgentTurn.session_id == session_id)
            if agent is not None:
                stmt = stmt.where(AgentTurn.agent == agent)
            if stage is not None:
                stmt = stmt.where(AgentTurn.stage == stage)
            if after_ts is not None:
                stmt = stmt.where(AgentTurn.ts > after_ts)
            stmt = stmt.order_by(AgentTurn.ts.asc()).limit(limit)
            rows = (await session.execute(stmt)).scalars().all()
            return [
                AgentTurnRecord(
                    session_id=r.session_id,
                    turn_id=r.turn_id,
                    parent_turn_id=r.parent_turn_id,
                    agent=r.agent,
                    stage=r.stage,
                    kind=r.kind,
                    payload=json.loads(r.payload_json),
                    system_prompt_hash=r.system_prompt_hash,
                    tokens_in=r.tokens_in,
                    tokens_out=r.tokens_out,
                    cost_usd=r.cost_usd,
                    is_mock=bool(r.is_mock),
                    ts=r.ts,
                )
                for r in rows
            ]
```

- [ ] **Step 4: Run tests; verify pass.**

```bash
uv run pytest tests/storage/test_agent_turns.py -v
```

- [ ] **Step 5: Commit.**

```bash
git add agentlabx/providers/storage/sqlite_backend.py tests/storage/test_agent_turns.py
git commit -m "feat(storage): implement append_agent_turn and list_agent_turns on SQLiteBackend"
```

### Task A5: `is_mock` attribute on LLM providers

**Files:**
- Modify: `agentlabx/providers/llm/base.py`
- Modify: `agentlabx/providers/llm/mock_provider.py`
- Test: `tests/providers/llm/test_is_mock.py`

- [ ] **Step 1: Write failing test.**

```python
# tests/providers/llm/test_is_mock.py
def test_base_llm_provider_default_is_mock_false():
    from agentlabx.providers.llm.base import BaseLLMProvider
    assert BaseLLMProvider.is_mock is False

def test_mock_llm_provider_is_mock_true():
    from agentlabx.providers.llm.mock_provider import MockLLMProvider
    p = MockLLMProvider(responses=[])
    assert p.is_mock is True
```

- [ ] **Step 2: Run; verify fail.**

- [ ] **Step 3: Add attribute.**

In `agentlabx/providers/llm/base.py`, on `BaseLLMProvider`:
```python
    is_mock: bool = False
```

In `agentlabx/providers/llm/mock_provider.py`, on `MockLLMProvider`:
```python
    is_mock: bool = True
```

- [ ] **Step 4: Run tests; verify pass.**

- [ ] **Step 5: Commit.**

```bash
git add agentlabx/providers/llm/base.py agentlabx/providers/llm/mock_provider.py tests/providers/llm/test_is_mock.py
git commit -m "feat(llm): add is_mock class attribute to BaseLLMProvider; MockLLMProvider sets True"
```

### Task A6: BaseAgent gains dirty flag and notes list

**Files:**
- Modify: `agentlabx/agents/base.py`
- Test: `tests/agents/test_base_memory.py`

- [ ] **Step 1: Write failing test.**

```python
# tests/agents/test_base_memory.py
def test_base_agent_has_dirty_flag():
    from agentlabx.agents.config_agent import ConfigAgent
    from agentlabx.agents.config_loader import AgentConfig
    from agentlabx.agents.context import MemoryScope

    cfg = AgentConfig(
        name="tester", role="tester", system_prompt="sp",
        memory_scope=MemoryScope(read=[], summarize={}, write=[]),
        tools=[], phases=[],
    )
    a = ConfigAgent(cfg)
    assert a.dirty is False
    assert a.notes == []

    a.add_note("hello")
    assert a.dirty is True
    assert a.notes == ["hello"]

    a.dirty = False
    a.working_memory["foo"] = "bar"   # direct mutation doesn't set dirty
    a.mark_dirty()
    assert a.dirty is True
```

- [ ] **Step 2: Run; verify fail.**

- [ ] **Step 3: Extend BaseAgent.** In `agentlabx/agents/base.py`, in `__init__`:

```python
        self.notes: list[str] = []
        self.turn_count: int = 0
        self.last_active_stage: str = ""
        self.dirty: bool = False
```

Add helpers on the class:

```python
    def add_note(self, note: str) -> None:
        self.notes.append(note)
        self.dirty = True

    def mark_dirty(self) -> None:
        self.dirty = True

    def snapshot_memory(self) -> dict:
        """Return an AgentMemoryRecord-shaped dict."""
        return {
            "working_memory": dict(self.working_memory),
            "notes": list(self.notes),
            "last_active_stage": self.last_active_stage,
            "turn_count": self.turn_count,
        }

    def load_memory(self, record: dict) -> None:
        self.working_memory = dict(record.get("working_memory", {}))
        self.notes = list(record.get("notes", []))
        self.last_active_stage = record.get("last_active_stage", "")
        self.turn_count = int(record.get("turn_count", 0))
        self.dirty = False
```

- [ ] **Step 4: Run tests; verify pass.**

- [ ] **Step 5: Commit.**

```bash
git add agentlabx/agents/base.py tests/agents/test_base_memory.py
git commit -m "feat(agents): add notes/turn_count/dirty tracking and snapshot/load helpers on BaseAgent"
```

### Task A7: `resolve_agent` hydrates agent memory from state

**Files:**
- Modify: `agentlabx/stages/_helpers.py`
- Modify: `tests/conftest.py` (fixtures)
- Test: `tests/stages/test_resolve_agent_memory.py`

- [ ] **Step 1: Add fixtures in `tests/conftest.py`:**

```python
# tests/conftest.py (additions)
import pytest
from agentlabx.agents.config_loader import AgentConfig
from agentlabx.agents.context import MemoryScope
from agentlabx.core.registry import PluginRegistry, PluginType

@pytest.fixture
def sample_agent_config():
    return AgentConfig(
        name="phd_student", role="phd student", system_prompt="You are a PhD.",
        memory_scope=MemoryScope(read=["*"], summarize={}, write=["plan"]),
        tools=[], phases=[],
    )

@pytest.fixture
def sample_registry(sample_agent_config):
    r = PluginRegistry()
    r.register(PluginType.AGENT, sample_agent_config.name, sample_agent_config)
    return r
```

- [ ] **Step 2: Write failing test.**

```python
# tests/stages/test_resolve_agent_memory.py
from agentlabx.stages._helpers import resolve_agent

def test_resolve_agent_hydrates_from_state(sample_registry):
    state = {
        "agent_memory": {
            "phd_student": {
                "working_memory": {"focus": "MATH"},
                "notes": ["found 3 relevant papers"],
                "last_active_stage": "literature_review",
                "turn_count": 7,
            }
        }
    }
    agent = resolve_agent(sample_registry, "phd_student", state=state)
    assert agent.working_memory == {"focus": "MATH"}
    assert agent.notes == ["found 3 relevant papers"]
    assert agent.turn_count == 7
    assert agent.dirty is False

def test_resolve_agent_with_no_prior_memory(sample_registry):
    state = {"agent_memory": {}}
    agent = resolve_agent(sample_registry, "phd_student", state=state)
    assert agent.working_memory == {}
    assert agent.notes == []
    assert agent.turn_count == 0
```

- [ ] **Step 3: Run; verify fail** (`resolve_agent` doesn't accept `state` kwarg yet).

- [ ] **Step 4: Update `resolve_agent`.** In `agentlabx/stages/_helpers.py`, add `state` kwarg and hydrate after instantiation:

```python
def resolve_agent(
    registry,
    name: str,
    *,
    llm_provider=None,
    model: str = "claude-sonnet-4-6",
    cost_tracker=None,
    state: dict | None = None,
):
    # ... existing resolution logic that produces `agent` ...

    if state is not None:
        memory_dict = (state.get("agent_memory") or {}).get(name)
        if memory_dict:
            agent.load_memory(memory_dict)
    return agent
```

Keep backward-compatible call sites unchanged — `state=None` produces identical behavior to before.

- [ ] **Step 5: Run tests; verify pass.**

- [ ] **Step 6: Commit.**

```bash
git add agentlabx/stages/_helpers.py tests/stages/test_resolve_agent_memory.py tests/conftest.py
git commit -m "feat(stages): resolve_agent hydrates BaseAgent memory from state[agent_memory]"
```

### Task A8: Stage `on_exit` syncs dirty agent memory back to state

**Files:**
- Modify: `agentlabx/stages/base.py`
- Test: `tests/stages/test_base_on_exit_memory_sync.py`

- [ ] **Step 1: Write failing test.**

```python
# tests/stages/test_base_on_exit_memory_sync.py
from agentlabx.stages.base import sync_agent_memory_to_state
from agentlabx.stages._helpers import resolve_agent

def test_sync_dirty_agent_writes_to_state(sample_registry):
    state = {"agent_memory": {}}
    agent = resolve_agent(sample_registry, "phd_student", state=state)
    agent.add_note("key insight")
    agent.last_active_stage = "plan_formulation"

    sync_agent_memory_to_state(state, {"phd_student": agent})
    assert state["agent_memory"]["phd_student"]["notes"] == ["key insight"]
    assert state["agent_memory"]["phd_student"]["last_active_stage"] == "plan_formulation"
    assert agent.dirty is False

def test_sync_skips_clean_agents(sample_registry):
    state = {"agent_memory": {"phd_student": {"notes": ["existing"], "working_memory": {}, "last_active_stage": "", "turn_count": 0}}}
    agent = resolve_agent(sample_registry, "phd_student", state=state)
    sync_agent_memory_to_state(state, {"phd_student": agent})
    assert state["agent_memory"]["phd_student"]["notes"] == ["existing"]
```

- [ ] **Step 2: Run; verify fail.**

- [ ] **Step 3: Add helper in `agentlabx/stages/base.py`:**

```python
def sync_agent_memory_to_state(state: dict, agents: dict[str, "BaseAgent"]) -> None:
    """Write each dirty agent's snapshot into state[agent_memory][name]. Clears dirty flags."""
    memory = state.setdefault("agent_memory", {})
    for name, agent in agents.items():
        if getattr(agent, "dirty", False):
            memory[name] = agent.snapshot_memory()
            agent.dirty = False
```

- [ ] **Step 4: Run tests; verify pass.**

- [ ] **Step 5: Commit.**

```bash
git add agentlabx/stages/base.py tests/stages/test_base_on_exit_memory_sync.py
git commit -m "feat(stages): add sync_agent_memory_to_state helper for dirty-flag-aware write-back"
```

### Task A9: Opt-in memory write-back in stages that use agents

**Files:**
- Modify: every stage file in `agentlabx/stages/` that calls `resolve_agent` (literature_review, plan_formulation, data_exploration, data_preparation, experimentation, results_interpretation, report_writing, peer_review, lab_meeting)

- [ ] **Step 1: For each stage file, pass `state=state` to `resolve_agent` and call `sync_agent_memory_to_state` before returning.** The pattern is:

```python
from agentlabx.stages.base import sync_agent_memory_to_state

# In run():
agent = resolve_agent(context.registry, "phd_student", llm_provider=..., state=state)
# ... agent work ...

# Before returning StageResult:
sync_agent_memory_to_state(state, {"phd_student": agent})
```

- [ ] **Step 2: Integration smoke — run existing full pipeline test.**

```bash
uv run pytest tests/integration/ -v
```
Expected: all pass (memory sync is additive; no semantic change when agents don't mutate memory).

- [ ] **Step 3: Commit.**

```bash
git add agentlabx/stages/
git commit -m "feat(stages): opt-in agent memory write-back via sync_agent_memory_to_state in every stage"
```

### Task A10: Phase A checkpoint — tests green, no UI/event changes

- [ ] **Step 1: Run full backend test suite.**

```bash
uv run pytest -v
```
Expected: all pass.

- [ ] **Step 2: Run ruff lint.**

```bash
uv run ruff check agentlabx/
uv run ruff format --check agentlabx/
```
Expected: clean.

- [ ] **Step 3: Tag Plan 6A complete.**

```bash
git tag plan6a-complete
```

---

## Summary

Plan 6A complete when:
- `PipelineState.agent_memory`, `experiment_log`, `pi_decisions` keys exist with correct TypedDict shapes
- `agent_turns` SQLAlchemy table exists with correct columns and indexes
- `BaseStorageBackend.append_agent_turn` / `list_agent_turns` implemented on `SQLiteBackend` with tests covering filter combinations
- `BaseAgent` carries dirty flag, notes, turn_count, last_active_stage; supports `snapshot_memory()` / `load_memory()`
- `resolve_agent(state=...)` hydrates; `sync_agent_memory_to_state(state, agents)` writes back
- Every stage that uses agents calls both hydration and write-back
- Binding spec edits landed in Task A0
- Full pytest suite + ruff clean; zero events/endpoints/UI changes

Next: Plan 6B (event plane + endpoints).
