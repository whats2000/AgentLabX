<div align="center">

# AgentLabX

### Open research-automation platform — Stage A1 foundation

**Multi-user backend + minimal web shell for a future LLM-agent research pipeline. Stage A1 delivers the identity, credential, session, audit, and plugin plumbing that every later stage will plug into.**

[![Python 3.12+](https://img.shields.io/badge/python-3.12+-blue.svg)](https://www.python.org/downloads/)
[![React 19](https://img.shields.io/badge/react-19-61dafb.svg)](https://react.dev/)
[![FastAPI](https://img.shields.io/badge/fastapi-0.115+-009688.svg)](https://fastapi.tiangolo.com/)
[![License: Apache 2.0](https://img.shields.io/badge/license-Apache%202.0-green.svg)](LICENSE)
[![Tests](https://img.shields.io/badge/tests-91%20passing-brightgreen.svg)](#development)

[Quickstart](docs/quickstart.md) · [Vision](docs/superpowers/specs/2026-04-15-agentlabx-vision.md) · [SRS](docs/superpowers/specs/2026-04-15-agentlabx-srs.md) · [A1 plan](docs/superpowers/plans/2026-04-15-stageA1-foundation-infrastructure.md)

</div>

---

## Status — Stage A1 Foundation Infrastructure

This repository is a ground-up rewrite of an earlier prototype. **Stage A1 ships the backend foundation and a minimal browser shell to exercise it.** Research agents, LLM calls, MCP tools, and stage orchestration are **not yet implemented** — they live in later stages of the roadmap (see [SRS §4](docs/superpowers/specs/2026-04-15-agentlabx-srs.md#part-4--build-roadmap-stage-sequence)).

### What A1 delivers

| | |
|---|---|
| 🔐 **Three authers** | `DefaultAuther` (passphrase + argon2), `TokenAuther` (bearer), `OAuthAuther` (RFC 8628 device flow, library-only) |
| 👤 **Owner + admin roles** | First-registered user is the immutable Owner; admins provision additional users and manage capabilities |
| 🔑 **Per-user encrypted credentials** | Fernet-encrypted at rest, master key held in the OS keyring; credentials never touch `.env` |
| 🍪 **Sessions + API tokens** | `HttpOnly` signed cookies for the browser, `Authorization: Bearer` for scripted clients — live side-by-side |
| 🧾 **Audit log** | Every auth + admin mutation emits a structured event; JSONL log on disk; admin view + archive-on-clear |
| 🚦 **Rate-limited login** | Per-email sliding window, 429 + `Retry-After` after 5 failures in 5 minutes, 15-minute lockout |
| 🗄️ **SQLite + migrations** | SQLAlchemy 2 async, aiosqlite, FK-cascades enforced, in-place forward migrations between schema versions |
| 🧩 **Plugin registry** | `importlib.metadata` entry-point discovery skeleton — stages, authers, LLM providers, MCP bundles will register here |
| 🖥️ **Minimal browser shell** | React 19 + Tailwind + shadcn/ui: login, profile, credentials, admin users, audit activity, session management |
| 🛠️ **Three CLI commands** | `agentlabx serve`, `agentlabx bootstrap-admin`, `agentlabx reset-passphrase` |
| ✅ **91 tests** | pytest + pytest-asyncio; ruff + mypy strict; TypeScript strict on the frontend |

### What's NOT here yet

- Research stages (literature review, plan formulation, experimentation, report writing, peer review) — Layer B
- LLM provider integration (LiteLLM + traced wrapper + budget cap) — Stage A2
- MCP host + bundled tool servers (arxiv, semantic-scholar, code-execution, browser, filesystem, memory) — Stage A3
- Literature RAG with citation verifier — Stage A5
- Orchestrator with zones, checkpoints, assist mode — Stage A7
- PI agent + configurable-agent layer — Stage A8
- `agentlabx reproduce` CLI + end-to-end harness — Stage C2
- Shared experiment-memory governance — Stage C4

See the [full roadmap in the SRS](docs/superpowers/specs/2026-04-15-agentlabx-srs.md#part-4--build-roadmap-stage-sequence) for the Layer A → Layer B → Layer C sequence.

---

## Quick start

**Five-minute walkthrough:** [`docs/quickstart.md`](docs/quickstart.md)

```bash
# 1. Install Python + frontend dependencies (requires Python 3.12+, Node 20+, uv, npm)
uv sync --extra dev
(cd web && npm install)

# 2. Create the Owner identity (first and only person who can never be demoted)
uv run agentlabx bootstrap-admin --display-name "Alice" --email alice@example.com
# → prompts for a passphrase (entered twice)

# 3. Run the backend on loopback
uv run agentlabx serve --bind loopback --port 8765

# 4. In another terminal, run the Vite dev server
(cd web && npm run dev)
# → open http://127.0.0.1:5173, log in as alice@example.com
```

> On first start the server writes SQLite + event log under `~/.agentlabx/`. Delete that directory to reset the install.

For LAN binding (lab deployment) you pass `--bind lan --tls-cert CERT --tls-key KEY`; TLS is enforced on non-loopback bind.

---

## Try out the A1 surface

Once you're logged in, the browser shell gives you:

- **Sidebar bottom → click your name** — popover menu with Profile + Credentials + Log out.
- **Profile** (`/profile`) — update display name / email / passphrase (email + passphrase changes require your current passphrase); issue, list, and revoke personal API tokens; view and revoke active sessions across devices.
- **Credentials** (`/settings`) — add, reveal, and delete encrypted key slots (e.g. `anthropic`, `openai`). Each slot's plaintext value is only revealed on demand.
- **Admin Users** (admin-only, `/admin`) — provision additional users, grant/revoke the `admin` capability (Owner row is protected with `(owner)` tag), delete users with confirm-dialog.
- **Activity** (admin-only, `/admin/activity`) — tail the JSONL audit log, filter newest-first, clear (archived to a timestamped `audit.<ts>.cleared.jsonl` — never truly destroyed).

**Test the bearer-token flow from a shell:**

```bash
# Issue a token from /profile → Personal API tokens → Issue token
# Then use it:
curl -H "Authorization: Bearer ax_..." http://127.0.0.1:8765/api/auth/me
```

**Locked out?** Reset your own passphrase (or the Owner's) from the server shell:

```bash
uv run agentlabx reset-passphrase --email alice@example.com
# revokes all sessions + tokens for the user as a side-effect
```

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

docs/superpowers/              vision + SRS + Stage A1 implementation plan
tests/                         91 tests: 75 unit, 16 integration
```

**Configuration:** environment variables prefixed `AGENTLABX_` override defaults. See [`agentlabx/config/settings.py`](agentlabx/config/settings.py).

---

## Development

```bash
# Backend gates
uv sync --extra dev
uv run pytest -v                           # 91 passing
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

### Project memory

This project follows a **spec → plan → subagent-driven execution → review** workflow. Authoritative docs:

- **Vision** — [`docs/superpowers/specs/2026-04-15-agentlabx-vision.md`](docs/superpowers/specs/2026-04-15-agentlabx-vision.md) — north star, non-negotiable principles.
- **SRS** — [`docs/superpowers/specs/2026-04-15-agentlabx-srs.md`](docs/superpowers/specs/2026-04-15-agentlabx-srs.md) — full system requirements, architecture, and build roadmap (Layer A / Layer B / Layer C).
- **A1 plan** — [`docs/superpowers/plans/2026-04-15-stageA1-foundation-infrastructure.md`](docs/superpowers/plans/2026-04-15-stageA1-foundation-infrastructure.md) — 29-task implementation plan that delivered A1.

New features land as a spec amendment (if the SRS diverges) + a plan doc + task-by-task subagent execution with tests and commits. Small fixes can skip the plan step.

---

## Roadmap

**Layer A — Backend framework** (foundation before any research stage)

- [x] **A1 — Foundation infrastructure** ← you are here
- [ ] A2 — LLM provider module (LiteLLM + traced wrapper + budget cap)
- [ ] A3 — MCP host + bundled servers (arxiv, semantic-scholar, code-exec, browser, filesystem, memory)
- [ ] A4 — Stage contract framework (all stage I/O Pydantic contracts defined upfront)
- [ ] A5 — RAG component (Chroma + three-index + citation verifier)
- [ ] A6 — Orchestrator + traffic engine + zones + checkpoint/resume + assist mode
- [ ] A7 — Current-run experiment notes
- [ ] A8 — Configurable agent layer (PI as user's decision proxy)

**Layer B — Research stage implementations** (happy-path order, each gated by its own real-LLM harness)

- [ ] B1 — literature_review  ·  B2 — plan_formulation  ·  B3 — data_exploration
- [ ] B4 — data_preparation  ·  B5 — experimentation  ·  B6 — interpretation
- [ ] B7 — report_writing  ·  B8 — peer_review

**Layer C — Frontend, reproducibility, hardening, memory governance**

- [ ] C1 — Full frontend (main graph, inner stage views, PI decision panel)
- [ ] C2 — `agentlabx reproduce` CLI + e2e semantic-fact assertion harness
- [ ] C3 — Multi-user-on-one-install adversarial hardening
- [ ] C4 — Shared experiment memory governance (curator workflow, taxonomy from observed material)

---

## License

Licensed under the **Apache License, Version 2.0** — see [LICENSE](LICENSE).
