# Claude — AgentLabX project notes

This file orients you (Claude) on AgentLabX. Read it before touching code.

## Authoritative documents

Treat these as the source of truth — when implementation drifts from them,
ask before diverging and update them after the user approves.

- **Vision** — north-star, scope, principles:
  [`docs/superpowers/specs/2026-04-15-agentlabx-vision.md`](docs/superpowers/specs/2026-04-15-agentlabx-vision.md)
- **Software Requirements Specification (SRS)** — module surfaces, contracts,
  and the per-stage roadmap (Layer A backend → Layer B research stages →
  Layer C frontend / reproducibility):
  [`docs/superpowers/specs/2026-04-15-agentlabx-srs.md`](docs/superpowers/specs/2026-04-15-agentlabx-srs.md)
- **Per-stage implementation plans** — one file per stage gate (A1, A2, A3,
  …). Each plan declares the contract, the file structure, and the
  verification gate the stage must satisfy:
  [`docs/superpowers/plans/`](docs/superpowers/plans/)

When you finish a stage, reverse-engineer the SRS section for that stage
to reflect what actually shipped — drift between the SRS and the code is a
documented anti-pattern (see the "spec alignment" memory note).

## Codebase shape

- `agentlabx/` — Python backend. Strict typing rules apply: no `typing.Any`,
  no `object`-as-placeholder. Tests are not exempt. ruff `ANN401` enforces.
- `web/` — TypeScript / React frontend (shadcn/ui + Tailwind, OpenWebUI-style
  cards, sidebar with icons). `strict: true` + `noImplicitAny: true`; `any`
  and unnarrowed `unknown` are treated identically to Python `Any`.
- `tests/` — pytest. Integration tests under `tests/integration/`;
  unit tests under `tests/unit/`. Mark integration tests with the
  `integration` marker. Real-LLM tests use the `real_llm` marker.
- `docs/superpowers/` — vision, SRS, plans, and any future review notes.

## Workflow conventions

- **Branches in main repo, never worktrees.** Naming: `stageXN-name`
  (e.g. `stageA2-llm-provider`, `stageA3-mcp-host`).
- **Never merge to main without explicit user permission.** "Continue" /
  "looks good" is not consent — wait for "yes, merge it" or equivalent.
- **Per-stage build gates**: framework-first, three gates (auth + module +
  verification), no half-finished implementations.
- **Pre-commit hooks** are required: ruff, ruff-format, mypy --strict
  (where applicable), prettier for `web/`, mixed-line-ending normalisation.
- **Use `uv` for Python** (`uv run pytest`, `uv run mypy --strict ...`,
  `uv run agentlabx serve --reload` for backend hot-reload in dev).
- **Frontend dev** via Vite; production-mode backend via
  `uv run agentlabx serve --bind loopback --port 8765`.

## What's shipped

- **Stage A1** — auth, sessions, encrypted credentials, event bus,
  migrations, CLI, React shell.
- **Stage A2** — LiteLLM router + traced wrapper (events / cost /
  budget cap), per-user encrypted key wiring, `/api/llm/*` endpoints.
- **Stage A3** — MCP host + dispatcher with capability gating, six
  bundled servers (filesystem, arxiv, semantic_scholar, browser,
  code_execution, memory), `/api/mcp/*` REST surface, `/mcp` UI.
- See [`README.md`](README.md) for the full per-stage progress list.
