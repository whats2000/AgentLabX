# Quickstart

Get from a fresh clone to a running research session in about five minutes. No API keys required — the default `--mock-llm` path uses canned responses so you can verify the plumbing before committing to a provider bill.

## Prerequisites

- **Python 3.12+** with [`uv`](https://docs.astral.sh/uv/) on `PATH` (`uv --version`)
- **Node.js 20+** and **npm 10+** (`node --version`)
- A recent git checkout of this repo

## 1. Install

```bash
git clone https://github.com/<you>/AgentLabX.git
cd AgentLabX
uv sync --extra dev
```

`uv sync` creates `.venv/`, installs the `agentlabx` package in editable mode, and pulls dev dependencies (pytest, ruff, httpx). First-time install takes 30-60 seconds.

## 2. Build the frontend

```bash
cd web
npm install
npm run build
cd ..
```

This produces `web/dist/index.html` and bundled assets. The backend's `mount_spa()` detects the directory and serves it at `/`.

> Skip this step if you only want to poke the REST API; `agentlabx serve` runs fine without a built frontend.

## 3. Start the server

```bash
uv run agentlabx serve --mock-llm
```

You should see uvicorn bind `http://0.0.0.0:8000`. Leave it running.

## 4. Open the dashboard

Browse to **http://localhost:8000**. You'll see the AgentLabX shell with an empty "Sessions" table.

- **http://localhost:8000/docs** — live OpenAPI docs
- **http://localhost:8000/openapi.json** — raw spec (regenerate frontend types from this)

## 5. Run a session

1. Click **New Session** (top right)
2. **Topic** step — enter anything ≥ 10 characters (e.g. "Effect of dropout on transformer convergence")
3. **Pipeline** step — leave defaults
4. **HITL controls** step — auto mode skips this
5. **Review** step — click **Create session**

You land on the session detail page. Click **Start session** in the left sidebar. The pipeline runs through all eight stages in a few seconds (mock LLM is fast). Watch:

- **Activity tab** — event feed updates in real time
- **Graph tab** — stage nodes light up as they complete
- **Artifacts tab** — each stage's structured output appears (literature review table, plan goals, experiment metrics, LaTeX report, reviewer scores)
- **Cost tab** — $0.00 in mock mode
- **Right sider** — hypothesis tracker fills in

When the session reaches `peer_review` and completes, the status pill flips to green. You can delete the session from the list view to clean up.

## 6. Swap in a real LLM

Copy `.env.example` → `.env`, add one provider key (Anthropic is a good default: `ANTHROPIC_API_KEY=sk-ant-...`), then restart:

```bash
# stop the previous server (Ctrl+C), then:
uv run agentlabx serve
```

The session create wizard's "LLM configuration" tab (in Settings) lets you set a cost ceiling; with a real model enabled, the pipeline makes real calls. Expect a full run to cost $0.10–$1.00 depending on topic complexity and the model you pick.

## Troubleshooting

**Port 8000 is already in use.** Either stop the other service or set `AGENTLABX_SERVER__PORT=8001`.

**The React bundle isn't served at `/`.** Make sure you ran `npm run build` in `web/` before starting. Without `web/dist/`, the backend runs API-only and `/` returns 404. The `/docs` route still works.

**Vite dev server says "cannot connect to backend".** Vite proxies `/api` and `/ws` to `localhost:8000`. Start `agentlabx serve` first, then `npm run dev`.

**`npm install` fails on React 19 peer-dep.** Run `npm install --legacy-peer-deps`. The AntD v5 compatibility patch is already wired in (`@ant-design/v5-patch-for-react-19`), so React 19 is supported.

**Tests: `uv run pytest` hangs.** Make sure no stray uvicorn is holding `data/agentlabx.db`. Kill lingering Python processes on Windows with `taskkill //F //IM python.exe`.

## Where to look next

- Platform spec — [`docs/superpowers/specs/2026-04-12-agentlabx-platform-design.md`](superpowers/specs/2026-04-12-agentlabx-platform-design.md)
- Implementation plans — [`docs/superpowers/plans/`](superpowers/plans/)
- Backend tests — [`tests/`](../tests/) (426 tests, pytest)
- Frontend tests — [`web/tests/`](../web/tests/) (102 tests, vitest)
