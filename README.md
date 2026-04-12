<div align="center">

# AgentLabX

### A modular autonomous research platform

**Coordinates a small team of LLM-backed agents through an 8-stage research pipeline: literature review → plan → experimentation → report → peer review. Every run is reproducible. Every stage is editable. Every artifact is structured.**

[![Python 3.12+](https://img.shields.io/badge/python-3.12+-blue.svg)](https://www.python.org/downloads/)
[![React 19](https://img.shields.io/badge/react-19-61dafb.svg)](https://react.dev/)
[![LangGraph](https://img.shields.io/badge/langgraph-0.4+-orange.svg)](https://langchain-ai.github.io/langgraph/)
[![FastAPI](https://img.shields.io/badge/fastapi-0.115+-009688.svg)](https://fastapi.tiangolo.com/)
[![License: Apache 2.0](https://img.shields.io/badge/license-Apache%202.0-green.svg)](LICENSE)
[![Tests](https://img.shields.io/badge/tests-528%20passing-brightgreen.svg)](#development)

[Quickstart](docs/quickstart.md) · [Spec](docs/superpowers/specs/2026-04-12-agentlabx-platform-design.md) · [Plans](docs/superpowers/plans/) · [API docs](http://localhost:8000/docs)

</div>

---

## What is this

A PhD student, a postdoc, an ML engineer, a software engineer, a professor, a panel of blind reviewers, and a supervising PI — each backed by an LLM, each with its own memory scope, each running as a LangGraph node. They collaborate through an 8-stage research pipeline and produce a peer-reviewed paper at the end.

You watch the whole thing happen live in the browser. You pause it. You redirect it. You inspect every artifact along the way. Every experiment ships with a reproducibility record so someone else can rerun it.

It runs on your laptop. No cloud. No accounts. One command.

```bash
uv run agentlabx serve --mock-llm
# open http://localhost:8000
```

<div align="center">

| | |
|---|---|
| 🧠 **Differentiated agents** | 7 role-based agents + a supervising PI, each with its own YAML-configured memory scope |
| 🔄 **LangGraph pipeline** | 8 stages with zone-based routing, typed state, and priority-based transitions |
| 🔬 **Structured artifacts** | Pydantic models for every output: hypotheses, plans, experiments, reviews |
| 🧪 **Reproducible by construction** | Seed, env hash, run command, git ref, and dependency snapshot per experiment |
| 👀 **Human-in-the-loop ready** | Per-stage control levels (auto / notify / approve / edit), flip any stage live |
| 🧩 **Plugin architecture** | Stages, tools, agents, LLMs, backends — all swappable via a typed registry |
| ⚡ **Live dashboard** | React 19 + Ant Design + React Flow. WebSocket streams every event to the UI |
| 💰 **Cost-aware** | Per-session budget ceilings with warning/critical tiers and live gauges |

</div>

---

## Quick start

**Five-minute walkthrough:** [`docs/quickstart.md`](docs/quickstart.md)

```bash
# 1. Install (requires Python 3.12+, Node 20+, uv, npm)
uv sync --extra dev

# 2. Build the UI once
cd web && npm install && npm run build && cd ..

# 3. Start the server with a mock LLM — no API keys needed
uv run agentlabx serve --mock-llm

# 4. Open http://localhost:8000 and create a session
```

For a real run, copy `.env.example` → `.env`, add one provider key (OpenAI, Anthropic, Gemini, or DeepSeek), and restart without `--mock-llm`.

<details>
<summary><strong>Dev mode with hot reload</strong></summary>

```bash
# Terminal 1 — backend
uv run agentlabx serve --mock-llm

# Terminal 2 — Vite dev server
cd web && npm run dev
# open http://localhost:5173 (proxies /api and /ws to :8000)
```

</details>

---

## The 8-stage pipeline

```
  ┌──────────────────┐   ┌────────────────┐   ┌──────────────────┐
  │   DISCOVERY      │──▶│ IMPLEMENTATION │──▶│     SYNTHESIS    │
  ├──────────────────┤   ├────────────────┤   ├──────────────────┤
  │ literature_review│   │ data_exploration│  │ results_interpret│
  │ plan_formulation │   │ data_preparation│  │ report_writing   │
  │                  │   │ experimentation │  │ peer_review      │
  └──────────────────┘   └────────────────┘   └──────────────────┘
                                │                       │
                                └──── backtrack ────────┘
                               (PI agent decides when)
```

Each stage is a LangGraph node backed by a `BaseStage` plugin. The PI agent watches the outputs and can backtrack the pipeline to a prior stage when evidence demands it (failed experiments, plateaued scores, negative results). The default sequence is overridable per-session.

---

## Architecture

```
agentlabx/                     Python backend (FastAPI + LangGraph)
├── core/                      config, registry, session, PipelineState, event bus
├── stages/                    StageRunner, PipelineBuilder, TransitionHandler
├── agents/                    ConfigAgent, PI Agent, ContextAssembler, lab meeting
├── providers/                 LiteLLM, SQLite, subprocess exec, built-in code agent
├── tools/                     arXiv, Semantic Scholar, GitHub, HuggingFace, LaTeX
├── server/                    REST routes, WebSocket, executor, SPA mount
└── cli/                       `agentlabx serve`

web/                           React frontend (Vite + TypeScript + Ant Design 5)
├── src/api/                   openapi-fetch client, WS service, registry singleton
├── src/hooks/                 TanStack Query hooks, useWebSocket
├── src/stores/                Zustand (client-only: wsStore + uiStore)
├── src/pages/                 Session List / Create / Detail, Plugins, Settings
└── src/components/session/    PipelineGraph, ActivityFeed, ControlBar, CostTracker...

config/                        YAML defaults (overridable via AGENTLABX_* env)
docs/                          spec + implementation plans
tests/   web/tests/            pytest (426) + vitest (102) = 528 tests
```

**Configuration precedence:** process env → `AGENTLABX_*` → `config/default.yaml` → model defaults.

---

## Core principles

<table>
<tr>
<td width="33%" valign="top">

**🔁 Reproducibility**

Every experiment records a `ReproducibilityRecord`: random seed, environment hash, run command, container image, git ref, full dependency snapshot. Runs can be replayed or audited.

</td>
<td width="33%" valign="top">

**📦 Structured artifacts**

Agents emit typed Pydantic models (`ResearchPlan`, `Hypothesis`, `ExperimentResult`, `ReportResult`), not free-form text. Cross-stage data flows through LangGraph state with reducer annotations.

</td>
<td width="33%" valign="top">

**🧬 Hypothesis loop**

Hypotheses are first-class state — `active`, `supported`, `refuted`, `abandoned` — with `evidence_for` and `evidence_against` links into specific experiments. The PI consults them before backtracking.

</td>
</tr>
<tr>
<td valign="top">

**🔒 Memory scopes**

Every agent declares what it can read and write. Reviewers can't see the plan they're reviewing. PhD students can't rewrite methodology. `ContextAssembler` enforces scopes before every LLM call.

</td>
<td valign="top">

**🎛️ Oversight**

Per-stage control: `auto` / `notify` / `approve` / `edit`. Flip any stage live mid-run. The backend owns a cooperative pause event — pressing Pause actually halts the next stage, not the queue.

</td>
<td valign="top">

**🔍 Traceability**

Every LLM call, tool call, cost update, and transition goes through the event bus and out over WebSocket. `AsyncSqliteSaver` checkpoints state after every node so server restarts replay cleanly.

</td>
</tr>
</table>

---

## Status

**✅ Done** — Plans 1–5 shipped, 528 tests green, MVP functional end-to-end

- Core engine: registry, typed state, event bus, base classes
- 8-stage pipeline with zone-based routing and priority-based transitions
- 7 YAML-configured agents + PI agent with JSON-mode structured output
- LiteLLM provider (retry + cost tracking); SQLite storage with session namespacing
- 7 research tools: arXiv, Semantic Scholar, GitHub, HuggingFace, session artifact search, code executor, LaTeX
- FastAPI server: 13 REST endpoints + WebSocket, cooperative pause, AsyncSqliteSaver checkpointing
- React 19 frontend with OpenWebUI-inspired aesthetic, live pipeline graph, activity feed, cost tracker, checkpoint modal
- One-process deployment: `agentlabx serve` delivers the full UI from FastAPI

**🔜 Deferred** — post-MVP

- Docker execution backend + Compose deployment
- PostgreSQL + MinIO storage (architecture-ready)
- OAuth / JWT auth (single-user today)
- Streaming `agent_thinking` events (wire format exists, agents don't stream yet)
- Full HITL interrupt — CheckpointModal ships observable (records the action, backend logs it); real LangGraph interrupt resume lands in a later plan
- Hard budget-ceiling enforcement (warning/critical tiers work; nothing halts spend at 100%)
- Third-party plugin auto-discovery via `entry-points`
- Dark mode, i18n, mobile layouts

---

## Development

```bash
# Backend
uv sync --extra dev
uv run pytest                              # 426 passing
uv run ruff check agentlabx tests
uv run agentlabx serve --mock-llm

# Frontend
cd web
npm install
npm run typecheck
npm run lint
npm test -- --run                          # 102 passing
npm run dev                                # Vite at :5173 with HMR
npm run build                              # emits web/dist/ for FastAPI
npm run codegen                            # regenerate src/api/generated.ts from live /openapi.json
```

### Tech stack

|              | |
|--------------|-|
| **Backend**  | Python 3.12, LangGraph 0.4+, FastAPI, uvicorn, LiteLLM, Pydantic v2, SQLAlchemy 2 async, aiosqlite, AsyncSqliteSaver |
| **Frontend** | React 19, TypeScript 5.5, Vite 6, Ant Design 5, @xyflow/react (React Flow), @ant-design/plots, Zustand 5, TanStack Query 5, openapi-fetch |
| **Testing**  | pytest + pytest-asyncio (backend), vitest + React Testing Library (frontend) |
| **Tooling**  | uv, ruff, eslint flat config, openapi-typescript |

### Contributing

The codebase follows a **plan → execute → review** workflow documented in [`docs/superpowers/`](docs/superpowers/). New features land as a plan doc + task-by-task implementation with tests and commits. Small bug fixes or tooling tweaks can skip the plan step.

Open an issue before starting anything non-trivial so we can align on scope.

---

## Documentation

- 📖 [**Quickstart**](docs/quickstart.md) — five-minute path from clone to a running session
- 📐 [**Platform spec**](docs/superpowers/specs/2026-04-12-agentlabx-platform-design.md) — the full design document
- 📋 [**Implementation plans**](docs/superpowers/plans/) — five plans covering core engine → pipeline → providers → server → frontend
- 🔌 **API docs** — live at `/docs` when the server is running

---

## License

Licensed under the **Apache License, Version 2.0** — see [LICENSE](LICENSE).
