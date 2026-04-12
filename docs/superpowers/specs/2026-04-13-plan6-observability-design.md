# Plan 6: Observability — Design Companion

**Date:** 2026-04-13
**Status:** Design complete; ready for implementation planning
**Scope:** Turn-grained observability for AgentLabX — agent events, agent memory persistence, owned graph topology, new API surface, reworked frontend layout

**Relationship to platform spec:** This document is a design-rationale companion. Binding spec changes land as edits to `docs/superpowers/specs/2026-04-12-agentlabx-platform-design.md` §3.4, §3.8, §4.3, §7.1, §7.2, §8. See Section 2 below for the exact edits.

---

## 1. Problem

The current web UI reduces a session to "8 stages ran, here are the artifacts, here's the total cost." A user watching `agentlabx serve --mock-llm` cannot verify:

- Which agent said what, with which LLM prompt, to which tool
- Whether memory scope isolation actually worked (did the reviewer really not see the plan?)
- What the PI agent decided and why, with what confidence
- Whether a hypothesis was supported/refuted by actual evidence or an LLM hallucination
- Whether an experiment's reproducibility record is complete
- Whether the pipeline is about to repeat a prior failed experiment

The scaffolding is sound (typed client, WS with refcount teardown, TanStack/Zustand split). The problem is that the components render stage-level bookends instead of turn-level research activity, and the backend never emits the events that would let them do better. The fix is: emit events from the hot paths, persist agent memory, expose new introspection endpoints, and rebuild the frontend around them.

## 2. Spec edits (binding)

The following changes land in `docs/superpowers/specs/2026-04-12-agentlabx-platform-design.md` as the first commit of implementation.

### 2.1 §3.4 — PipelineState gets three new keys

```python
# appended to PipelineState
agent_memory: dict[str, AgentMemoryRecord]   # per-agent scratchpad, keyed by agent name
experiment_log: list[ExperimentAttempt]      # cross-agent failure memory (Plan 6 scaffolding)
pi_decisions: list[PIDecision]               # PI agent decision log, moved off ephemeral instance
```

### 2.2 §3 — add new domain types

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

class PIDecision(TypedDict):
    decision_id: str
    action: str                  # "advance" | "backtrack" | "iterate" | "accept_negative" | "pivot" | "complete" | "flag_human"
    confidence: float
    next_stage: str | None
    reasoning: str
    used_fallback: bool           # true when confidence < threshold and default sequence applied
    ts: datetime
```

### 2.3 §4.3 — concretize working memory mechanism

Replace current §4.3 text with:

> Agent memory persists in two places:
>
> 1. **Scratchpad state** — `PipelineState.agent_memory[agent_name]` holds `working_memory`, `notes`, `last_active_stage`, and `turn_count`. Loaded by `resolve_agent` on instantiation; written back by the stage `on_exit` hook when dirty. Rides the LangGraph checkpoint automatically.
>
> 2. **Conversation turns** — separate append-only `agent_turns` table in the storage backend. Indexed by `(session_id, agent, ts)` and `(session_id, stage, ts)`. Kept out of checkpoint state to prevent blob growth on long sessions.
>
> Every `ConfigAgent.inference()` call creates one logical *turn* with a UUID `turn_id`. LLM requests, LLM responses, and nested tool calls produced by that inference share the same `turn_id` (tool calls that internally trigger another inference get a `parent_turn_id` pointer). This is the correlation key for chat-style rendering and for filtering a single "what did this agent say?" view.

### 2.4 §7.1 — new REST endpoints

| Method | Endpoint | Purpose |
|---|---|---|
| GET | `/api/sessions/{id}/graph` | Owned topology — nodes, edges, cursor, subgraphs |
| GET | `/api/sessions/{id}/agents` | List agents registered for this session |
| GET | `/api/sessions/{id}/agents/{name}/context` | Post-scope-filter assembled context snapshot |
| GET | `/api/sessions/{id}/agents/{name}/history` | Paginated `agent_turns` for this agent |
| GET | `/api/sessions/{id}/agents/{name}/memory` | AgentMemoryRecord scratchpad |
| GET | `/api/sessions/{id}/pi/history` | PI decision log with confidence + used_fallback |
| GET | `/api/sessions/{id}/requests` | Pending + completed CrossStageRequest |
| GET | `/api/sessions/{id}/experiments` | ExperimentResult + ExperimentAttempt log + refs |

### 2.5 §7.2 — event taxonomy replaced (no backward compat)

AgentLabX has not shipped a stable release; existing event listeners are internal only. The prior draft names `agent_thinking` and bare `agent_tool_call` are removed and replaced:

**Server → Client events:**

| Event | Payload |
|---|---|
| `stage_started` | {stage, agents, started_at} |
| `stage_completed` | {stage, status, summary, elapsed_ms} |
| `stage_failed` | {stage, error} |
| `agent_turn_started` | {turn_id, agent, stage, started_at, system_prompt_hash, system_prompt_preview, assembled_context_keys, memory_scope_applied, is_mock} |
| `agent_turn_completed` | {turn_id, elapsed_ms, tokens_in_total, tokens_out_total, cost_usd} |
| `agent_llm_request` | {turn_id, parent_turn_id?, model, messages, temperature, is_mock} |
| `agent_llm_response` | {turn_id, content, tokens_in, tokens_out, cost_usd, model, is_mock} |
| `agent_tool_call` | {turn_id, parent_turn_id?, tool, args} |
| `agent_tool_result` | {turn_id, tool, success, result_preview, error?} |
| `agent_dialogue` | {turn_id, from_agent, to_agent, message} |
| `pi_decision` | {decision_id, action, confidence, next_stage, reasoning, used_fallback} |
| `hypothesis_update` | {hypothesis_id, new_status, evidence_link?} |
| `checkpoint_reached` | unchanged |
| `cost_update` | unchanged |
| `error` | unchanged |

Content fields are truncated at 8KB on the wire; full payloads retrievable from `/agents/{name}/history`.

**Client → Server actions:** unchanged.

### 2.6 §8.2 / §8.3 — layout reframed, new components listed

Replace the Session Detail paragraph in §8.2 with:

> The center splits vertically. Top: an always-visible `GraphTopology` canvas showing the live pipeline with rich nodes (status dot, elapsed time, iteration count, current agent, per-stage control dropdown, per-stage cost). Bottom: tabs — Conversations (default), Artifacts, Experiments, Cost.
>
> The left sider carries only global controls: Pause, Resume, Cancel. Per-stage control levels live on the graph nodes, not in a parallel list.
>
> The right sider is the Agent Monitor. For the currently-focused agent it shows memory scope (read/summarize/write keys), assembled-context preview (what this agent saw on its last turn), conversation history (paginated), and scratchpad (working_memory + notes). Focus follows the latest `agent_turn_started` event unless pinned. Below the monitor: Hypotheses (unchanged), PI decision log (last N), compact Cost tracker.

Add to §8.3 component list: `GraphTopology`, `ChatView` (with `mode` prop reserved for future `lab_scene`), `AgentMonitor`, `AgentScopeCard`, `AgentContextPreview`, `AgentMemoryCard`, `AgentHistoryCard`, `ExperimentsTab`, `ExperimentDetail`, `ExperimentDiffView`, `PIDecisionLog`.

Remove from §8.3: `PipelineGraph` (old hardcoded version).

---

## 3. Backend design

### 3.1 Data plane

**New SQLAlchemy table `agent_turns`:**

```python
class AgentTurn(Base):
    id: int                            # PK
    session_id: str                    # FK, indexed
    turn_id: str                       # UUID, correlates request/response/tool-calls within one inference
    parent_turn_id: str | None         # For nested sub-turns (tool call → sub-inference)
    agent: str
    stage: str
    kind: Literal["llm_request", "llm_response", "tool_call", "tool_result", "dialogue"]
    payload_json: str                  # Full payload (not the 8KB-truncated wire version)
    system_prompt_hash: str | None
    tokens_in: int | None
    tokens_out: int | None
    cost_usd: float | None
    is_mock: bool
    ts: datetime
```

Composite indexes: `(session_id, agent, ts DESC)` for chat-per-agent views; `(session_id, stage, ts ASC)` for chat-per-stage views.

Storage backend gains two async methods: `append_agent_turn(turn)` and `list_agent_turns(session_id, *, agent=None, stage=None, after_ts=None, limit=200)`.

**`PipelineState.agent_memory`** is a dict keyed by agent name. `resolve_agent(name, state)` in `stages/_helpers.py` hydrates the agent's `working_memory` and `notes` from it; stage `on_exit` hooks write back. A `dirty` flag on the agent avoids no-op writes.

**Mock tag propagation:** `BaseLLMProvider` gains `is_mock: bool = False`. `MockLLMProvider` sets `True`. The tracing wrapper reads it and sets `is_mock` on every emitted event and `agent_turns` row.

### 3.2 Event plane

Two emission points correlated via `turn_id` in a `contextvars.ContextVar`:

1. **Agent-level boundary** — `ConfigAgent.inference()` creates a `turn_id`, stores a `TurnContext` in the ContextVar, emits `agent_turn_started` (with `system_prompt_hash`, `assembled_context_keys`, `memory_scope_applied`, `is_mock`), runs the body, emits `agent_turn_completed` with aggregated tokens/cost. `PIAgent.decide()` emits `pi_decision` at return. Hypothesis updates in `results_interpretation` emit `hypothesis_update`.

2. **Provider boundary** — `TracedLLMProvider` and `TracedTool` wrappers read the current `TurnContext` from the ContextVar and emit `agent_llm_request/response` and `agent_tool_call/result` around the underlying call. Same code path for every agent; no agent-level call-site changes beyond `inference()`.

ContextVar avoids threading `turn_id` through every function signature and is asyncio-safe (one task = one context).

Every emitted event also writes an `agent_turns` row. WS stream and REST history endpoint read the same table — single source of truth.

### 3.3 Endpoints

Thin wrappers — the data is already in state or `agent_turns`:

- `GET /graph` — graph topology mapper (see 3.4)
- `GET /agents` — list keys of `state["agent_memory"]` merged with registry metadata (role, memory_scope)
- `GET /agents/{name}/context` — run `ContextAssembler.assemble(state, name)`, return `{keys, preview, scope}`
- `GET /agents/{name}/history` — `list_agent_turns(session_id, agent=name)` paginated
- `GET /agents/{name}/memory` — `state["agent_memory"][name]`
- `GET /pi/history` — `state["pi_decisions"]`
- `GET /requests` — `{pending: state["pending_requests"], completed: state["completed_requests"]}`
- `GET /experiments` — `{runs: [{...ExperimentResult, stdout, stderr, exit_code, wall_time, refs, linked_hypothesis_id}], log: state["experiment_log"]}`

### 3.4 Graph topology mapper

`/api/sessions/{id}/graph` returns the owned shape:

```
{
  nodes: [{id, type: "stage"|"transition"|"subgraph", label, zone, status, iteration_count, skipped}],
  edges: [{from, to, kind: "sequential"|"backtrack"|"conditional", reason?}],
  cursor: {node_id, agent?, started_at} | null,
  subgraphs: [{id: "lab_meeting", nodes: [...], edges: [...]}]
}
```

Implementation:
1. Walk `graph.get_graph()` for base nodes/edges
2. Overlay runtime annotations from state: `completed_stages`, `current_stage`, `stage_iterations`, `skip_stages` from config
3. Extract subgraphs via `graph.get_graph(xray=1)` — preserved nested rather than flattened
4. Compute `cursor` from the most recent `stage_started` or `agent_turn_started` event

### 3.5 Experiment log

`experiment_log` is appended by `ExperimentationStage` after each run:
- `outcome` inferred from exit_code (non-zero → failure) and linked hypothesis check (no metric improvement → inconclusive)
- `failure_reason` extracted from stderr last-line heuristic + LLM summarization when available
- `learnings` populated during `results_interpretation` stage when it reviews this attempt

Plan 6 does not inject the log into downstream agent contexts (that is Plan 7). The UI renders it so humans can see "we've tried approach X three times, all failed for different reasons" even if the agents themselves aren't yet reading it.

---

## 4. Frontend design

### 4.1 Layout (stacked canvas + tabs)

```
┌──────────────────────────────────────────────────────────┐
│ Header: topic · session_id · status                      │
├──────────────────────────────────────────────────────────┤
│  GraphTopology (always on, resizable ~320px)            │
│  rich stage nodes: status · iter · agent · control · $  │
├─────────┬────────────────────────────────┬──────────────┤
│ Left    │ Tabs:                          │ Right sider   │
│ (slim)  │ • Conversations (default)      │ Agent Monitor │
│ Pause   │ • Artifacts                    │ Hypotheses    │
│ Resume  │ • Experiments                  │ PI Decisions  │
│ Cancel  │ • Cost                         │ Cost (compact)│
├─────────┴────────────────────────────────┴──────────────┤
│ FeedbackInput (sticky bottom)                           │
└──────────────────────────────────────────────────────────┘
```

### 4.2 New and revised components

```
web/src/components/session/
  GraphTopology.tsx          # replaces PipelineGraph.tsx; @xyflow/react + elkjs auto-layout
  StageNode.tsx              # rich node: status, iter, agent, control dropdown, cost, kebab
  ChatView.tsx               # center "Conversations" tab; mode="clean" (lab_scene reserved)
  StageGroup.tsx             # collapsible stage section within ChatView
  AgentTurn.tsx              # one turn card; folded system_prompt, inline tool calls by parent_turn_id
  ToolCallInline.tsx         # collapsible call+result pair
  AgentMonitor.tsx           # right sider top; per-agent tabs; auto-focus with pin
  AgentScopeCard.tsx         # read/summarize/write keys
  AgentContextPreview.tsx    # what was assembled for the latest turn
  AgentMemoryCard.tsx        # working_memory + notes
  AgentHistoryCard.tsx       # paginated turn list filtered to this agent
  PIDecisionLog.tsx          # last N PI decisions with confidence chips
  ExperimentsTab.tsx         # experiment run cards + prior-attempts ribbon
  ExperimentDetail.tsx       # one run: script, stdout, stderr, repro, refs, linked hypothesis
  ExperimentDiffView.tsx     # side-by-side run compare
```

### 4.3 Stage node design

Each `StageNode` card shows: status dot (idle/active/complete/failed/skipped), elapsed time when active, `iter N/M`, current or last-active agent name, per-stage control radio (`auto`/`notify`/`approve`/`edit`) feeding `/api/sessions/{id}/preferences`, running cost, kebab menu (`redirect here`, `jump to artifacts`). Skipped stages render at 0.4 opacity. Lab meeting compounds to a single subgraph node with a "drill-in" action that swaps the canvas to the subgraph view.

### 4.4 Data hooks

```
useGraph(sessionId)
useAgents(sessionId)
useAgentContext(sessionId, agentName)
useAgentHistory(sessionId, agentName, cursor)
useAgentMemory(sessionId, agentName)
usePIHistory(sessionId)
useCrossStageRequests(sessionId)
useExperiments(sessionId)
```

All TanStack Query. WS event handler invalidates matching keys on relevant events: e.g., `agent_turn_completed` → invalidate `useAgentHistory(agent)` + `useAgentContext(agent)` + `useAgentMemory(agent)`; `pi_decision` → `usePIHistory`; `stage_started`/`stage_completed` → `useGraph`.

### 4.5 Dropped / replaced

- `PipelineGraph.tsx` (hardcoded 8-node diagram) — replaced by `GraphTopology`
- `StageOutputPanel compact` in right sider — was a duplicate of the main-area Artifacts tab
- Per-stage controls inside `ControlBar` — move to graph nodes; `ControlBar` keeps only global actions
- `PipelineTracker` in left sider — graph IS the tracker
- "Graph" and "Activity" tabs — graph is now always-on, Activity is replaced by Conversations

### 4.6 Conversation UI — `mode` prop reserved

`ChatView` accepts `mode: "clean" | "lab_scene"`. Plan 6 ships `clean` only. The `lab_scene` renderer (pixel-art avatars, dialogue bubbles) is reserved for a future creative-polish plan and lives outside this spec.

---

## 5. Research-realism additions beyond pure observability

### 5.1 Cloned reference rendering (Experiments tab)

`ExecutionResult` already captures `git_ref` in its `ReproducibilityRecord`. Plan 6 surfaces `refs: list[{repo_url, commit, path}]` on each experiment card so humans can see "this run referenced repo X at commit Y." Low implementation cost, closes the reproducibility loop.

### 5.2 Experiment log scaffolding

Plan 6 structures the cross-agent failure memory (state key, append logic, API, UI) so humans can see "we've tried this three times and failed" during a session. Plan 6 does **not** modify agent context assembly — agents don't yet read the log.

Plan 7 (separate future brainstorm) will:
- Inject log summaries into ML engineer / postdoc / PI agent context before a new experiment
- Add fuzzy similarity checking ("this proposal looks like attempt #3 which failed — proceed anyway?")
- Decide read/write scope per agent for the log

Scoping the behavior change into a separate plan keeps Plan 6 bounded; the UI surfaces the data now, which is already valuable for human observation.

---

## 6. Testing strategy

### 6.1 Backend

- **Event emission** — patch event bus, call `ConfigAgent.inference()` with mock provider, assert `agent_turn_started` → `agent_llm_request` → `agent_llm_response` → `agent_turn_completed` with correlated `turn_id`.
- **Agent memory round-trip** — set `working_memory` on an agent in stage 1, run `on_exit`, re-resolve in stage 2, assert memory survives.
- **agent_turns** — append, filter by agent, filter by stage, paginate with `after_ts`.
- **Graph topology mapper** — given mock compiled graph + state with `skip_stages`, assert skipped nodes marked, cursor on `current_stage`, lab_meeting preserved as subgraph.
- **End-to-end mock-LLM** — run `test_full_pipeline` with `MockLLMProvider`, assert the event stream for one stage contains exactly the expected turn sequence. This is the audit's "watch the stream and validate" turned into a regression test.
- **Endpoints** — each new endpoint: happy path, missing session (404), empty state.

### 6.2 Frontend

- **ChatView** — given a turn fixture, renders grouped stages; tool calls render inline at correct parent_turn_id.
- **AgentMonitor** — tab switch preserves scroll; auto-focus follows latest `agent_turn_started` unless pinned.
- **GraphTopology** — given owned-shape fixture, renders N nodes with correct status classes; skipped nodes at 0.4 opacity; clicking a node opens the stage drawer.
- **ExperimentsTab** — two fixtures in `ExperimentDiffView` render side-by-side stdout delta.
- **WS → cache invalidation** — mock WS sends `agent_turn_completed`, assert `useAgentHistory` refetches.

No streaming tests (payload level B, no chunking).

---

## 7. Out of scope for Plan 6 (explicit)

- `lab_scene` conversation renderer — hook prop exists, no implementation
- Token streaming (`agent_llm_chunk`) — payload level B only
- Human-editable agent memory (write endpoint on `/agents/{name}/memory`)
- PostgreSQL migration for `agent_turns` — SQLite only; Alembic migration works for both but Postgres path untested
- Multi-user observability — all endpoints remain `(user_id="default", session_id)`-scoped
- Retention / GC of `agent_turns` — append-only, no cleanup in Plan 6
- Redaction / PII scrubbing of LLM payloads
- Agent-behavior integration of `experiment_log` (→ Plan 7)
- Human-initiated "add literature request" affordance (emission side; viewing side is in)

---

## 8. Delivery phases

Single implementation plan, three phases with natural checkpoints.

**Phase A — Data plane.** `agent_turns` SQLAlchemy table + Alembic migration, storage backend append/list methods, `PipelineState.agent_memory`/`experiment_log`/`pi_decisions` keys, memory round-trip through `resolve_agent` + `on_exit`, `is_mock` propagation on providers. Passes backend tests. No UI changes.

**Phase B — Event plane + endpoints.** `contextvars` `TurnContext`, `TracedLLMProvider` + `TracedTool` wrappers, emission in `ConfigAgent.inference` + `PIAgent.decide` + `ExperimentationStage` + `results_interpretation`, all 8 new REST endpoints, graph topology mapper, mock-LLM end-to-end test. At this checkpoint the backend is fully observable via curl + websocat.

**Phase C — UI.** New stacked layout, `GraphTopology` + `StageNode`, `ChatView` + `AgentTurn` + `ToolCallInline`, `AgentMonitor` + subcards, `ExperimentsTab` + `ExperimentDiffView`, `PIDecisionLog`, hook layer, WS invalidation wiring. Drop `PipelineGraph.tsx`, compact duplicates, and old Graph/Activity tabs.

Each phase lands as its own commit(s) / PR(s). Backend phases (A, B) are demo-able without frontend work; Phase C has the full `--mock-llm` validation demo.

---

## 9. Open questions / future work

- **Plan 7:** agent-behavior integration of `experiment_log` — context injection, fuzzy-similarity warnings, read/write scope per agent
- **Plan 8 (tentative):** `lab_scene` creative conversation renderer — art style, avatar mapping per agent role, thinking animations
- Token streaming for chunked LLM output
- Human-editable agent memory (write endpoint + UI editor)
- Postgres `agent_turns` validation
- `agent_turns` retention policy
- Payload redaction / PII scrubbing
