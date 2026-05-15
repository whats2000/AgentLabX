<div align="center">

# AgentLabX

### Open research-automation platform

**A researcher defines a topic. A team of LLM-powered agents takes it end-to-end — reviewing literature, forming a plan, preparing data, running experiments with baselines and ablations, interpreting results, writing a report, and critiquing it — with a principal-investigator agent overseeing strategic decisions. Local-first, observable at every step, and reproducible by construction.**

[![Python 3.12+](https://img.shields.io/badge/python-3.12+-blue.svg)](https://www.python.org/downloads/)
[![React 19](https://img.shields.io/badge/react-19-61dafb.svg)](https://react.dev/)
[![FastAPI](https://img.shields.io/badge/fastapi-0.115+-009688.svg)](https://fastapi.tiangolo.com/)
[![License: Apache 2.0](https://img.shields.io/badge/license-Apache%202.0-green.svg)](LICENSE)

[Quickstart](docs/quickstart.md) · [Vision](docs/superpowers/specs/2026-04-15-agentlabx-vision.md) · [SRS](docs/superpowers/specs/2026-04-15-agentlabx-srs.md) · [Plans](docs/superpowers/plans/)

</div>

---

## What AgentLabX is

A rewrite of an earlier prototype, focused on producing research that resembles real lab output rather than a prompt chain. Every stage is a swappable module with a formal input/output contract, every tool is a standards-compliant MCP server, every credential is per-user and encrypted, and every step is observable.

The end product is a reproducible research artifact — **literature survey · research plan · executed experiments with baselines and ablations · interpretation · written report · peer review** — that a peer can hand-check number-by-number.

### The research pipeline

```
  ┌──────────────────┐   ┌──────────────────┐   ┌──────────────────┐
  │    DISCOVERY     │──>│  IMPLEMENTATION  │──>│     SYNTHESIS    │
  ├──────────────────┤   ├──────────────────┤   ├──────────────────┤
  │ literature_review│   │ data_exploration │   │  interpretation  │
  │ plan_formulation │   │ data_preparation │   │  report_writing  │
  │                  │   │  experimentation │   │   peer_review    │
  └──────────────────┘   └──────────────────┘   └──────────────────┘
           ▲                      ▲ │                     │
           │                      │ │                     │
           └──────────────────────┴─┴────── backtrack ────┘
                      (any stage may target any earlier stage;
                       stage-owned policy, partial rollback preserves
                       accepted artifacts; PI consulted only at
                       final-decision / clarification gates)
```

Each stage declares its **input contract, output contract, required tools, and completion criteria**. Multiple implementations of each stage can coexist behind the same contract — a simple baseline, a curated multi-turn version, a wrapper around a reference implementation — so users can compare method quality head-to-head on the same task.

Stages advance forward by default; if a stage uncovers evidence that invalidates earlier work it can request a backtrack with partial rollback that preserves accepted artifacts (literature entries, data splits, metrics). The **PI agent** — configured by the user — is consulted sparingly, only at final-decision gates or when a stage hits something only a human user can resolve (e.g., a missing API key).

### Core principles

<table>
<tr>
<td width="50%" valign="top">

**🔁 Reproducibility**

Every experiment records seed, environment hash, dependency snapshot, run command, container image, and git ref. An `agentlabx reproduce <artifact>` CLI rebuilds any run bit-for-bit on a clean machine.

</td>
<td width="50%" valign="top">

**📦 Contracts over conventions**

Every stage declares its I/O schema and completion criteria in Pydantic. Validation is deterministic; implementations are swappable behind the contract. `typing.Any` is banned project-wide — a stage that says nothing cannot be called "done".

</td>
</tr>
<tr>
<td valign="top">

**👤 User sovereignty**

Credentials live encrypted under the user's OS keyring, never in `.env` files or config repositories, never process-global. Multi-user from day one; solo use is the degenerate case under the same code path.

</td>
<td valign="top">

**🔍 Observable over opaque**

Every agent turn, tool call, stage transition, and PI decision is emitted as a structured event — consumable by the local UI, external test harnesses, and audit logs. No hidden work.

</td>
</tr>
<tr>
<td valign="top">

**🧩 Standards-compliant tools**

External tools (paper search, code execution, browser, filesystem, shared memory) are integrated as MCP servers. Bring your own or use the bundled set. Stages declare the capabilities they require; the orchestrator refuses to start if a capability is missing.

</td>
<td valign="top">

**🏗️ Incremental build-up**

The platform is assembled one stage at a time, each with its own spec, plan, and review. Plans declare the **contract** (what to build); subagent execution writes the code (how to build it). The two stay separate.

</td>
</tr>
</table>

---

## Roadmap

Three layers, built in strict order. Each stage delivers working, testable software; the next stage does not begin until its predecessor's gate passes.

### Layer A — Backend framework

Complete the full framework before any research stage exists. All stage I/O contracts are defined upfront in Stage A4 so implementations slot into a known shape rather than reshaping the framework mid-stream.

- [x] **A1 — Foundation infrastructure** — auth, sessions, encrypted credentials, event bus, plugin registry, migrations, CLI, test shell
- [x] **A2 — LLM provider module** — LiteLLM router · traced wrapper (events + cost + budget cap) · mock LLM server · per-user encrypted key wiring · `/api/llm/*` provider/model endpoints
- [x] **A3 — MCP host + bundled servers** — MCPHost lifecycle (per-handle owner-task pattern) · ToolDispatcher with capability gating · `x-agentlabx-capabilities` schema metadata · adopt-over-build bundles (filesystem, arxiv, semantic_scholar, browser, code_execution Docker-sandboxed) · in-process memory MCP server · `/api/mcp/*` REST surface · per-user vs admin scope isolation
- [x] **A4 — Stage contract framework** — `Stage` ABC + frozen Pydantic v2 I/O contracts for all 8 pipeline stages (`literature_review` → `peer_review`), `ReproducibilityContract`, `BacktrackSignal` (with `preserve: frozenset[str]` and canonical tag enforcement), `StageOutput`, `StageContext` (with `run_mode: Literal["auto","hitl"]`), `StageRegistry` with entry-point discovery + 5-rule registration enforcement (capability-tag mismatch WARNS, not raises), `StageIOValidator` with contract-driven enforcement, 8 deterministic `Echo*Stage` stubs registered under `agentlabx.stages`. **No Layer B implementations** — A4 ships the contract-of-contracts that makes Layer B drift-free.
- [ ] **A5 — RAG component** — Chroma · three-index design (project corpus / lab reference library / project artifact index) · citation verifier
- [ ] **A6 — Orchestrator + traffic engine + zones** — forward routing · backtrack edge tracking · partial rollback · per-edge retry caps · checkpoint + resume · assist mode · graph extraction API
- [ ] **A7 — Current-run experiment notes** — per-run server-local notes surface
- [ ] **A8 — Configurable agent layer** — user-maintained agent definitions (name · system prompt · per-stage tool allow-list) · PI agent as the user's decision proxy invoked at final/clarification gates only

### Layer B — Research stage implementations

Happy-path order, one at a time. Each stage ships its own internal flow, its own backtrack policy, and a stage-local real-LLM integration test. A stage is not "done" until its real-LLM test passes, and the next stage does not begin until then.

- [ ] **B1 — literature_review** (Discovery) — curated references with grounded citations
- [ ] **B2 — plan_formulation** (Discovery) — hypotheses · methodology · baselines · ablations
- [ ] **B3 — data_exploration** (Implementation) — summary stats · dataset characterization
- [ ] **B4 — data_preparation** (Implementation) — reproducible splits / transforms
- [ ] **B5 — experimentation** (Implementation) — baseline + ablations · reproducibility contract · checkpoint+resume
- [ ] **B6 — interpretation** (Synthesis) — grounded in actual metric values; no fabricated numbers
- [ ] **B7 — report_writing** (Synthesis) — Markdown / LaTeX / PDF · citation verifier enforced
- [ ] **B8 — peer_review** (Synthesis) — structured critique · backtrack signal can target any earlier stage

### Layer C — Frontend, reproducibility, hardening, memory governance

Built only after Layers A + B are complete — each needs something real to exercise it.

- [ ] **C1 — Full frontend** — main pipeline graph · per-stage inner views · backtrack animation · PI/User decision panel · artifact comparison view · cost/budget dashboard
- [ ] **C2 — Reproduce CLI + e2e harness** — `agentlabx reproduce <artifact>` · semantic-fact assertion harness driving integration tests across the whole pipeline
- [ ] **C3 — Multi-user-on-one-install hardening** — adversarial credential isolation · session audit · LAN-bind TLS audit
- [ ] **C4 — Shared experiment memory governance** — memory MCP server governance layer · category taxonomy seeded from observed Layer B material · curator workflow · cross-install via remote memory server

Full details: [SRS Part 4 — Build Roadmap](docs/superpowers/specs/2026-04-15-agentlabx-srs.md#part-4--build-roadmap-stage-sequence).

---

## Quick start

**Five-minute walkthrough:** [`docs/quickstart.md`](docs/quickstart.md)

### System dependencies

The backend launches MCP servers as subprocesses, so the host environment must provide three external runtimes in addition to Python 3.12+:

| Tool | Used by | Install |
|------|---------|---------|
| `uvx` | filesystem MCP bundle (and any Python-packaged MCP server) | ships with [`uv`](https://docs.astral.sh/uv/) |
| `npx` | arxiv-search / fetch and other Node-packaged MCP servers | Node.js ≥ 18 (`node --version`) |
| Docker Engine | code-execution sandbox | [docker.com/get-started](https://www.docker.com/get-started/) — daemon must be running |

The unit-test suite needs only Python; the integration / smoke suites assume all three are present and **do not skip on absence** — install them on every dev machine and CI runner.

```bash
# 1. Install dependencies (requires Python 3.12+, Node 20+, uv, npm, Docker)
uv sync --extra dev
(cd web && npm install)

# 2. Run the backend on loopback
uv run agentlabx serve --bind loopback --port 8765

# 3. In another terminal, run the Vite dev server
(cd web && npm run dev)
# → open http://127.0.0.1:5173
```

On a fresh install, the browser opens a **"Create first identity"** form — fill in your name, email, and passphrase to become the Owner. Alternatively, automate the first admin setup from the shell:

```bash
uv run agentlabx bootstrap-admin --display-name "Alice" --email alice@example.com
# → prompts for a passphrase (entered twice)
```

Either path is fine — they both hit the same backend code. The CLI variant is for headless / scripted installs (CI, container entrypoints); interactive operators can just open the browser.

> On first start the server writes SQLite + event log under `~/.agentlabx/`. Delete that directory to reset the install.

For LAN binding (lab deployment) you pass `--bind lan --tls-cert CERT --tls-key KEY`; TLS is enforced on non-loopback bind.

---

## Architecture

```
agentlabx/                     Python backend (FastAPI + SQLAlchemy 2 async)
├── auth/                      Auther Protocol, Default/Token/OAuth, Identity, AuthError
├── security/                  argon2 passwords, keyring store, Fernet encrypt/decrypt
├── config/                    pydantic-settings AppSettings, BindMode, TLS gate
├── db/                        schema (6 tables), session factory, in-place migrations
├── events/                    in-process asyncio pub/sub EventBus + JsonlEventSink
├── plugins/                   PluginRegistry + importlib.metadata discovery
├── models/                    Pydantic request/response DTOs
├── server/                    FastAPI app factory, session middleware + Bearer auth,
│                              dependencies (current_identity, require_admin), routers
│                              (auth, settings, runs, health), rate limiter
└── cli/                       `agentlabx serve` + `bootstrap-admin` + `reset-passphrase`

web/                           React frontend (Vite + TypeScript strict + Tailwind + shadcn/ui)
├── src/api/                   fetch-based client with FastAPI detail-parsing
├── src/auth/                  AuthProvider + LoginPage (bootstrap-aware default mode)
├── src/components/            Layout (Claude-style sidebar), ui/ (shadcn primitives),
│                              confirm-dialog, password-input
└── src/pages/                 SettingsPage (credentials), ProfilePage (self-edit + tokens +
                               sessions), AdminPage (users), AdminActivityPage (audit),
                               RunsPage (placeholder — Layer B will populate)

docs/superpowers/              vision + SRS + per-stage implementation plans
tests/                         pytest suite (unit + integration)
```

**Configuration:** environment variables prefixed `AGENTLABX_` override defaults. See [`agentlabx/config/settings.py`](agentlabx/config/settings.py).

---

## Development

```bash
# Backend gates
uv sync --extra dev
uv run pytest -v
uv run ruff check agentlabx tests
uv run mypy agentlabx tests
uv run agentlabx serve --bind loopback

# Frontend gates
cd web
npm install
npm run lint                               # tsc --noEmit
npm run build                              # emits web/dist/ for production serve
npm run dev                                # Vite at :5173, proxies /api to :8765
```

### Tech stack

|              | |
|--------------|-|
| **Backend**  | Python 3.12 · FastAPI · uvicorn · SQLAlchemy 2 async + aiosqlite · Pydantic 2 · argon2-cffi · cryptography (Fernet) · keyring · itsdangerous · click · httpx |
| **Frontend** | React 19 · Vite 5 · TypeScript 5 strict · Tailwind 3 · shadcn/ui · @radix-ui (alert-dialog, dropdown-menu, label, slot) · TanStack Query 5 · React Router 6 · lucide-react · sonner |
| **Testing**  | pytest 8 · pytest-asyncio · httpx · ruff (`ANN` incl. `ANN401`) · mypy strict (`disallow_any_explicit`, `disallow_any_generics`) · tsc --noEmit |
| **Tooling**  | uv (Python deps/lockfile), npm (JS deps), Vite (bundler) |

### Contributing

This project follows a **spec → plan → subagent-driven execution → review** workflow. Authoritative docs:

- **Vision** — [`docs/superpowers/specs/2026-04-15-agentlabx-vision.md`](docs/superpowers/specs/2026-04-15-agentlabx-vision.md) — north star, non-negotiable principles.
- **SRS** — [`docs/superpowers/specs/2026-04-15-agentlabx-srs.md`](docs/superpowers/specs/2026-04-15-agentlabx-srs.md) — full system requirements, architecture, and the Layer A / B / C build roadmap.
- **Stage plans** — [`docs/superpowers/plans/`](docs/superpowers/plans/) — each stage gets its own contract-driven implementation plan.

New features land as a spec amendment (if the SRS diverges) + a plan doc + task-by-task subagent execution with tests and commits. Small fixes can skip the plan step.

---

## License

Licensed under the **Apache License, Version 2.0** — see [LICENSE](LICENSE).
