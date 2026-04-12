# AgentLabX

**A modular autonomous research platform with extensible agent pipelines, coding agents, and experiment orchestration.**

AgentLabX coordinates a small team of LLM-backed agents — PhD student, postdoc, ML engineer, software engineer, professor, reviewers, and a supervising PI — through an eight-stage research pipeline: literature review → plan formulation → data exploration → data preparation → experimentation → results interpretation → report writing → peer review. Each stage is an editable LangGraph node; each agent runs under an explicit memory scope; every run is reproducible by construction (random seed, environment hash, dependency snapshot, run command).

The platform ships with a React dashboard that lets a researcher create a session, watch it execute live over a WebSocket, steer it interactively, and review every artifact and cost breakdown along the way.

---

## Quick start

See [`docs/quickstart.md`](docs/quickstart.md) for the five-minute walkthrough (clone → install → `--mock-llm` → create a session in the browser). Short version:

```bash
# 1. Install
uv sync --extra dev

# 2. Run the backend with a mock LLM (no API keys needed)
uv run agentlabx serve --mock-llm

# 3. Build + open the UI
# Option A — built SPA served by FastAPI at http://localhost:8000
cd web && npm install && npm run build
# then open http://localhost:8000 in a browser

# Option B — Vite dev server with hot reload at http://localhost:5173
cd web && npm install && npm run dev
# (the backend must be running at localhost:8000 so /api and /ws proxy works)
```

REST docs: `http://localhost:8000/docs`

For a real run with live models, copy `.env.example` → `.env` and fill in at least one provider key (OpenAI / Anthropic / Gemini / DeepSeek), then start without `--mock-llm`.

---

## Architecture

```
agentlabx/               Python backend
  core/      config, registry, session, state (PipelineState), event bus
  stages/    8-stage pipeline + StageRunner + PipelineBuilder + TransitionHandler
  agents/    ConfigAgent (YAML-driven), PI Agent, ContextAssembler
  providers/ LiteLLM, SQLite, subprocess execution, built-in code agent
  tools/     arXiv, Semantic Scholar, GitHub, HuggingFace, code executor, LaTeX
  server/    FastAPI app, REST routes, WebSocket, executor, SPA static mount
  cli/       `agentlabx serve` entry point

web/                     React frontend
  src/
    api/        openapi-fetch REST client, WebSocket service, wsRegistry singleton
    hooks/      TanStack Query hooks, useWebSocket
    stores/     Zustand (wsStore + uiStore only; server data lives in TanStack)
    pages/      Session List / Create / Detail, Plugin Browser, Settings
    components/ session detail panels (PipelineGraph, AgentActivityFeed, ...)

config/      YAML defaults (overridden by env vars: AGENTLABX_*)
docs/        Platform design spec + implementation plans
tests/       pytest (backend, 426 tests)
web/tests/   vitest + React Testing Library (frontend, 102 tests)
```

Configuration layers (highest precedence wins): process env → `AGENTLABX_*` env vars → `config/default.yaml` → model defaults.

---

## Core principles

**Reproducibility.** Every experiment records a `ReproducibilityRecord` with random seed, environment hash, run command, container image (when available), git ref, and full dependency snapshot. Runs can be replayed or audited.

**Structured artifacts.** Agents emit typed Pydantic models (`ResearchPlan`, `LitReviewResult`, `Hypothesis`, `ExperimentResult`, `ReportResult`, `ReviewResult`) rather than free-form text. Cross-stage artifacts flow through LangGraph state with reducer annotations.

**Hypothesis–experiment loop.** Hypotheses are first-class state: `active`, `supported`, `refuted`, or `abandoned`, with `evidence_for` / `evidence_against` links back to specific experiment results. The PI agent consults them when deciding whether to backtrack.

**Memory scopes.** Each agent declares what it can read and what it can write. A reviewer can't see the plan it's reviewing; a PhD student can't rewrite the methodology. Scopes are enforced by `ContextAssembler` before every LLM call.

**Automation with oversight.** Per-stage control levels (`auto` / `notify` / `approve` / `edit`) let a user flip any single stage into HITL mode mid-run. The backend owns a cooperative pause event; pressing "Pause" actually halts the next stage, not the event queue.

**Traceability.** Every LLM call, tool call, cost update, and transition is logged via the event bus and broadcast over the WebSocket. AsyncSqliteSaver checkpoints state after every node so a server restart replays cleanly.

---

## Status

**Done (Plans 1–5, 527 tests green):**

- [x] Core engine — registry, state, events, base classes
- [x] 8-stage pipeline with zone-based LangGraph routing + TransitionHandler priority scheme
- [x] 7 configurable YAML agents + PI agent with JSON-mode structured output
- [x] LiteLLM provider with retry + cost tracking; SQLite storage with session namespacing
- [x] 7 research tools (arxiv, semanticscholar, GitHub, HF, session artifact search, code executor, LaTeX)
- [x] FastAPI server: sessions CRUD + lifecycle, preferences, artifacts, transitions, cost, hypotheses, plugins, WebSocket
- [x] Cooperative pause / AsyncSqliteSaver checkpointing / session-owned EventBus / single WS subscription per session
- [x] React 19 + TypeScript + Vite 6 + Ant Design 5 frontend with OpenWebUI-inspired aesthetic
- [x] openapi-fetch typed REST client + WebSocket registry singleton + WS→TanStack invalidation
- [x] Pipeline graph (React Flow), activity feed, stage output panel, hypothesis tracker, control bar, feedback input, cost tracker, checkpoint modal
- [x] FastAPI `mount_spa()` so `agentlabx serve` delivers the full UI from a single process

**Deferred (post-MVP):**

- [ ] Docker execution backend + Compose deployment recipe
- [ ] PostgreSQL + MinIO storage (architecture is ready)
- [ ] OAuth / JWT auth (single-user mode today)
- [ ] Real `agent_thinking` / `agent_tool_call` / `agent_dialogue` event emission (the wire format exists; backend agents don't stream yet)
- [ ] Full HITL interrupt flow — CheckpointModal ships observable (records the action, backend logs it); real LangGraph interrupt resume lands in a later plan
- [ ] Hard budget-ceiling enforcement (warning/critical tiers work; nothing halts spend at 100% yet)
- [ ] `.entry-points` third-party plugin auto-discovery
- [ ] Dark-mode toggle, i18n, mobile layouts

---

## Development

```bash
# Backend
uv sync --extra dev
uv run pytest                              # 426 passing
uv run ruff check agentlabx tests          # lint
uv run agentlabx serve --mock-llm          # run without API keys

# Frontend
cd web
npm install
npm run typecheck
npm run lint
npm test -- --run                          # 102 passing
npm run dev                                # Vite dev server at :5173
npm run build                              # emits web/dist/ for FastAPI to serve
npm run codegen                            # regenerate src/api/generated.ts from /openapi.json
```

- **Specification:** [`docs/superpowers/specs/2026-04-12-agentlabx-platform-design.md`](docs/superpowers/specs/2026-04-12-agentlabx-platform-design.md)
- **Implementation plans (5 plans, ~100 commits):** [`docs/superpowers/plans/`](docs/superpowers/plans/)

---

## Contributing

Contributions welcome. The codebase follows a "plan → execute → review" workflow documented in the [`docs/superpowers/`](docs/superpowers/) tree — new features should land as a plan doc + task-by-task implementation with tests and commits. Small bug fixes or tooling improvements can skip the plan step.

Open an issue before starting anything non-trivial so we can align on scope.

---

## License

TBD — a `LICENSE` file has not been chosen yet. Until one lands, assume no permissive license.
