# AgentLabX Platform Design Spec

**Date:** 2026-04-12
**Status:** Draft
**Scope:** Full rewrite of `third_party/AgentLaboratory` into a modular, multi-instance research platform

---

## 1. Overview

AgentLabX is a modular, multi-instance research automation platform that orchestrates LLM-powered agents through an end-to-end scientific research workflow. It rewrites the monolithic AgentLaboratory (~4,000 lines across 9 files) into a plugin-based architecture designed for extensibility, session isolation, and real-world research simulation.

### Goals

- **Modular plugin architecture** — every stage, agent, tool, and backend is a swappable plugin
- **Research-realistic simulation** — agents have differentiated memory, autonomy within their scope, lab meetings when stuck, and code reuse from external sources
- **Multi-instance capable** — session isolation from day one, multi-user ready with zero schema changes when auth is added
- **Configurable over hardcoded** — Pydantic settings, YAML configs, env vars, per-session overrides
- **Service-deployable** — runs locally with one command, scales to Docker Compose or Kubernetes

### Non-Goals (MVP)

- User authentication and RBAC (architecture supports it, not implemented)
- Kubernetes execution backend (Docker and subprocess only)
- Production horizontal scaling (single-process uvicorn is sufficient)
- Mobile or native desktop UI

---

## 2. Architecture

### 2.1 Modular Monolith with Plugin Architecture

Single deployable application with internal module boundaries enforced by a plugin registry system. Runs as one process but all components are swappable.

**Three layers:**

1. **Web Layer** — React + Vite frontend bundled with FastAPI server. REST + WebSocket APIs with OpenAPI docs.
2. **Core Engine** — LangGraph pipeline, plugin registry, session manager, agent framework, config system.
3. **Plugin Layer** — stage plugins, provider plugins (LLM, execution, storage, code agent), tool plugins.

### 2.2 Project Structure

```
agentlabx/
  core/
    registry.py          # Plugin registry — discover, register, resolve
    pipeline.py          # LangGraph StateGraph builder + runner
    session.py           # Session lifecycle, isolation, state
    config.py            # Pydantic settings, YAML loader, env merge
    state.py             # Typed pipeline state (LangGraph TypedDict)
    events.py            # Event bus for plugin communication
  stages/
    base.py              # BaseStage ABC — run(), validate(), on_enter(), on_exit()
    literature_review.py
    plan_formulation.py
    data_exploration.py  # EDA, data quality analysis — can trigger plan revision
    data_preparation.py  # Cleaning, feature engineering, pipeline code
    experimentation.py   # Baselines → main experiments → ablations (enforced)
    results_interpretation.py
    report_writing.py
    peer_review.py
    lab_meeting.py       # Special subgraph — cross-zone collaboration
  agents/
    base.py              # BaseAgent ABC — inference(), get_context(), tools
    config_agent.py      # Generic agent instantiated from YAML config
    configs/
      phd_student.yaml
      postdoc.yaml
      ml_engineer.yaml
      sw_engineer.yaml
      professor.yaml
      reviewers.yaml
      pi_agent.yaml      # Transition handler agent
  providers/
    llm/
      base.py            # BaseLLMProvider ABC
      litellm_provider.py
    execution/
      base.py            # BaseExecutionBackend ABC
      subprocess_backend.py
      docker_backend.py
    storage/
      base.py            # BaseStorageBackend ABC
      sqlite_backend.py
      postgres_backend.py
    code_agent/
      base.py            # BaseCodeAgent ABC — generate(), edit(), debug()
      claude_code_agent.py
      builtin_agent.py   # Fallback: direct LLM code generation
  tools/
    base.py              # BaseTool ABC — execute(), validate_config(), get_schema()
    arxiv_search.py
    hf_dataset_search.py
    semantic_scholar.py
    code_executor.py
    latex_compiler.py
    github_search.py     # Search + clone repos
    session_artifact_search.py  # Cross-session code reuse
  server/
    app.py               # FastAPI application factory
    routes/              # API routes (sessions, pipeline, agents, plugins, artifacts)
    ws/                  # WebSocket handlers (streaming, events)
    deps.py              # Dependency injection
  web/                   # React + Vite (separate build, bundled in dist)
    src/
    package.json
    vite.config.ts
config/                  # Default YAML configs
tests/                   # Mirrors source structure
pyproject.toml           # Single package, optional extras
docker-compose.yml       # Dev + production profiles
```

### 2.3 Plugin System

Three discovery mechanisms:

**Built-in plugins** — decorator-based registration, auto-registered at startup.
```python
@register_stage("literature_review")
class LiteratureReview(BaseStage):
    ...
```

**Config-based plugins** — drop a YAML file in the config directory. No Python needed.
```yaml
# agents/configs/custom_chemist.yaml
name: chemist
role: "Chemistry domain expert"
system_prompt: "You are..."
tools: [pubchem_search, rdkit]
phases: [lit_review, experiment]
```

**Entry point plugins** — third-party packages register via Python entry points, auto-discovered on install.
```toml
# In third-party pyproject.toml
[project.entry-points."agentlabx.tools"]
pubmed = "agentlabx_pubmed:PubMedTool"
```

### 2.4 Base Class Contracts

**BaseStage:**
```python
class BaseStage(ABC):
    name: str
    description: str
    required_agents: list[str]
    required_tools: list[str]

    @abstractmethod
    async def run(self, state: PipelineState, context: StageContext) -> PipelineState: ...
    def validate(self, state: PipelineState) -> bool: ...
    def on_enter(self, state: PipelineState) -> PipelineState: ...
    def on_exit(self, state: PipelineState) -> PipelineState: ...
```

**BaseTool:**
```python
class BaseTool(ABC):
    name: str
    description: str
    config_schema: type[BaseModel]

    @abstractmethod
    async def execute(self, **kwargs) -> ToolResult: ...
    def validate_config(self) -> bool: ...
    def get_schema(self) -> dict: ...  # For LLM tool calling
```

**BaseAgent:**
```python
class BaseAgent(ABC):
    name: str
    role: str
    system_prompt: str
    tools: list[BaseTool]
    memory_scope: MemoryScope

    @abstractmethod
    async def inference(self, prompt: str, context: AgentContext) -> str: ...
    def get_context(self, phase: str) -> str: ...
    def reset(self) -> None: ...
```

**BaseCodeAgent:**
```python
class BaseCodeAgent(ABC):
    name: str
    supports_streaming: bool

    @abstractmethod
    async def generate(self, task: str, context: CodeContext, workspace: Path) -> CodeResult: ...
    @abstractmethod
    async def edit(self, instruction: str, files: list[Path], context: CodeContext) -> CodeResult: ...
    @abstractmethod
    async def debug(self, error: str, files: list[Path], execution_log: str) -> CodeResult: ...
```

---

## 3. Pipeline Design

### 3.1 Non-Linear Research Graph

The pipeline is NOT a linear production line. It models how real research labs work: agents have autonomy, collaborate directly with peers, and iterate freely within their scope.

**Zone-based collaboration:**

- **Discovery Zone** (Literature Review + Plan Formulation) — PhD student and postdoc explore the problem space
- **Implementation Zone** (Data Exploration + Data Preparation + Experimentation) — engineers analyze data, build, and iterate
- **Synthesis Zone** (Interpretation + Report Writing + Peer Review) — team synthesizes results

**Cross-cutting capabilities:** Literature search is both a stage (dedicated deep dive in Discovery) AND a tool available to all agents in all stages. Any agent can invoke `arxiv_search` or `semantic_scholar` mid-workflow — discovering a critical baseline paper during experimentation or a missing citation during report writing is normal research behavior.

**Transition rules:**

| Transition Type | Behavior |
|---|---|
| Within a zone | Agents move freely — self-loop, iterate, peer handoff. No approval needed. |
| Forward between zones | Automatic on stage completion |
| Backward across zones | Auto mode: PI agent decides. HITL mode: human approves. Always logged. |
| Targeted requests | Any stage can emit `experiment_requests` or `literature_requests` to other stages without a full backtrack (e.g., report writing says "we need one more ablation study" → feeds to experimentation as a targeted task). |

### 3.2 Stage Architecture

Each stage is a LangGraph subgraph with internal autonomy:

```
ENTER → Agent(s) work (tools, LLM calls, dialogue) → Evaluate → Decide → EXIT
         ↻ self-loop: iterate within stage (agent decides)
```

Stage exit returns a `StageResult`:
```python
class StageResult:
    output: Any           # Stage output data
    status: Literal["done", "backtrack", "negative_result", "request"]
    next_hint: str | None # Suggested next stage
    reason: str           # Why this decision
    feedback: str | None  # Context for target stage
    requests: list[CrossStageRequest] | None  # Targeted requests to other stages
```

**Status semantics:**
- `done` — stage completed successfully, advance
- `backtrack` — stage needs an earlier stage re-run with feedback
- `negative_result` — experiment conclusively showed no significant improvement. This is a valid research outcome, not a failure. The PI agent decides: publish the negative finding, pivot the hypothesis, or try a different approach.
- `request` — stage completed but needs targeted work from another stage (e.g., report writing needs one more ablation study from experimentation). Not a full backtrack — the requesting stage pauses and resumes when the request is fulfilled.

### 3.3 PI Agent — Intelligent Transition Handler

The PI agent replaces a dumb rule engine. It is an LLM-powered research director with its own memory scope (high-level summaries, transition history, budget status — NOT implementation details).

When a stage exits, the PI agent evaluates: "Given the research goals, what we've done so far, what just happened, and the budget remaining — what should the lab do next?"

**PI agent can decide to:**
- Advance to next stage (normal flow)
- Send back to a specific stage with targeted feedback
- Request additional iteration within current stage
- Accept a negative result as a valid finding worth reporting
- Pivot the active hypothesis based on accumulated evidence
- Recommend completion
- Flag for human review (uncertain decision)

**PI agent resilience:** The PI agent includes a confidence score with each decision. If confidence is below a configurable threshold, the system falls back to the default sequence rather than acting on a low-confidence routing decision. PI decision accuracy is tracked over the session (did backtracks actually improve outcomes? did "advance" decisions lead to successful completions?) for observability and future tuning.

**Override priority:** human override > hard limits (iteration caps, cost ceiling) > PI agent judgment (if confident) > default sequence fallback (if PI uncertain) > stage self-assessment.

In HITL mode, the PI agent still makes a recommendation, but the human has final say. Switching modes doesn't change the architecture.

### 3.4 Pipeline State

```python
class PipelineState(TypedDict):
    # Identity
    session_id: str
    user_id: str
    research_topic: str

    # Hypothesis tracking — the scientific backbone of the session
    hypotheses: list[Hypothesis]  # See §3.5

    # Stage outputs (versioned — each re-run appends, not overwrites)
    literature_review: list[LitReviewResult]
    plan: list[ResearchPlan]
    data_exploration: list[EDAResult]       # EDA findings, data quality reports
    dataset_code: list[str]
    experiment_results: list[ExperimentResult]  # See §3.6 for required fields
    interpretation: list[str]
    report: list[ReportResult]
    review: list[ReviewResult]

    # Cross-stage requests (targeted, not full backtracks)
    pending_requests: list[CrossStageRequest]
    completed_requests: list[CrossStageRequest]

    # Pipeline control
    current_stage: str
    stage_config: dict  # Per-stage overrides

    # Routing
    next_stage: str | None
    human_override: str | None
    default_sequence: list[str]
    completed_stages: list[str]

    # Iteration tracking
    stage_iterations: dict[str, int]
    total_iterations: int
    max_stage_iterations: dict[str, int]
    max_total_iterations: int

    # History
    transition_log: list[Transition]
    review_feedback: list[ReviewFeedback]
    messages: list[AgentMessage]
    cost_tracker: CostTracker
    errors: list[StageError]
```

Stage outputs are **versioned** — when a stage runs multiple times, results append to a list. The latest entry is the "active" version used by downstream stages. Previous versions remain for comparison.

### 3.5 Hypothesis Tracking

Real research is hypothesis-driven. The pipeline explicitly tracks hypotheses as first-class state:

```python
class Hypothesis:
    id: str
    statement: str                              # "Chain-of-thought with 5-shot examples will improve MATH accuracy by >5%"
    status: Literal["active", "supported", "refuted", "abandoned"]
    evidence_for: list[EvidenceLink]            # Links to experiment results supporting this
    evidence_against: list[EvidenceLink]        # Links to experiment results contradicting this
    parent_hypothesis: str | None               # If this was derived from pivoting another
    created_at_stage: str                       # Which stage proposed it
    resolved_at_stage: str | None               # Which stage resolved it

class EvidenceLink:
    experiment_result_index: int                # Points to experiment_results[i]
    metric: str                                 # "accuracy", "f1", etc.
    value: float
    interpretation: str                         # "Accuracy improved by 4.8%, supporting H1"
```

The PI agent uses hypothesis status as structured input for routing decisions: "H1 is refuted — should we abandon this line entirely, or is there a variant worth testing?" This is far more rigorous than reading summaries.

Plan formulation proposes initial hypotheses. Experimentation links results to hypotheses. Interpretation updates hypothesis status. The PI agent tracks which hypotheses are active when making transition decisions.

### 3.6 Experimentation — Internal Structure

The experimentation stage has required internal phases that enforce scientific rigor:

1. **Baselines** — establish what "no improvement" looks like. The stage cannot exit `done` without at least one baseline result. Baselines are linked to the null hypothesis.
2. **Main experiments** — test the active hypotheses against the baselines.
3. **Ablation studies** — systematically remove/modify components to understand what actually contributes to improvements. Required before the stage can exit `done` if main experiments show positive results.

This is enforced via stage validation: `ExperimentationStage.validate()` checks that `experiment_results` contains at least one entry tagged as `baseline` and, if positive results exist, at least one tagged as `ablation`.

### 3.7 Reproducibility

Every `ExperimentResult` automatically captures reproducibility metadata:

```python
class ExperimentResult:
    # ... output fields ...
    reproducibility: ReproducibilityRecord

class ReproducibilityRecord:
    random_seed: int                    # Exact seed used
    environment_hash: str               # Hash of Python environment (pip freeze)
    run_command: str                     # Exact command that produced this result
    container_image: str | None          # Docker image tag if containerized
    git_ref: str | None                  # Commit hash of referenced code
    dependencies_snapshot: dict          # Frozen dependency versions
    timestamp: datetime
```

The execution backend captures these automatically — the researcher doesn't need to think about it. Results are reproducible by re-running `run_command` with the same `random_seed` in an environment matching `environment_hash`.

### 3.8 Two Execution Modes

**Full Automatic:** Agents run autonomously. Each stage decides when it's done and what comes next. Safety nets: per-stage iteration limits, global cost ceiling, cycle detection, full transition log.

**Human-in-the-Loop:** Pipeline pauses at configurable checkpoints. Per-stage control levels:

| Level | Behavior |
|---|---|
| `auto` | No pause, run freely |
| `notify` | Notify human, don't wait |
| `approve` | Pause and wait for approval |
| `edit` | Pause, human can edit stage output |

Users can switch between auto and HITL **at any time during execution** and toggle per-stage review preferences live. Changes take effect at the next stage transition. Backtrack transitions can have their own approval setting independent of forward transitions.

---

## 4. Agent Memory & Knowledge

### 4.1 Differentiated Memory Scopes

Each agent sees the project through a different lens, configured via YAML:

```yaml
# Example: ml_engineer agent config
memory_scope:
  read:             # What this agent can see
    - plan.methodology
    - experiment_code.*
    - execution_logs.*
    - dataset.schema
    - dataset.samples
  write:            # What this agent produces
    - experiment_code
    - experiment_results
  summarize:        # Gets summary, not full content
    literature_review: abstract   # LLM-generated abstract of full review
    plan: goals_only              # Extract goals section only
```

**Agent memory scopes:**

Scopes use `read` (full access), `summarize` (abstracted view), and no entry (no access). The goal is differentiated depth, NOT silos. Real research teams share context — the difference is how much detail each role needs.

| Agent | Full access | Summarized access | No access |
|---|---|---|---|
| **PI Agent** | Transition history, budget, review feedback, hypothesis status, past decisions | All stage outputs (summary level) | Implementation code, raw data, individual agent conversations |
| **Professor** | Full lit review, report drafts, review feedback | Experiment results (metrics + interpretation), plan (methodology) | Raw code, debug logs, data preprocessing steps |
| **Postdoc** | Full plan (owns it), experiment design, results with analysis, lit review | Implementation code (approach summary) | Infrastructure config, debug logs |
| **PhD Student** | Full paper texts, detailed notes, plan details, experiment results, professor guidance | Implementation code (approach + results) | Infrastructure/DevOps, other sessions |
| **ML Engineer** | Plan methodology, full experiment code (owns it), execution logs, dataset schema | Literature review (abstracts + key findings), report (results section) | Full paper texts, report writing drafts, professor-student conversations |
| **SW Engineer** | Data requirements, dataset code (owns it), data validation, ML engineer data requests | Plan (data requirements), experiment methodology (what data shape is needed) | Full literature, report drafts, review commentary |
| **Reviewers** | Final report ONLY | Nothing | All internal state, transition history, agent conversations, failed attempts |

**Note on Reviewers:** The reviewer agents intentionally have the most restricted scope. They see only the final report — no access to transition history, agent messages, or failed attempts. This simulates real blind peer review where reviewers come in cold and judge the paper on its own merits. Optionally, a different LLM provider can be configured for review to reduce model-level bias.

### 4.2 Context Assembly Pipeline

When an agent runs, context is assembled by:

1. **Filter** — include only state keys matching `memory_scope.read`
2. **Summarize** — for `summarize` scopes, produce the right abstraction level (LLM or extractive summarization)
3. **Sliding window** — agent's own conversation history (configurable length per agent)
4. **Working memory** — agent's scratchpad notes from previous iterations
5. **Token budget** — if assembled context exceeds agent's budget, prioritize by recency and relevance

### 4.3 Working Memory

Each agent maintains a personal scratchpad, persisted with session checkpoints:

- **Notes** — key findings, decisions, hypotheses to remember across iterations
- **Conversation history** — sliding window (length varies: professor=short, PhD=long)
- **Peer messages** — direct messages from collaborating agents (e.g., professor guidance to student)

---

## 5. Lab Meetings

When a stage is stuck, the system can trigger a lab meeting — a special cross-zone collaboration subgraph.

### 5.1 Triggers (configurable)

- Consecutive failures (default: 3)
- Score plateau over N rounds (default: 2)
- Agent explicitly flags "I'm stuck"
- Scheduled periodic checkpoints
- Human requests meeting via UI/API

**Budget triggers are separate from stuck triggers.** A budget warning (e.g., 70% spent) does NOT trigger a lab meeting — meetings burn more budget. Instead, budget warnings shift the PI agent's decision bias toward wrapping up: prefer completing over iterating, prefer publishing negative results over exploring more hypotheses, prefer advancing to synthesis over running more experiments. This is configured via `budget_policy`, not `lab_meeting.triggers`.

### 5.2 Meeting Flow

1. **Problem Presentation** — stuck agent presents what they tried, what failed, and blockers (using their own memory scope)
2. **Multi-Agent Discussion** — other agents contribute from their perspective: professor suggests high-level pivots, postdoc connects to literature, ML engineer proposes implementation alternatives
3. **Action Items** — PI agent synthesizes discussion into concrete next steps (retry with new approach, backtrack to earlier stage, or pivot research direction)
4. **Memory Update** — meeting summary distributed to each agent's working memory, filtered by their scope

### 5.3 Configuration

```yaml
lab_meeting:
  enabled: true
  triggers:
    consecutive_failures: 3
    score_plateau_rounds: 2
    scheduled_interval: null  # or every N iterations
  participants: auto  # or explicit agent list
  max_discussion_rounds: 5

# Separate from lab meetings — budget influences PI decision bias, not meetings
budget_policy:
  warning_threshold: 0.7       # At 70% spent, PI biases toward wrapping up
  critical_threshold: 0.9      # At 90% spent, PI must advance or complete
  hard_ceiling: 1.0            # Pipeline stops
```

---

## 6. Code Reuse & External Code Agents

### 6.1 Code Reuse — Three Sources

**GitHub Code Search** (tool plugin): Agents search GitHub for relevant implementations, clone repos as reference. Configurable: max repos, token auth.

**Session Artifact Search** (tool plugin): Search and import code from previous sessions within the same user workspace. "Elder student's code" pattern.

**Reference Workspace** per session:
```
session_workspace/
  refs/           # Cloned repos (read-only)
  imported/       # From past sessions (read-only)
  experiment/     # Current work (read-write)
```

### 6.2 External Code Agent Integration

AgentLabX agents are research thinkers, not code generators. Actual coding is delegated to external code agents through a `BaseCodeAgent` interface.

**Separation of concerns:**
- **ML Engineer agent (ours):** decides WHAT to implement, evaluates results, iterates strategy
- **Code agent (external):** decides HOW to implement, writes code, handles debugging

**Shipped adapters:**
- `ClaudeCodeAgent` — invokes Claude Code SDK
- `BuiltinAgent` — fallback: direct LLM code generation (for environments without external agents)

**Additional adapters can be added** for Aider, Codex CLI, or any other code agent via the plugin system.

**Configuration:**
```yaml
code_agent:
  backend: claude_code  # or aider, codex, built_in
  model: claude-sonnet-4-6
  allowed_tools: [read, write, bash]
  workspace_isolation: true
  max_turns: 20
```

---

## 7. API Layer

### 7.1 REST API

| Method | Endpoint | Purpose |
|---|---|---|
| GET | `/api/sessions` | List sessions |
| POST | `/api/sessions` | Create session (with config overrides) |
| GET | `/api/sessions/{id}` | Session detail + state |
| POST | `/api/sessions/{id}/start` | Start pipeline |
| POST | `/api/sessions/{id}/pause` | Pause at next checkpoint |
| POST | `/api/sessions/{id}/resume` | Resume from checkpoint |
| POST | `/api/sessions/{id}/redirect` | Human override → target stage |
| PATCH | `/api/sessions/{id}/preferences` | Live mode toggle + per-stage controls |
| GET | `/api/sessions/{id}/artifacts` | Papers, code, data |
| GET | `/api/sessions/{id}/transitions` | Pipeline transition history |
| GET | `/api/sessions/{id}/cost` | Token usage and cost |
| GET | `/api/sessions/{id}/hypotheses` | Hypothesis status and evidence |
| GET | `/api/plugins` | Available stages, tools, agents |

### 7.2 WebSocket

Endpoint: `ws://host:port/ws/sessions/{id}`

**Server → Client events:**
- `stage_started` — which stage, which agents
- `agent_thinking` — streaming LLM output (token by token)
- `agent_tool_call` — tool invocation + result
- `agent_dialogue` — inter-agent messages
- `stage_completed` — output summary
- `transition` — PI decision + reasoning
- `checkpoint_reached` — awaiting human input (with options: approve, edit, redirect)
- `cost_update` — token usage delta
- `error` — stage failure + recovery action

**Client → Server actions:**
- `approve` — approve checkpoint
- `edit` — modify stage output
- `redirect` — override next stage
- `inject_feedback` — send note to agents mid-stage
- `update_preferences` — live mode toggle

---

## 8. Frontend

### 8.1 Tech Stack

- **React 19** + TypeScript + Vite
- **Ant Design 5** — component library (Layout, Table, Modal, Form, Steps, Tree, etc.)
- **@ant-design/plots** — charts and cost visualization
- **React Flow** — pipeline graph visualization
- **Zustand** — state management
- **TanStack Query** — REST data fetching + caching
- **openapi-typescript** — auto-generated typed API client from FastAPI's OpenAPI schema

### 8.2 Pages

- **Session List (Dashboard)** — all sessions with status (running/paused/completed), current stage, iteration count, cost
- **Session Create** — config wizard: research topic, LLM model, pipeline config, agent selection, stage controls
- **Session Detail** — main workspace:
  - Left sidebar: pipeline progress tracker (shows backtracks like "Plan ×2"), controls (pause/stop), mode toggle (auto/HITL)
  - Center: agent activity feed with streaming output, tool calls, execution results, inter-agent dialogue
  - Right panel: current stage output summary, PI agent assessment, budget tracker
  - Bottom: human feedback input for sending notes to agents or redirecting
- **Plugin Browser** — available stages, tools, agents with descriptions and config schemas
- **Settings** — global config: default LLM, API keys, execution backend, storage backend

### 8.3 Key Components

- `PipelineGraph` — React Flow visualization of the transition graph (nodes = stages, edges = transitions with reasons)
- `AgentActivityFeed` — real-time streaming log of agent actions via WebSocket
- `StageOutputPanel` — versioned results viewer (compare iteration N vs N-1)
- `ControlBar` — mode toggle, pause/resume, per-stage review preference toggles
- `CostTracker` — @ant-design/plots budget visualization
- `CheckpointModal` — HITL approval dialog with PI recommendation
- `FeedbackInput` — human → agent messaging
- `HypothesisTracker` — visual status of all hypotheses (active/supported/refuted/abandoned) with linked evidence

---

## 9. Session Management

### 9.1 Session Isolation

Every session is scoped to `(user_id, session_id)` from day one. MVP uses `user_id = "default"`.

- Artifacts namespaced as `storage/{user_id}/{session_id}/`
- Each session gets its own LLM context, execution container, artifacts, and LangGraph checkpoint
- Sessions are independent — no shared mutable state

### 9.2 Session Lifecycle

```
Create → Run → Pause → Resume → Complete → Archive
```

- **Create:** allocate session ID, namespace storage, initialize pipeline state
- **Run:** execute LangGraph, stream events via WebSocket
- **Pause:** checkpoint state at next stage boundary, persist to storage
- **Resume:** load checkpoint, continue from last completed node
- **Complete:** finalize artifacts, cleanup execution containers
- **Archive:** compress artifacts, move to cold storage (future)

### 9.3 Database Schema

```sql
users(id, name, settings_json)
sessions(id, user_id, topic, status, pipeline_config, created_at, updated_at)
checkpoints(id, session_id, stage, state_blob, created_at)
artifacts(id, session_id, type, path, metadata_json)
```

**Multi-user upgrade path:** add auth middleware (OAuth/JWT) → populate `user_id` from token instead of "default" → add RBAC if needed. Zero schema changes.

---

## 10. Configuration

### 10.1 Configuration Hierarchy (highest priority first)

1. Environment variables (`AGENTLABX_*`)
2. User config file (`~/.agentlabx/config.yaml`)
3. Project config file (`./config/default.yaml`)
4. Pydantic defaults in code

### 10.2 Per-Session Overrides

Sessions can override any default at creation time via API:

```json
{
  "topic": "MATH benchmark",
  "config": {
    "llm": { "default_model": "gpt-4o", "cost_ceiling": 5.00 },
    "pipeline": {
      "skip_stages": ["literature_review"],
      "stage_config": { "experiment": { "max_iterations": 10 } }
    },
    "agents": { "use": ["phd_student", "ml_engineer", "custom_chemist"] }
  }
}
```

---

## 11. Deployment

### 11.1 Local Development

```bash
uv pip install agentlabx
agentlabx serve
# → http://localhost:8000
```

Stack: SQLite + local filesystem + subprocess execution. Zero external dependencies.

### 11.2 Docker Compose

```bash
docker compose up
```

Services: agentlabx-app (FastAPI + React, port 8000) + postgres (port 5432) + minio (port 9000) + experiment runner (Docker-in-Docker, ephemeral containers).

### 11.3 Production (future)

Adds: OAuth/JWT auth, Kubernetes execution backend, Redis for WebSocket pub/sub, horizontal scaling.

---

## 12. Tech Stack Summary

### Backend
- Python 3.11+
- FastAPI — REST + WebSocket
- LangGraph — pipeline orchestration
- LiteLLM — LLM provider routing (wrapped in our own abstraction)
- Pydantic v2 — config + validation
- SQLAlchemy 2 (async) — ORM
- Alembic — database migrations
- Docker SDK — container execution
- uv — package management

### Frontend
- React 19 + TypeScript
- Vite — build tool
- Ant Design 5 — component library
- @ant-design/plots — charts
- React Flow — pipeline graph visualization
- Zustand — state management
- TanStack Query — data fetching
- openapi-typescript — typed API client

### Infrastructure
- SQLite (local default) / PostgreSQL (production)
- Local filesystem (default) / MinIO (S3-compatible, production)
- Docker / subprocess — execution backends
- pytest + Vitest — testing
- Ruff — Python linting
- ESLint + Prettier — JS linting

### Research Tools
- arxiv — paper search
- semanticscholar — citation search
- huggingface_hub — dataset search
- PyPDF2 — PDF extraction
- pdflatex — LaTeX compilation
- scikit-learn — TF-IDF based search

---

## 13. MVP Scope

Priority: **pipeline modularity first**.

### MVP includes:
- LangGraph pipeline with all 8 default stages as plugins (including data exploration)
- PI agent as intelligent transition handler with confidence-based fallback
- Hypothesis tracking as first-class pipeline state
- Experimentation stage with enforced baselines and ablation structure
- Reproducibility metadata auto-captured by execution backend
- Agent config system (YAML + code extensibility)
- Differentiated agent memory scopes (permeable, not siloed) with blind reviewer isolation
- Literature search as both a stage AND a cross-cutting tool available to all agents
- Cross-stage targeted requests (report → experiment without full backtrack)
- Lab meeting subgraph with proper budget/stuck separation
- Budget policy system (warning → conservative PI, not more meetings)
- Subprocess execution backend (Docker as opt-in)
- SQLite + local filesystem storage
- LiteLLM-based LLM provider with cost tracking
- Built-in code agent (fallback) + Claude Code adapter
- GitHub search + session artifact search tools
- FastAPI server with REST + WebSocket
- Functional React/Ant Design UI (session list, pipeline view, agent activity feed, mode controls, per-stage review toggles, hypothesis tracker)
- Plugin registry with decorator and YAML config registration
- Configuration hierarchy with per-session overrides
- `agentlabx serve` one-command startup

### Deferred to later versions:
- Entry point plugin discovery (third-party packages)
- User authentication and RBAC
- PostgreSQL + MinIO storage backends (architecture-ready; Docker Compose profile exists for early adopters, but not the default MVP path)
- Kubernetes execution backend
- Session archival and cold storage
- Additional code agent adapters (Aider, Codex)
- Scheduled periodic lab meetings
- Cross-session artifact sharing UI
- Configurable alternative LLM provider for reviewer agents (bias reduction)
