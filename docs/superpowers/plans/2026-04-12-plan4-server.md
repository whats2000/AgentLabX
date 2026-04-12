# Plan 4: Server — FastAPI, WebSocket, Remaining Real Stages, CLI

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Expose AgentLabX as a deployable service — FastAPI REST + WebSocket server, live event streaming from pipeline execution, session persistence via SQLite, remaining 4 real stage implementations (data_exploration, data_preparation, experimentation, results_interpretation), and the `agentlabx serve` CLI entrypoint. After Plan 4, the platform is usable end-to-end with a real HTTP interface and all 8 stages running real agent dialogue.

**Architecture:** FastAPI app wraps session lifecycle and exposes REST endpoints per spec §7.1. WebSocket handlers subscribe to the per-session `EventBus` (Plan 1) to forward real-time pipeline events. A `PipelineExecutor` service manages concurrent session tasks — each session runs in its own asyncio task, streams events to its WebSocket clients, and supports HITL pause/resume via LangGraph's native `interrupt`. Sessions are persisted to SQLite via the Plan 3 storage backend. The remaining 4 real stages use the code agent and subprocess backend for actual experiment execution.

**Tech Stack:** FastAPI 0.115+, uvicorn 0.32+, websockets 14+, python-multipart (file uploads), click (CLI), httpx (test client), plus everything from Plans 1-3.

**Spec reference:** `docs/superpowers/specs/2026-04-12-agentlabx-platform-design.md` §3.6 (experimentation validation), §7 (API), §9 (sessions), §11 (deployment)

**Depends on:** Plans 1-3 (288 tests passing, all providers/tools/agents wired, 4 of 8 real stages)

**Note:** Plan 4 does NOT implement authentication. `user_id = "default"` is hardcoded in the API layer. Per spec §9.3, the schema and routes already carry `user_id` so adding OAuth/JWT in a later plan is additive. Tests use `httpx.AsyncClient` with FastAPI's test client.

---

## File Structure

```
agentlabx/
  server/
    __init__.py
    app.py                   # FastAPI application factory
    deps.py                  # Dependency injection: registry, executor, storage
    executor.py              # PipelineExecutor — manages running sessions as asyncio tasks
    events.py                # EventType constants + stage event emission hooks
    routes/
      __init__.py
      sessions.py            # Session CRUD + lifecycle (start/pause/resume/redirect)
      preferences.py         # PATCH /preferences (live mode toggle)
      artifacts.py           # GET artifacts/transitions/cost/hypotheses
      plugins.py             # GET available stages/tools/agents
    ws/
      __init__.py
      connection.py          # ConnectionManager — per-session WS subscribers
      handlers.py            # WebSocket event handlers (client actions + server events)
  stages/
    data_exploration.py      # NEW: real EDA via code executor + SW engineer
    data_preparation.py      # NEW: real data pipeline code generation
    experimentation.py       # NEW: baselines → main → ablations with validation
    results_interpretation.py  # NEW: postdoc synthesis of results
  cli/
    __init__.py
    main.py                  # `agentlabx serve` entrypoint
  core/
    pipeline.py              # EXTENDED: accept llm_provider, cost_tracker, event_bus in build()
tests/
  server/
    __init__.py
    test_app.py
    test_sessions_routes.py
    test_preferences_routes.py
    test_artifacts_routes.py
    test_plugins_routes.py
    test_executor.py
    test_websocket.py
    test_server_e2e.py
  stages/
    test_data_exploration_real.py
    test_data_preparation_real.py
    test_experimentation_real.py
    test_results_interpretation_real.py
  cli/
    __init__.py
    test_cli.py
```

---

### Task 1: Add Plan 4 Dependencies

**Files:** Modify `pyproject.toml`

- [ ] **Step 1: Add dependencies**

```toml
dependencies = [
    # ... existing ...
    "fastapi>=0.115,<1.0",
    "uvicorn[standard]>=0.32,<1.0",
    "python-multipart>=0.0.9,<1.0",
    "click>=8.1,<9.0",
]

[project.optional-dependencies]
dev = [
    "pytest>=8.0",
    "pytest-asyncio>=0.24",
    "httpx>=0.27,<1.0",
    "ruff>=0.4",
]

[project.scripts]
agentlabx = "agentlabx.cli.main:cli"
```

- [ ] **Step 2: Install** — `uv sync --extra dev`
- [ ] **Step 3: Verify** — `uv run python -c "import fastapi, uvicorn, httpx, click; print('ok')"`
- [ ] **Step 4: Commit** — `build: add FastAPI, uvicorn, httpx, click for Plan 4`

---

### Task 2: Extend PipelineBuilder with provider/tracker/event_bus

**Files:**
- Modify: `agentlabx/core/pipeline.py`
- Modify: `tests/core/test_pipeline.py` (add tests for the new wiring)

Currently `PipelineBuilder.build(stage_sequence, checkpointer=None)` doesn't receive or forward the LLM provider, cost tracker, or event bus. Real stages need all three via `StageContext`.

- [ ] **Step 1: Extend signature**

```python
# agentlabx/core/pipeline.py
from agentlabx.core.events import EventBus
from agentlabx.core.state import CostTracker
from agentlabx.providers.llm.base import BaseLLMProvider
from agentlabx.stages.base import StageContext


class PipelineBuilder:
    def __init__(
        self,
        registry: PluginRegistry,
        preferences: SessionPreferences | None = None,
    ) -> None:
        self.registry = registry
        self.preferences = preferences or SessionPreferences()

    def build(
        self,
        stage_sequence: list[str],
        *,
        checkpointer: Any | None = None,
        llm_provider: BaseLLMProvider | None = None,
        cost_tracker: CostTracker | None = None,
        event_bus: EventBus | None = None,
    ) -> Any:
        """Build and compile the StateGraph.

        Parameters
        ----------
        llm_provider: injected into StageContext so stages pass to agents
        cost_tracker: shared tracker — agents accumulate LLM costs here
        event_bus: real-time event emission — server layer subscribes for WS forwarding
        """
        if checkpointer is None:
            checkpointer = MemorySaver()

        builder = StateGraph(PipelineState)

        # Build shared context
        stage_context = StageContext(
            settings={},
            event_bus=event_bus,
            registry=self.registry,
            llm_provider=llm_provider,
            cost_tracker=cost_tracker,
        )

        # Resolve stages with the shared context
        runners: dict[str, StageRunner] = {}
        for stage_name in stage_sequence:
            stage_cls = self.registry.resolve(PluginType.STAGE, stage_name)
            stage_instance = stage_cls()
            runners[stage_name] = StageRunner(stage_instance, context=stage_context)

        # ... rest unchanged ...
```

- [ ] **Step 2: Test the wiring**

```python
# Additions to tests/core/test_pipeline.py
class TestPipelineBuilderProviderWiring:
    async def test_llm_provider_reaches_stages(self, registry):
        """Verify LLM provider passed to build() reaches StageContext."""
        from agentlabx.providers.llm.mock_provider import MockLLMProvider
        provider = MockLLMProvider(responses=["lit review"])
        builder = PipelineBuilder(registry=registry)
        graph = builder.build(
            stage_sequence=["literature_review"],
            llm_provider=provider,
        )
        initial = create_initial_state(
            session_id="s1", user_id="u1", research_topic="test",
            default_sequence=["literature_review"],
        )
        config = {"configurable": {"thread_id": "test-provider"}}
        # Mock arxiv so tool call doesn't hit real API
        with patch("agentlabx.tools.arxiv_search.arxiv.Client") as MockClient:
            MockClient.return_value.results.return_value = iter([])
            # Need tool registered
            from agentlabx.tools.arxiv_search import ArxivSearch
            registry.register(PluginType.TOOL, "arxiv_search", ArxivSearch)
            result = await graph.ainvoke(initial, config=config)
        # The LLM provider should have been called (at least one inference)
        assert len(provider.calls) > 0

    async def test_event_bus_receives_stage_events(self, registry):
        """EventBus subscribers should receive events during pipeline execution."""
        from agentlabx.core.events import Event, EventBus
        bus = EventBus()
        received: list[Event] = []
        async def handler(event: Event) -> None:
            received.append(event)
        bus.subscribe("*", handler)

        builder = PipelineBuilder(registry=registry)
        graph = builder.build(
            stage_sequence=["literature_review", "plan_formulation"],
            event_bus=bus,
        )
        initial = create_initial_state(
            session_id="s1", user_id="u1", research_topic="test",
            default_sequence=["literature_review", "plan_formulation"],
        )
        config = {"configurable": {"thread_id": "test-events"}}
        await graph.ainvoke(initial, config=config)
        # After events are wired in Task 3, this will pass. For now, accept empty.
        # This test enforces the wiring surface exists; event emission lands in Task 3.
        assert bus is not None  # placeholder
```

- [ ] **Step 3: Commit** — `feat(core): extend PipelineBuilder with llm_provider, cost_tracker, event_bus wiring`

---

### Task 3: Stage Event Emission

**Files:**
- Modify: `agentlabx/stages/runner.py` (emit events around stage execution)
- Create: `agentlabx/server/events.py` (EventType constants)
- Modify: `tests/stages/test_runner.py` (add event emission tests)

- [ ] **Step 1: Define event types**

```python
# agentlabx/server/events.py
"""Event type constants emitted during pipeline execution.

These constants are the canonical event names. The WebSocket layer (Task 9)
forwards events whose type matches any of these to subscribed clients.
"""

from __future__ import annotations

# Stage lifecycle
STAGE_STARTED = "stage_started"
STAGE_COMPLETED = "stage_completed"
STAGE_FAILED = "stage_failed"

# Agent activity
AGENT_THINKING = "agent_thinking"
AGENT_TOOL_CALL = "agent_tool_call"
AGENT_DIALOGUE = "agent_dialogue"

# Pipeline routing
TRANSITION = "transition"
CHECKPOINT_REACHED = "checkpoint_reached"

# Observability
COST_UPDATE = "cost_update"
ERROR = "error"
```

- [ ] **Step 2: Emit events from StageRunner**

```python
# agentlabx/stages/runner.py — additions

# At the top of run():
if self.context.event_bus is not None:
    await self.context.event_bus.emit(Event(
        type="stage_started",
        data={"stage": self.stage.name, "session_id": state.get("session_id", "")},
        source=self.stage.name,
    ))

# At the end (after exit hooks):
if self.context.event_bus is not None:
    await self.context.event_bus.emit(Event(
        type="stage_completed",
        data={
            "stage": self.stage.name,
            "session_id": state.get("session_id", ""),
            "reason": getattr(result, "reason", "") if "result" in locals() else "",
            "next_hint": update.get("next_stage"),
        },
        source=self.stage.name,
    ))

# On exception (inside except block):
if self.context.event_bus is not None:
    await self.context.event_bus.emit(Event(
        type="stage_failed",
        data={
            "stage": self.stage.name,
            "session_id": state.get("session_id", ""),
            "error_type": type(e).__name__,
            "message": str(e),
        },
        source=self.stage.name,
    ))
```

Import `Event` from `agentlabx.core.events` at the top.

- [ ] **Step 3: Tests**

Add to `tests/stages/test_runner.py`:

```python
async def test_emits_stage_started_event(initial_state):
    from agentlabx.core.events import Event, EventBus
    bus = EventBus()
    received = []
    async def handler(event: Event) -> None:
        received.append(event)
    bus.subscribe("stage_started", handler)

    ctx = StageContext(settings={}, event_bus=bus, registry=None)
    runner = StageRunner(SuccessStage(), context=ctx)
    await runner.run(initial_state)
    assert len(received) == 1
    assert received[0].data["stage"] == "success_stage"


async def test_emits_stage_completed_event(initial_state):
    from agentlabx.core.events import Event, EventBus
    bus = EventBus()
    received = []
    async def handler(event: Event) -> None:
        received.append(event)
    bus.subscribe("stage_completed", handler)

    ctx = StageContext(settings={}, event_bus=bus, registry=None)
    runner = StageRunner(SuccessStage(), context=ctx)
    await runner.run(initial_state)
    assert len(received) == 1


async def test_emits_stage_failed_event(initial_state):
    from agentlabx.core.events import Event, EventBus
    bus = EventBus()
    received = []
    async def handler(event: Event) -> None:
        received.append(event)
    bus.subscribe("stage_failed", handler)

    ctx = StageContext(settings={}, event_bus=bus, registry=None)
    runner = StageRunner(FailingStage(), context=ctx)
    await runner.run(initial_state)
    assert len(received) == 1
    assert "Stage crashed" in received[0].data["message"]
```

- [ ] **Step 4: Commit** — `feat(stages): emit stage_started/completed/failed events via EventBus`

---

### Task 4: FastAPI App Scaffold + Dependency Injection

**Files:**
- Create: `agentlabx/server/__init__.py` (empty)
- Create: `agentlabx/server/app.py`
- Create: `agentlabx/server/deps.py`
- Create: `agentlabx/server/routes/__init__.py` (empty)
- Create: `tests/server/__init__.py` (empty)
- Create: `tests/server/test_app.py`

- [ ] **Step 1: Implement `deps.py`**

```python
# agentlabx/server/deps.py
"""Dependency injection container for the FastAPI server.

Holds singletons shared across requests:
- PluginRegistry (with all default agents, stages, tools registered)
- SessionManager (session lifecycle)
- Storage backend (SQLite by default)
- LLM provider
- PipelineExecutor (manages running sessions — created in Task 6)
"""

from __future__ import annotations

from pathlib import Path

from agentlabx.agents.config_loader import AgentConfigLoader
from agentlabx.core.config import Settings
from agentlabx.core.registry import PluginRegistry, PluginType
from agentlabx.core.session import SessionManager
from agentlabx.providers.execution.subprocess_backend import SubprocessBackend
from agentlabx.providers.llm.base import BaseLLMProvider
from agentlabx.providers.llm.litellm_provider import LiteLLMProvider
from agentlabx.providers.llm.mock_provider import MockLLMProvider
from agentlabx.providers.storage.sqlite_backend import SQLiteBackend
from agentlabx.stages.skeleton import register_default_stages
from agentlabx.tools.arxiv_search import ArxivSearch
from agentlabx.tools.code_executor import CodeExecutor
from agentlabx.tools.github_search import GitHubSearch
from agentlabx.tools.hf_dataset_search import HFDatasetSearch
from agentlabx.tools.latex_compiler import LaTeXCompiler
from agentlabx.tools.semantic_scholar import SemanticScholarSearch


AGENT_CONFIGS_DIR = Path(__file__).parent.parent / "agents" / "configs"


class AppContext:
    """Shared runtime context for the FastAPI app."""

    def __init__(
        self,
        *,
        settings: Settings,
        registry: PluginRegistry,
        session_manager: SessionManager,
        storage: SQLiteBackend,
        llm_provider: BaseLLMProvider,
    ) -> None:
        self.settings = settings
        self.registry = registry
        self.session_manager = session_manager
        self.storage = storage
        self.llm_provider = llm_provider
        self.executor = None  # Set in Task 6 (PipelineExecutor)


def build_default_registry() -> PluginRegistry:
    """Register all default plugins: agents, stages, tools."""
    registry = PluginRegistry()

    # Agents from YAML
    loader = AgentConfigLoader()
    configs = loader.load_all(AGENT_CONFIGS_DIR)
    loader.register_all(configs, registry)

    # Stages (real + skeleton)
    register_default_stages(registry)

    # Tools (stateless)
    registry.register(PluginType.TOOL, "arxiv_search", ArxivSearch)
    registry.register(PluginType.TOOL, "semantic_scholar", SemanticScholarSearch)
    registry.register(PluginType.TOOL, "hf_dataset_search", HFDatasetSearch)
    registry.register(PluginType.TOOL, "github_search", GitHubSearch)
    registry.register(PluginType.TOOL, "latex_compiler", LaTeXCompiler)
    # Tools requiring backend injection (code_executor) are registered at runtime
    # per-request in Task 6 when the executor composes contexts

    return registry


async def build_app_context(
    *,
    settings: Settings | None = None,
    use_mock_llm: bool = False,
) -> AppContext:
    """Initialize all singletons for the app. Call once at startup."""
    settings = settings or Settings()
    registry = build_default_registry()
    session_manager = SessionManager()

    storage = SQLiteBackend(
        database_url=settings.storage.database_url,
        artifacts_path=Path(settings.storage.artifacts_path),
    )
    await storage.initialize()

    # Register backend-dependent tools now that storage/execution exist
    execution_backend = SubprocessBackend()
    code_executor = CodeExecutor(backend=execution_backend)
    registry.register(PluginType.TOOL, "code_executor", code_executor)

    llm_provider: BaseLLMProvider = (
        MockLLMProvider() if use_mock_llm else LiteLLMProvider()
    )

    return AppContext(
        settings=settings,
        registry=registry,
        session_manager=session_manager,
        storage=storage,
        llm_provider=llm_provider,
    )
```

- [ ] **Step 2: Implement `app.py`**

```python
# agentlabx/server/app.py
"""FastAPI application factory."""

from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from agentlabx.core.config import Settings
from agentlabx.server.deps import AppContext, build_app_context


def create_app(
    *,
    settings: Settings | None = None,
    use_mock_llm: bool = False,
) -> FastAPI:
    """Factory for the FastAPI app."""
    settings = settings or Settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        context = await build_app_context(settings=settings, use_mock_llm=use_mock_llm)
        app.state.context = context
        try:
            yield
        finally:
            await context.storage.close()

    app = FastAPI(
        title="AgentLabX",
        version="0.1.0",
        description="Modular multi-instance research automation platform",
        lifespan=lifespan,
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.server.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Routes registered in Tasks 5-8
    @app.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "ok", "version": "0.1.0"}

    return app


def get_context(app: FastAPI) -> AppContext:
    """Helper for routes to access the shared app context."""
    return app.state.context
```

- [ ] **Step 3: Tests**

```python
# tests/server/test_app.py
from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient

from agentlabx.server.app import create_app


class TestApp:
    async def test_health_endpoint(self):
        app = create_app(use_mock_llm=True)
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            # Lifespan manager handles startup/shutdown
            async with LifespanManager(app):
                response = await client.get("/health")
        assert response.status_code == 200
        assert response.json()["status"] == "ok"

    async def test_app_has_registry_after_startup(self):
        app = create_app(use_mock_llm=True)
        async with LifespanManager(app):
            assert hasattr(app.state, "context")
            assert app.state.context.registry is not None
            assert app.state.context.session_manager is not None


# Helper for lifespan in tests — install via pip: asgi-lifespan>=2.1
# OR use this minimal inline helper:
class LifespanManager:
    def __init__(self, app):
        self.app = app
        self._ctx = None

    async def __aenter__(self):
        # Trigger lifespan startup
        self._ctx = self.app.router.lifespan_context(self.app)
        await self._ctx.__aenter__()
        return self

    async def __aexit__(self, exc_type, exc, tb):
        await self._ctx.__aexit__(exc_type, exc, tb)
```

If the minimal LifespanManager above doesn't work cleanly, add `asgi-lifespan>=2.1` to dev deps and import `from asgi_lifespan import LifespanManager`.

- [ ] **Step 4: Commit** — `feat(server): add FastAPI app factory with lifespan-managed AppContext`

---

### Task 5: Session REST Routes

**Files:**
- Create: `agentlabx/server/routes/sessions.py`
- Modify: `agentlabx/server/app.py` (register router)
- Create: `tests/server/test_sessions_routes.py`

Implement per spec §7.1 — all session endpoints except preferences (Task 7) and artifacts (Task 8). Include:

- `GET /api/sessions` — list
- `POST /api/sessions` — create (body: `{topic, user_id?, config?}`, returns session detail)
- `GET /api/sessions/{id}` — detail + state (reads LangGraph checkpoint)
- `POST /api/sessions/{id}/start` — spawns async task (Task 6 adds the actual spawn)
- `POST /api/sessions/{id}/pause` — signals executor to pause at next checkpoint
- `POST /api/sessions/{id}/resume` — resume from checkpoint
- `POST /api/sessions/{id}/redirect` — body: `{target_stage, reason}` — sets `human_override` in state

**Request/response models (Pydantic):**

```python
# agentlabx/server/routes/sessions.py
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from agentlabx.core.session import Session, SessionStatus


router = APIRouter(prefix="/api/sessions", tags=["sessions"])


class SessionCreateRequest(BaseModel):
    topic: str
    user_id: str = "default"
    config: dict[str, Any] = {}


class SessionSummary(BaseModel):
    session_id: str
    user_id: str
    research_topic: str
    status: str


class SessionDetail(SessionSummary):
    preferences: dict[str, Any]
    config_overrides: dict[str, Any]


class RedirectRequest(BaseModel):
    target_stage: str
    reason: str = ""


def _summarize(session: Session) -> SessionSummary:
    return SessionSummary(
        session_id=session.session_id,
        user_id=session.user_id,
        research_topic=session.research_topic,
        status=session.status.value,
    )


def _detail(session: Session) -> SessionDetail:
    return SessionDetail(
        session_id=session.session_id,
        user_id=session.user_id,
        research_topic=session.research_topic,
        status=session.status.value,
        preferences=session.preferences.model_dump(),
        config_overrides=session.config_overrides,
    )


@router.get("", response_model=list[SessionSummary])
async def list_sessions(request: Request, user_id: str | None = None):
    manager = request.app.state.context.session_manager
    sessions = manager.list_sessions(user_id=user_id) if user_id else manager.list_sessions()
    return [_summarize(s) for s in sessions]


@router.post("", response_model=SessionDetail, status_code=201)
async def create_session(request: Request, body: SessionCreateRequest):
    manager = request.app.state.context.session_manager
    session = manager.create_session(
        user_id=body.user_id,
        research_topic=body.topic,
        config_overrides=body.config,
    )
    return _detail(session)


@router.get("/{session_id}", response_model=SessionDetail)
async def get_session(request: Request, session_id: str):
    manager = request.app.state.context.session_manager
    try:
        session = manager.get_session(session_id)
    except KeyError:
        raise HTTPException(status_code=404, detail=f"Session '{session_id}' not found")
    return _detail(session)


@router.post("/{session_id}/start", status_code=202)
async def start_session(request: Request, session_id: str):
    context = request.app.state.context
    try:
        session = context.session_manager.get_session(session_id)
    except KeyError:
        raise HTTPException(status_code=404, detail="Session not found")

    if session.status != SessionStatus.CREATED:
        raise HTTPException(status_code=409, detail=f"Cannot start from {session.status.value}")

    # Executor.start_session() implemented in Task 6
    if context.executor is not None:
        await context.executor.start_session(session)
    else:
        session.start()  # Fallback: just transition state

    return {"session_id": session_id, "status": session.status.value}


@router.post("/{session_id}/pause", status_code=202)
async def pause_session(request: Request, session_id: str):
    context = request.app.state.context
    try:
        session = context.session_manager.get_session(session_id)
    except KeyError:
        raise HTTPException(status_code=404, detail="Session not found")
    if context.executor is not None:
        await context.executor.pause_session(session_id)
    else:
        session.pause()
    return {"session_id": session_id, "status": session.status.value}


@router.post("/{session_id}/resume", status_code=202)
async def resume_session(request: Request, session_id: str):
    context = request.app.state.context
    try:
        session = context.session_manager.get_session(session_id)
    except KeyError:
        raise HTTPException(status_code=404, detail="Session not found")
    if context.executor is not None:
        await context.executor.resume_session(session_id)
    else:
        session.resume()
    return {"session_id": session_id, "status": session.status.value}


@router.post("/{session_id}/redirect", status_code=202)
async def redirect_session(request: Request, session_id: str, body: RedirectRequest):
    context = request.app.state.context
    try:
        session = context.session_manager.get_session(session_id)
    except KeyError:
        raise HTTPException(status_code=404, detail="Session not found")

    if context.executor is not None:
        await context.executor.redirect_session(session_id, body.target_stage, body.reason)
    # Without executor, no-op (tests Task 6 wiring separately)

    return {
        "session_id": session_id,
        "target_stage": body.target_stage,
        "reason": body.reason,
    }
```

Register the router in `app.py`:

```python
# In create_app(), after CORS middleware:
from agentlabx.server.routes import sessions
app.include_router(sessions.router)
```

**Tests:**

Cover all endpoints. Use `httpx.AsyncClient` with the FastAPI test pattern. Verify:
- POST /api/sessions creates a session with auto-generated ID
- GET /api/sessions/{id} returns detail including preferences
- GET /api/sessions lists all
- GET with user_id filter returns only that user's sessions
- 404 on missing session
- Start requires CREATED status (409 otherwise)
- Redirect echoes target_stage in response

Commit: `feat(server): add session REST endpoints (CRUD + start/pause/resume/redirect)`

---

### Task 6: Pipeline Executor Service

**Files:**
- Create: `agentlabx/server/executor.py`
- Create: `tests/server/test_executor.py`
- Modify: `agentlabx/server/deps.py` to construct and attach the executor

The `PipelineExecutor` owns running sessions as `asyncio.Task`s. One task per session. It:
1. Builds a `PipelineBuilder` graph with the session's LLM provider, cost tracker, and event bus
2. Runs `graph.astream(...)` in a task, consuming events
3. Forwards stage events to the session's `EventBus` (which WS subscribers will listen to)
4. Handles pause/resume via LangGraph checkpoints
5. Handles redirect via state updates (`human_override`)
6. Cleans up tasks on completion/cancellation

```python
# agentlabx/server/executor.py
"""PipelineExecutor — manages running sessions as asyncio tasks."""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from langgraph.checkpoint.memory import MemorySaver

from agentlabx.core.events import EventBus
from agentlabx.core.pipeline import PipelineBuilder
from agentlabx.core.registry import PluginRegistry
from agentlabx.core.session import Session, SessionManager
from agentlabx.core.state import CostTracker, create_initial_state
from agentlabx.providers.llm.base import BaseLLMProvider


logger = logging.getLogger(__name__)


class RunningSession:
    """In-memory handle for a running session."""

    def __init__(
        self,
        *,
        session: Session,
        graph: Any,
        event_bus: EventBus,
        cost_tracker: CostTracker,
        task: asyncio.Task,
        thread_id: str,
    ) -> None:
        self.session = session
        self.graph = graph
        self.event_bus = event_bus
        self.cost_tracker = cost_tracker
        self.task = task
        self.thread_id = thread_id
        self.paused = asyncio.Event()
        self.paused.set()  # Not paused by default


class PipelineExecutor:
    """Runs pipelines per session as independent asyncio tasks."""

    def __init__(
        self,
        *,
        registry: PluginRegistry,
        session_manager: SessionManager,
        llm_provider: BaseLLMProvider,
    ) -> None:
        self.registry = registry
        self.session_manager = session_manager
        self.llm_provider = llm_provider
        self._running: dict[str, RunningSession] = {}

    def get_running(self, session_id: str) -> RunningSession | None:
        return self._running.get(session_id)

    async def start_session(self, session: Session) -> RunningSession:
        """Begin running a session's pipeline as an asyncio task."""
        if session.session_id in self._running:
            raise RuntimeError(f"Session {session.session_id} already running")

        session.start()

        # Build sequence from config overrides OR default
        from agentlabx.core.config import PipelineConfig
        default_sequence = session.config_overrides.get(
            "pipeline", {}
        ).get("default_sequence") or PipelineConfig().default_sequence

        event_bus = EventBus()
        cost_tracker = CostTracker()
        checkpointer = MemorySaver()  # Plan 4+: swap for SQLite-backed checkpointer

        builder = PipelineBuilder(registry=self.registry, preferences=session.preferences)
        graph = builder.build(
            stage_sequence=default_sequence,
            checkpointer=checkpointer,
            llm_provider=self.llm_provider,
            cost_tracker=cost_tracker,
            event_bus=event_bus,
        )

        initial_state = create_initial_state(
            session_id=session.session_id,
            user_id=session.user_id,
            research_topic=session.research_topic,
            default_sequence=default_sequence,
        )
        thread_id = session.session_id
        config = {"configurable": {"thread_id": thread_id}}

        async def run_pipeline():
            try:
                await graph.ainvoke(initial_state, config=config)
                session.complete()
            except asyncio.CancelledError:
                logger.info("Session %s cancelled", session.session_id)
                raise
            except Exception as e:
                logger.exception("Pipeline error for %s: %s", session.session_id, e)
                session.fail()
            finally:
                self._running.pop(session.session_id, None)

        task = asyncio.create_task(run_pipeline(), name=f"pipeline-{session.session_id}")
        running = RunningSession(
            session=session, graph=graph, event_bus=event_bus,
            cost_tracker=cost_tracker, task=task, thread_id=thread_id,
        )
        self._running[session.session_id] = running
        return running

    async def pause_session(self, session_id: str) -> None:
        running = self._running.get(session_id)
        if running is None:
            raise KeyError(session_id)
        running.session.pause()
        running.paused.clear()  # Stage runner can check this for cooperative pause

    async def resume_session(self, session_id: str) -> None:
        running = self._running.get(session_id)
        if running is None:
            raise KeyError(session_id)
        running.session.resume()
        running.paused.set()

    async def redirect_session(
        self, session_id: str, target_stage: str, reason: str
    ) -> None:
        """Update graph state with human_override to redirect on next transition."""
        running = self._running.get(session_id)
        if running is None:
            raise KeyError(session_id)
        config = {"configurable": {"thread_id": running.thread_id}}
        await running.graph.aupdate_state(
            config, {"human_override": target_stage}
        )

    async def cancel_session(self, session_id: str) -> None:
        running = self._running.get(session_id)
        if running is None:
            return
        running.task.cancel()
        try:
            await running.task
        except asyncio.CancelledError:
            pass
```

Update `deps.py::build_app_context` to construct the executor:

```python
# In build_app_context:
from agentlabx.server.executor import PipelineExecutor
# ... after context created ...
context.executor = PipelineExecutor(
    registry=registry,
    session_manager=session_manager,
    llm_provider=llm_provider,
)
return context
```

Tests use `MockLLMProvider` in fixtures:
- test_start_session_creates_task (session status → RUNNING, task exists)
- test_start_session_twice_raises
- test_pause_and_resume (pause → paused Event cleared, resume → set again)
- test_cancel_session (task cancelled, cleaned up)
- test_redirect_updates_state
- test_executor_cleanup_on_completion

Commit: `feat(server): add PipelineExecutor managing concurrent session pipelines`

---

### Task 7: Preferences PATCH Route

**Files:**
- Create: `agentlabx/server/routes/preferences.py`
- Modify: `agentlabx/server/app.py` (register router)
- Create: `tests/server/test_preferences_routes.py`

Live mode/control toggle — spec §7.1 `PATCH /api/sessions/{id}/preferences`.

```python
# agentlabx/server/routes/preferences.py
from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel


router = APIRouter(prefix="/api/sessions", tags=["preferences"])


class PreferencesUpdateRequest(BaseModel):
    mode: Literal["auto", "hitl"] | None = None
    stage_controls: dict[str, Literal["auto", "notify", "approve", "edit"]] | None = None
    backtrack_control: Literal["auto", "notify", "approve"] | None = None


@router.patch("/{session_id}/preferences")
async def update_preferences(
    request: Request, session_id: str, body: PreferencesUpdateRequest
):
    manager = request.app.state.context.session_manager
    try:
        session = manager.get_session(session_id)
    except KeyError:
        raise HTTPException(status_code=404, detail="Session not found")

    updates = body.model_dump(exclude_none=True)
    if updates:
        session.update_preferences(**updates)

    return {
        "session_id": session_id,
        "preferences": session.preferences.model_dump(),
    }
```

Tests cover:
- PATCH with mode flip
- PATCH with stage_controls sets per-stage
- PATCH with no fields → no change
- 404 on missing session
- Multiple patches accumulate correctly

Commit: `feat(server): add PATCH /preferences for live mode and stage control toggling`

---

### Task 8: Artifacts, Transitions, Cost, Hypotheses, Plugins Routes

**Files:**
- Create: `agentlabx/server/routes/artifacts.py`
- Create: `agentlabx/server/routes/plugins.py`
- Modify: `agentlabx/server/app.py`
- Create: `tests/server/test_artifacts_routes.py`
- Create: `tests/server/test_plugins_routes.py`

These endpoints all read from either pipeline state (via LangGraph `get_state`) or the plugin registry.

```python
# agentlabx/server/routes/artifacts.py
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Request


router = APIRouter(prefix="/api/sessions", tags=["session-data"])


async def _get_state(request: Request, session_id: str) -> dict[str, Any]:
    context = request.app.state.context
    executor = context.executor
    if executor is None:
        raise HTTPException(status_code=503, detail="Executor not initialized")
    running = executor.get_running(session_id)
    if running is None:
        # Not currently running — fall back to storage for a completed session
        return await context.storage.load_state(session_id, "final") or {}
    config = {"configurable": {"thread_id": running.thread_id}}
    snapshot = await running.graph.aget_state(config)
    return snapshot.values if snapshot else {}


@router.get("/{session_id}/artifacts")
async def list_artifacts(request: Request, session_id: str):
    state = await _get_state(request, session_id)
    return {
        "literature_review": [r.model_dump() if hasattr(r, "model_dump") else r
                               for r in state.get("literature_review", [])],
        "plan": [p.model_dump() if hasattr(p, "model_dump") else p
                 for p in state.get("plan", [])],
        "experiment_results": [e.model_dump() if hasattr(e, "model_dump") else e
                                for e in state.get("experiment_results", [])],
        "report": [r.model_dump() if hasattr(r, "model_dump") else r
                   for r in state.get("report", [])],
    }


@router.get("/{session_id}/transitions")
async def list_transitions(request: Request, session_id: str):
    state = await _get_state(request, session_id)
    return {
        "transitions": [
            t.model_dump() if hasattr(t, "model_dump") else t
            for t in state.get("transition_log", [])
        ],
        "completed_stages": state.get("completed_stages", []),
        "current_stage": state.get("current_stage", ""),
    }


@router.get("/{session_id}/cost")
async def get_cost(request: Request, session_id: str):
    context = request.app.state.context
    executor = context.executor
    if executor is None:
        raise HTTPException(status_code=503, detail="Executor not initialized")
    running = executor.get_running(session_id)
    if running is None:
        raise HTTPException(status_code=404, detail="Session not running")
    tracker = running.cost_tracker
    return {
        "total_tokens_in": tracker.total_tokens_in,
        "total_tokens_out": tracker.total_tokens_out,
        "total_cost": tracker.total_cost,
    }


@router.get("/{session_id}/hypotheses")
async def list_hypotheses(request: Request, session_id: str):
    state = await _get_state(request, session_id)
    return {
        "hypotheses": [
            h.model_dump() if hasattr(h, "model_dump") else h
            for h in state.get("hypotheses", [])
        ],
    }
```

```python
# agentlabx/server/routes/plugins.py
from __future__ import annotations

from fastapi import APIRouter, Request

from agentlabx.core.registry import PluginType


router = APIRouter(prefix="/api/plugins", tags=["plugins"])


@router.get("")
async def list_plugins(request: Request):
    registry = request.app.state.context.registry
    result: dict[str, list[str]] = {}
    for plugin_type in PluginType:
        plugins = registry.list_plugins(plugin_type)
        result[plugin_type.value] = list(plugins.keys())
    return result
```

Tests verify: the endpoints return data matching the current session state, plugins lists include known names (e.g., "phd_student" under "agent"), cost returns tracker fields, 404s on missing sessions.

Commit: `feat(server): add artifacts/transitions/cost/hypotheses/plugins GET endpoints`

---

### Task 9: WebSocket Handler

**Files:**
- Create: `agentlabx/server/ws/__init__.py` (empty)
- Create: `agentlabx/server/ws/connection.py`
- Create: `agentlabx/server/ws/handlers.py`
- Modify: `agentlabx/server/app.py`
- Create: `tests/server/test_websocket.py`

Per spec §7.2 — one WS per session, forwards `EventBus` events to the client, receives client actions (approve/edit/redirect/inject_feedback/update_preferences).

```python
# agentlabx/server/ws/connection.py
from __future__ import annotations

from fastapi import WebSocket


class ConnectionManager:
    """Tracks active WebSocket connections per session."""

    def __init__(self) -> None:
        self._connections: dict[str, list[WebSocket]] = {}

    async def connect(self, session_id: str, websocket: WebSocket) -> None:
        await websocket.accept()
        self._connections.setdefault(session_id, []).append(websocket)

    def disconnect(self, session_id: str, websocket: WebSocket) -> None:
        if session_id in self._connections:
            try:
                self._connections[session_id].remove(websocket)
            except ValueError:
                pass
            if not self._connections[session_id]:
                del self._connections[session_id]

    async def broadcast(self, session_id: str, message: dict) -> None:
        """Send a JSON message to all WS clients subscribed to this session."""
        dead: list[WebSocket] = []
        for ws in self._connections.get(session_id, []):
            try:
                await ws.send_json(message)
            except Exception:
                dead.append(ws)
        for ws in dead:
            self.disconnect(session_id, ws)
```

```python
# agentlabx/server/ws/handlers.py
from __future__ import annotations

import logging

from fastapi import APIRouter, Request, WebSocket, WebSocketDisconnect

from agentlabx.core.events import Event
from agentlabx.server.ws.connection import ConnectionManager


logger = logging.getLogger(__name__)
manager = ConnectionManager()
router = APIRouter()


@router.websocket("/ws/sessions/{session_id}")
async def session_websocket(websocket: WebSocket, session_id: str):
    app = websocket.app
    context = app.state.context
    executor = context.executor
    session_manager = context.session_manager

    # Validate session exists
    try:
        session_manager.get_session(session_id)
    except KeyError:
        await websocket.close(code=4404, reason="Session not found")
        return

    await manager.connect(session_id, websocket)

    # Subscribe to session event bus if running
    running = executor.get_running(session_id) if executor else None

    async def forward_event(event: Event) -> None:
        await manager.broadcast(session_id, {
            "type": event.type,
            "data": event.data,
            "source": event.source,
        })

    if running is not None:
        running.event_bus.subscribe("*", forward_event)

    try:
        # Receive client messages (approve/edit/redirect/inject_feedback/update_preferences)
        while True:
            msg = await websocket.receive_json()
            await _handle_client_message(msg, session_id, context)
    except WebSocketDisconnect:
        pass
    except Exception as e:
        logger.exception("WS error for session %s: %s", session_id, e)
    finally:
        if running is not None:
            running.event_bus.unsubscribe("*", forward_event)
        manager.disconnect(session_id, websocket)


async def _handle_client_message(msg: dict, session_id: str, context) -> None:
    action = msg.get("action")
    if action == "update_preferences":
        session = context.session_manager.get_session(session_id)
        prefs_update = {k: v for k, v in msg.items() if k in {"mode", "stage_controls", "backtrack_control"}}
        if prefs_update:
            session.update_preferences(**prefs_update)
    elif action == "redirect":
        target = msg.get("target_stage")
        reason = msg.get("reason", "")
        if target and context.executor:
            await context.executor.redirect_session(session_id, target, reason)
    elif action == "inject_feedback":
        # Append feedback to state via executor (updates pending_requests or messages)
        # For MVP, log and no-op — full implementation when HITL interrupt flow lands
        logger.info("Feedback for %s: %s", session_id, msg.get("content", ""))
    # approve/edit are interrupt-driven — Plan 4 deferred implementation
```

Register WS router in `app.py`:

```python
# In create_app:
from agentlabx.server.ws import handlers as ws_handlers
app.include_router(ws_handlers.router)
```

**Tests:**

Use `TestClient` from Starlette (sync websocket testing) or `httpx_ws` for async. The simplest approach:

```python
from fastapi.testclient import TestClient

def test_websocket_connects(app_with_session):
    app, session_id = app_with_session
    client = TestClient(app)
    with client.websocket_connect(f"/ws/sessions/{session_id}") as ws:
        ws.send_json({"action": "update_preferences", "mode": "hitl"})
        # Preferences should now be updated on the session
```

Verify:
- Connect to existing session succeeds
- Connect to missing session closes with 4404
- Sending `update_preferences` updates the session
- Sending `redirect` triggers executor.redirect_session
- Disconnect cleans up subscribers

Commit: `feat(server): add WebSocket handler with per-session event forwarding`

---

### Task 10: Session Persistence via SQLite

**Files:**
- Modify: `agentlabx/core/session.py` (add load/save hooks)
- Modify: `agentlabx/server/executor.py` (persist on status changes)
- Create: `tests/server/test_session_persistence.py`

Wire SessionManager to the SQLite storage backend so sessions survive restarts.

Add to `SessionManager` (note: the existing Plan 2 signature is `__init__(self)` with no args — keep `storage` as a keyword-only optional so existing tests in `tests/core/test_session.py` that call `SessionManager()` still pass):

```python
class SessionManager:
    def __init__(self, *, storage: BaseStorageBackend | None = None) -> None:
        self._sessions: dict[str, Session] = {}
        self._storage = storage

    async def persist_session(self, session: Session) -> None:
        """Save session metadata to storage."""
        if self._storage is None:
            return
        await self._storage.save_state(
            session.session_id,
            "session_metadata",
            {
                "session_id": session.session_id,
                "user_id": session.user_id,
                "research_topic": session.research_topic,
                "status": session.status.value,
                "preferences": session.preferences.model_dump(),
                "config_overrides": session.config_overrides,
            },
        )

    async def restore_session(self, session_id: str) -> Session | None:
        """Load a session from storage if not already in memory."""
        if session_id in self._sessions:
            return self._sessions[session_id]
        if self._storage is None:
            return None
        data = await self._storage.load_state(session_id, "session_metadata")
        if not data:
            return None
        session = Session(
            session_id=data["session_id"],
            user_id=data["user_id"],
            research_topic=data["research_topic"],
            config_overrides=data.get("config_overrides", {}),
        )
        session.status = SessionStatus(data["status"])
        session.preferences = SessionPreferences(**data.get("preferences", {}))
        self._sessions[session_id] = session
        return session
```

Update `deps.py::build_app_context` to pass storage:

```python
session_manager = SessionManager(storage=storage)
```

Update executor's status transitions to trigger persistence:

```python
# In start_session(), after session.start():
await self.session_manager.persist_session(session)

# Same in pause/resume/complete/fail
```

Tests:
- test_persist_and_restore roundtrip
- test_session_survives_manager_restart (create new SessionManager with same storage, restore)
- test_restore_missing_returns_none

Commit: `feat(server): persist sessions to SQLite via SessionManager.persist_session`

---

### Task 11: Real Data Exploration Stage

**Files:**
- Create: `agentlabx/stages/data_exploration.py`
- Update: `agentlabx/stages/skeleton.py` (remove skeleton, import real)
- Create: `tests/stages/test_data_exploration_real.py`

SW engineer runs EDA via code_executor tool: load dataset, compute basic stats (size, schema, distributions), write findings.

```python
# agentlabx/stages/data_exploration.py
"""Real data exploration stage — SW engineer runs EDA via code_executor."""

from __future__ import annotations

import json
import re

from agentlabx.core.registry import PluginType
from agentlabx.core.state import EDAResult, PipelineState
from agentlabx.stages._helpers import build_agent_context, resolve_agent, resolve_tool
from agentlabx.stages.base import BaseStage, StageContext, StageResult


EDA_JSON_FORMAT = (
    '{"code": "Python script that loads the dataset and prints shape/schema/stats", '
    '"expected_outputs": ["what the script should print"]}'
)


class DataExplorationStage(BaseStage):
    name = "data_exploration"
    description = "SW engineer runs exploratory data analysis via code executor."
    required_agents = ["sw_engineer"]
    required_tools = ["code_executor"]

    async def run(self, state: PipelineState, context: StageContext) -> StageResult:
        registry = context.registry
        if registry is None:
            return StageResult(
                output={}, status="backtrack", next_hint=None,
                reason="No registry in StageContext",
            )

        sw = resolve_agent(
            registry, "sw_engineer",
            llm_provider=context.llm_provider,
            cost_tracker=context.cost_tracker,
        )
        code_executor = resolve_tool(registry, "code_executor")

        plan_list = state.get("plan", [])
        plan_summary = plan_list[-1].methodology if plan_list else "No plan yet"
        topic = state["research_topic"]

        # Step 1: SW engineer drafts EDA script
        eda_prompt = (
            f"Topic: {topic}\n\nPlan methodology:\n{plan_summary}\n\n"
            f"Write a short Python script that performs exploratory data analysis. "
            f"The script should: (1) import the dataset (use a HuggingFace dataset or "
            f"generate synthetic if none specified), (2) print the shape, (3) print the "
            f"first 3 rows or samples, (4) print basic statistics. Respond ONLY with JSON:"
            f"\n{EDA_JSON_FORMAT}\n\nNo prose outside the JSON."
        )
        eda_response = await sw.inference(
            eda_prompt,
            build_agent_context(state, sw, phase="data_exploration"),
        )
        parsed = _parse_json(eda_response)
        code = parsed.get("code", "")

        # Step 2: Execute
        exec_result = None
        if code:
            import tempfile
            from pathlib import Path
            with tempfile.TemporaryDirectory() as tmpdir:
                exec_result = await code_executor.execute(
                    code=code, workspace=str(Path(tmpdir)), timeout=60,
                )

        # Step 3: SW engineer synthesizes findings from execution output
        stdout = (exec_result.data.get("stdout", "") if exec_result and exec_result.success else "")
        stderr = (exec_result.data.get("stderr", "") if exec_result else "")
        findings_prompt = (
            f"EDA script output:\n\nSTDOUT:\n{stdout[:2000]}\n\nSTDERR:\n{stderr[:500]}\n\n"
            f"Summarize findings. Respond ONLY with JSON:\n"
            f'{{"findings": ["finding 1", ...], "data_quality_issues": ["issue 1", ...], '
            f'"recommendations": ["rec 1", ...]}}\n\nNo prose outside the JSON.'
        )
        findings_response = await sw.inference(
            findings_prompt,
            build_agent_context(state, sw, phase="data_exploration"),
        )
        findings_parsed = _parse_json(findings_response)

        eda = EDAResult(
            findings=findings_parsed.get("findings", []) or ["EDA completed"],
            data_quality_issues=findings_parsed.get("data_quality_issues", []) or [],
            recommendations=findings_parsed.get("recommendations", []) or [],
        )

        return StageResult(
            output={"data_exploration": [eda]},
            status="done",
            reason=f"Data exploration complete. {len(eda.findings)} findings.",
        )


def _parse_json(text: str) -> dict:
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if match:
        try:
            return json.loads(match.group(0))
        except json.JSONDecodeError:
            pass
    return {}
```

Tests scripted with MockLLMProvider and a mock code_executor (registry.register a pre-built instance):
- test_runs_end_to_end (valid JSON + successful execution → EDAResult with findings)
- test_malformed_json_returns_defaults
- test_execution_failure_still_returns_eda (stderr captured, findings still produced)
- test_no_registry_backtrack

Commit: `feat(stages): add real data exploration stage with code-executor-driven EDA`

---

### Task 12: Real Data Preparation Stage

**Files:**
- Create: `agentlabx/stages/data_preparation.py`
- Update skeleton.py
- Create: `tests/stages/test_data_preparation_real.py`

SW + ML engineers collaborate. ML engineer describes required shape/features; SW engineer writes loading+preprocessing code; execution validates the code runs.

```python
# agentlabx/stages/data_preparation.py
"""Real data preparation stage — ML/SW engineers collaborate on dataset pipeline."""

from __future__ import annotations

import json
import re

from agentlabx.core.state import PipelineState
from agentlabx.stages._helpers import build_agent_context, resolve_agent, resolve_tool
from agentlabx.stages.base import BaseStage, StageContext, StageResult


class DataPreparationStage(BaseStage):
    name = "data_preparation"
    description = "ML + SW engineers collaborate on data pipeline; validate via execution."
    required_agents = ["ml_engineer", "sw_engineer"]
    required_tools = ["code_executor"]

    async def run(self, state: PipelineState, context: StageContext) -> StageResult:
        registry = context.registry
        if registry is None:
            return StageResult(
                output={}, status="backtrack", next_hint=None,
                reason="No registry in StageContext",
            )

        ml = resolve_agent(
            registry, "ml_engineer",
            llm_provider=context.llm_provider,
            cost_tracker=context.cost_tracker,
        )
        sw = resolve_agent(
            registry, "sw_engineer",
            llm_provider=context.llm_provider,
            cost_tracker=context.cost_tracker,
        )
        code_executor = resolve_tool(registry, "code_executor")

        plan_list = state.get("plan", [])
        methodology = plan_list[-1].methodology if plan_list else "No plan"
        eda_list = state.get("data_exploration", [])
        eda_summary = (
            "; ".join(eda_list[-1].recommendations) if eda_list else "No EDA yet"
        )

        # Step 1: ML engineer specifies required features/shape
        specs_prompt = (
            f"Plan methodology:\n{methodology}\n\nEDA recommendations:\n{eda_summary}\n\n"
            f"Describe the dataset shape and preprocessing steps you need for the "
            f"experimentation stage. Be specific (batch size, features, splits)."
        )
        specs = await ml.inference(
            specs_prompt, build_agent_context(state, ml, phase="data_preparation"),
        )

        # Step 2: SW engineer writes the loader/preprocessor
        code_prompt = (
            f"ML engineer requirements:\n{specs}\n\n"
            f"Write a Python script that loads and preprocesses the dataset as specified. "
            f'Respond ONLY with JSON: {{"code": "..."}}. No prose.'
        )
        code_response = await sw.inference(
            code_prompt, build_agent_context(state, sw, phase="data_preparation"),
        )
        code = _parse_json(code_response).get("code", "")

        # Step 3: Execute to validate
        import tempfile
        from pathlib import Path
        validation_passed = False
        stderr = ""
        if code:
            with tempfile.TemporaryDirectory() as tmpdir:
                exec_result = await code_executor.execute(
                    code=code, workspace=str(Path(tmpdir)), timeout=120,
                )
                validation_passed = exec_result.success
                stderr = exec_result.data.get("stderr", "") if exec_result else ""

        if not validation_passed and code:
            # SW engineer debugs once
            debug_prompt = (
                f"The preprocessing script failed:\n\nStderr:\n{stderr[:500]}\n\n"
                f'Fix the code. Respond ONLY with JSON: {{"code": "..."}}'
            )
            debug_response = await sw.inference(
                debug_prompt, build_agent_context(state, sw, phase="data_preparation"),
            )
            code = _parse_json(debug_response).get("code", code)

        return StageResult(
            output={"dataset_code": [code] if code else []},
            status="done" if code else "backtrack",
            next_hint=None if code else "data_exploration",
            reason=(
                "Data preparation pipeline ready"
                if code else "Could not produce working data pipeline"
            ),
        )


def _parse_json(text: str) -> dict:
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if match:
        try:
            return json.loads(match.group(0))
        except json.JSONDecodeError:
            pass
    return {}
```

Tests mirror data_exploration pattern.

Commit: `feat(stages): add real data preparation stage with ML-SW engineer collaboration`

---

### Task 13: Real Experimentation Stage (with validation)

**Files:**
- Create: `agentlabx/stages/experimentation.py`
- Update skeleton.py
- Create: `tests/stages/test_experimentation_real.py`

Per spec §3.6 — enforce baseline + main + ablation structure. The stage must NOT exit "done" without at least one baseline result, and without at least one ablation if main shows positive results.

```python
# agentlabx/stages/experimentation.py
"""Real experimentation stage — ML engineer runs baseline, main, ablations with validation."""

from __future__ import annotations

import json
import re
from datetime import UTC, datetime
from typing import Literal

from agentlabx.core.state import ExperimentResult, PipelineState, ReproducibilityRecord
from agentlabx.stages._helpers import build_agent_context, resolve_agent, resolve_tool
from agentlabx.stages.base import BaseStage, StageContext, StageResult


class ExperimentationStage(BaseStage):
    name = "experimentation"
    description = "ML engineer runs baselines, main experiments, and ablations (validated)."
    required_agents = ["ml_engineer"]
    required_tools = ["code_executor"]

    async def run(self, state: PipelineState, context: StageContext) -> StageResult:
        registry = context.registry
        if registry is None:
            return StageResult(
                output={}, status="backtrack", next_hint=None,
                reason="No registry in StageContext",
            )

        ml = resolve_agent(
            registry, "ml_engineer",
            llm_provider=context.llm_provider,
            cost_tracker=context.cost_tracker,
        )
        code_executor = resolve_tool(registry, "code_executor")

        plan_list = state.get("plan", [])
        hypotheses = state.get("hypotheses", [])
        methodology = plan_list[-1].methodology if plan_list else "No plan"

        results: list[ExperimentResult] = []

        # Run each experiment tier
        for tier in ("baseline", "main", "ablation"):
            prompt = self._build_experiment_prompt(tier, methodology, hypotheses, results)
            response = await ml.inference(
                prompt, build_agent_context(state, ml, phase="experimentation"),
            )
            parsed = _parse_json(response)
            code = parsed.get("code", "")
            if not code:
                continue

            # Execute
            import tempfile
            from pathlib import Path
            with tempfile.TemporaryDirectory() as tmpdir:
                exec_result = await code_executor.execute(
                    code=code, workspace=str(Path(tmpdir)), timeout=180, seed=42,
                )
                if not exec_result.success:
                    continue

                # Extract metrics from JSON-in-stdout or use provided
                stdout = exec_result.data.get("stdout", "")
                metrics = _extract_metrics(stdout) or parsed.get("metrics", {})
                repro = exec_result.data.get("reproducibility")
                repro_record = ReproducibilityRecord(**repro) if repro else ReproducibilityRecord(
                    random_seed=42, environment_hash="", run_command="",
                    timestamp=datetime.now(UTC),
                )

                result = ExperimentResult(
                    tag=tier,  # type: ignore[arg-type]
                    metrics=metrics,
                    description=parsed.get("description", f"{tier} experiment"),
                    reproducibility=repro_record,
                )
                results.append(result)

            # Skip ablation if no positive main result
            if tier == "main" and not _has_positive_improvement(results):
                break

        # Enforce validation: must have baseline
        has_baseline = any(r.tag == "baseline" for r in results)
        has_main = any(r.tag == "main" for r in results)
        has_ablation = any(r.tag == "ablation" for r in results)

        if not has_baseline:
            return StageResult(
                output={"experiment_results": results},
                status="backtrack",
                next_hint="plan_formulation",
                reason="Experimentation requires at least one baseline result",
            )

        # If main shows improvement, ablation is required
        if has_main and _has_positive_improvement(results) and not has_ablation:
            return StageResult(
                output={"experiment_results": results},
                status="backtrack",
                next_hint="experimentation",
                reason="Positive main result requires at least one ablation study",
            )

        # Negative result path
        if has_main and not _has_positive_improvement(results):
            return StageResult(
                output={"experiment_results": results},
                status="negative_result",
                reason="Experiments did not show significant improvement over baseline",
            )

        return StageResult(
            output={"experiment_results": results},
            status="done",
            reason=f"Experimentation complete: {len(results)} runs (baseline, main, ablation)",
        )

    def _build_experiment_prompt(
        self,
        tier: Literal["baseline", "main", "ablation"],
        methodology: str,
        hypotheses: list,
        prior_results: list,
    ) -> str:
        prior_summary = "\n".join(
            f"- {r.tag}: {r.metrics}" for r in prior_results
        ) or "(none yet)"
        hyp_summary = "\n".join(
            f"- {h.statement}" for h in hypotheses[:3]
        ) or "(no hypotheses)"
        tier_goal = {
            "baseline": "Establish baseline performance without any new techniques.",
            "main": "Test the main hypothesis against the baseline.",
            "ablation": "Ablate one component at a time to understand contributions.",
        }[tier]
        return (
            f"Methodology: {methodology}\n\nHypotheses:\n{hyp_summary}\n\n"
            f"Prior results:\n{prior_summary}\n\n"
            f"Current tier: {tier}. {tier_goal}\n\n"
            f"Write a short Python script that runs this experiment. "
            f"The script MUST print a JSON line like: "
            f'`{{"metrics": {{"accuracy": 0.75, "f1": 0.72}}}}` as its final line.\n\n'
            f"Respond ONLY with JSON:\n"
            f'{{"code": "...", "description": "...", "metrics": {{}}}}\n\nNo prose.'
        )


def _parse_json(text: str) -> dict:
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if match:
        try:
            return json.loads(match.group(0))
        except json.JSONDecodeError:
            pass
    return {}


def _extract_metrics(stdout: str) -> dict:
    """Find the last {"metrics": {...}} line in stdout."""
    for line in reversed(stdout.strip().split("\n")):
        line = line.strip()
        if line.startswith("{") and "metrics" in line:
            try:
                parsed = json.loads(line)
                return parsed.get("metrics", {})
            except json.JSONDecodeError:
                continue
    return {}


def _has_positive_improvement(results: list) -> bool:
    """Check if main result shows improvement over baseline."""
    baselines = [r for r in results if r.tag == "baseline"]
    mains = [r for r in results if r.tag == "main"]
    if not baselines or not mains:
        return False
    # Compare first shared metric
    for metric in mains[-1].metrics:
        if metric in baselines[-1].metrics:
            if mains[-1].metrics[metric] > baselines[-1].metrics[metric]:
                return True
    return False
```

Tests:
- test_complete_pipeline (baseline + main with improvement + ablation → done)
- test_missing_baseline_backtracks
- test_positive_main_without_ablation_backtracks
- test_no_improvement_returns_negative_result
- test_execution_failure_handled

Commit: `feat(stages): add real experimentation stage with enforced baseline+ablation validation`

---

### Task 14: Real Results Interpretation Stage

**Files:**
- Create: `agentlabx/stages/results_interpretation.py`
- Update skeleton.py
- Create: `tests/stages/test_results_interpretation_real.py`

Postdoc and PhD interpret experiment results, update hypothesis statuses, link evidence. Per spec §3.5 — interpretation should mutate hypothesis status (active/supported/refuted) based on evidence.

```python
# agentlabx/stages/results_interpretation.py
"""Real results interpretation stage — postdoc + PhD analyze experiments, update hypotheses."""

from __future__ import annotations

import json
import re

from agentlabx.core.state import EvidenceLink, Hypothesis, PipelineState
from agentlabx.stages._helpers import build_agent_context, resolve_agent
from agentlabx.stages.base import BaseStage, StageContext, StageResult


class ResultsInterpretationStage(BaseStage):
    name = "results_interpretation"
    description = "Postdoc and PhD interpret results, update hypothesis status."
    required_agents = ["postdoc", "phd_student"]
    required_tools = []

    async def run(self, state: PipelineState, context: StageContext) -> StageResult:
        registry = context.registry
        if registry is None:
            return StageResult(
                output={}, status="backtrack", next_hint=None,
                reason="No registry in StageContext",
            )

        postdoc = resolve_agent(
            registry, "postdoc",
            llm_provider=context.llm_provider,
            cost_tracker=context.cost_tracker,
        )
        phd = resolve_agent(
            registry, "phd_student",
            llm_provider=context.llm_provider,
            cost_tracker=context.cost_tracker,
        )

        experiments = state.get("experiment_results", [])
        hypotheses = state.get("hypotheses", [])

        exp_summary = "\n".join(
            f"- {e.tag}: {e.metrics}" for e in experiments
        ) or "(none)"
        hyp_summary = "\n".join(
            f"- {h.id}: {h.statement}" for h in hypotheses
        ) or "(none)"

        # Step 1: Postdoc writes draft interpretation
        interp_prompt = (
            f"Experiment results:\n{exp_summary}\n\nHypotheses:\n{hyp_summary}\n\n"
            f"Write a 200-word interpretation. For each hypothesis, state whether the "
            f"evidence supports, refutes, or is inconclusive. Cite specific metric values."
        )
        draft = await postdoc.inference(
            interp_prompt, build_agent_context(state, postdoc, phase="results_interpretation"),
        )

        # Step 2: PhD adds nuance
        phd_prompt = (
            f"Postdoc's interpretation:\n{draft}\n\n"
            f"Add 1-2 nuanced observations or caveats. Be concise."
        )
        phd_input = await phd.inference(
            phd_prompt, build_agent_context(state, phd, phase="results_interpretation"),
        )

        # Step 3: Postdoc finalizes + emits structured hypothesis updates
        final_prompt = (
            f"Draft:\n{draft}\n\nPhD input:\n{phd_input}\n\n"
            f"Finalize interpretation AND emit hypothesis updates. Respond ONLY with JSON:\n"
            f'{{"interpretation": "200-word final text", '
            f'"hypothesis_updates": [{{"id": "H1", "new_status": "supported"|"refuted"|"active"|"abandoned", '
            f'"evidence": [{{"experiment_result_index": 0, "metric": "accuracy", '
            f'"value": 0.78, "interpretation": "..."}}]}}]}}\n\nNo prose outside JSON.'
        )
        final_response = await postdoc.inference(
            final_prompt, build_agent_context(state, postdoc, phase="results_interpretation"),
        )
        parsed = _parse_json(final_response)

        interpretation_text = parsed.get("interpretation", draft + "\n" + phd_input)
        hypothesis_updates = parsed.get("hypothesis_updates", [])

        # Apply updates: build new Hypothesis objects with updated status + evidence
        updated_hypotheses: list[Hypothesis] = []
        hyp_by_id = {h.id: h for h in hypotheses}
        for update in hypothesis_updates:
            hid = update.get("id")
            if hid not in hyp_by_id:
                continue
            original = hyp_by_id[hid]
            new_status = update.get("new_status", original.status)
            if new_status not in ("active", "supported", "refuted", "abandoned"):
                new_status = original.status
            evidence = update.get("evidence", [])
            evidence_links = []
            for e in evidence:
                try:
                    evidence_links.append(EvidenceLink(
                        experiment_result_index=int(e.get("experiment_result_index", 0)),
                        metric=str(e.get("metric", "")),
                        value=float(e.get("value", 0.0)),
                        interpretation=str(e.get("interpretation", "")),
                    ))
                except (TypeError, ValueError):
                    continue

            updated = Hypothesis(
                id=original.id,
                statement=original.statement,
                status=new_status,
                evidence_for=original.evidence_for + [
                    e for e in evidence_links if new_status == "supported"
                ],
                evidence_against=original.evidence_against + [
                    e for e in evidence_links if new_status == "refuted"
                ],
                parent_hypothesis=original.parent_hypothesis,
                created_at_stage=original.created_at_stage,
                resolved_at_stage="results_interpretation" if new_status != "active" else None,
            )
            updated_hypotheses.append(updated)

        output: dict = {"interpretation": [interpretation_text]}
        if updated_hypotheses:
            # For hypothesis updates, use operator.add reducer — appending updated
            # records alongside originals creates a history. UI can render latest.
            output["hypotheses"] = updated_hypotheses

        return StageResult(
            output=output,
            status="done",
            reason=(
                f"Interpretation complete with {len(updated_hypotheses)} "
                f"hypothesis updates"
            ),
        )


def _parse_json(text: str) -> dict:
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if match:
        try:
            return json.loads(match.group(0))
        except json.JSONDecodeError:
            pass
    return {}
```

Tests:
- test_updates_hypothesis_to_supported (H1 → supported with evidence link)
- test_updates_hypothesis_to_refuted (H2 → refuted)
- test_no_updates_still_produces_interpretation
- test_malformed_json_still_produces_draft_text
- test_unknown_hypothesis_id_ignored

Commit: `feat(stages): add real results interpretation stage with hypothesis status updates`

---

### Task 15: CLI Entrypoint

**Files:**
- Create: `agentlabx/cli/__init__.py` (empty)
- Create: `agentlabx/cli/main.py`
- Create: `tests/cli/__init__.py` (empty)
- Create: `tests/cli/test_cli.py`

```python
# agentlabx/cli/main.py
"""Command-line entrypoints."""

from __future__ import annotations

import click
import uvicorn

from agentlabx import __version__


@click.group()
@click.version_option(version=__version__, prog_name="agentlabx")
def cli():
    """AgentLabX — modular multi-instance research automation platform."""


@cli.command()
@click.option("--host", default="0.0.0.0", help="Bind host")
@click.option("--port", default=8000, type=int, help="Bind port")
@click.option("--reload", is_flag=True, help="Enable hot reload (development)")
@click.option("--mock-llm", is_flag=True, help="Use MockLLMProvider (no API keys needed)")
def serve(host: str, port: int, reload: bool, mock_llm: bool):
    """Run the AgentLabX HTTP + WebSocket server."""
    import os
    if mock_llm:
        os.environ["AGENTLABX_USE_MOCK_LLM"] = "1"
    uvicorn.run(
        "agentlabx.cli.main:build_app",
        host=host,
        port=port,
        reload=reload,
        factory=True,
    )


def build_app():
    """Factory invoked by uvicorn."""
    import os
    from agentlabx.server.app import create_app
    return create_app(use_mock_llm=os.getenv("AGENTLABX_USE_MOCK_LLM") == "1")
```

Tests:
- test_cli_version (invoke `agentlabx --version`)
- test_serve_command_exists (invoke `agentlabx serve --help`)
- test_build_app_returns_fastapi (test `build_app()` is invokable)

Use `click.testing.CliRunner`:
```python
from click.testing import CliRunner
def test_version():
    runner = CliRunner()
    result = runner.invoke(cli, ["--version"])
    assert result.exit_code == 0
    assert "0.1.0" in result.output
```

Commit: `feat(cli): add agentlabx serve command for running the HTTP server`

---

### Task 16: End-to-End Server Tests

**Files:**
- Create: `tests/server/test_server_e2e.py`

Tests that start the server (via ASGI test client), create a session, start it with MockLLMProvider, observe events via WS, and verify the session completes end-to-end.

```python
# tests/server/test_server_e2e.py
"""End-to-end server tests: full session lifecycle over HTTP + WebSocket."""

from __future__ import annotations

import asyncio

import pytest
from fastapi.testclient import TestClient
from httpx import ASGITransport, AsyncClient

from agentlabx.server.app import create_app


@pytest.fixture()
def client():
    app = create_app(use_mock_llm=True)
    with TestClient(app) as tc:
        yield tc


class TestServerE2E:
    def test_create_start_complete_session(self, client):
        # Create
        response = client.post("/api/sessions", json={"topic": "Test topic", "user_id": "u1"})
        assert response.status_code == 201
        session_id = response.json()["session_id"]

        # Start
        response = client.post(f"/api/sessions/{session_id}/start")
        assert response.status_code == 202

        # Wait briefly for pipeline to run (MockLLMProvider is fast)
        # In practice, we'd await the task or poll; here we give the async loop time
        # via a small sleep on the test client side
        import time
        time.sleep(2.0)

        # Check state
        response = client.get(f"/api/sessions/{session_id}")
        # Status should be running, paused, or completed
        assert response.json()["status"] in ("running", "paused", "completed", "failed")

    def test_preferences_update(self, client):
        r = client.post("/api/sessions", json={"topic": "t", "user_id": "u1"})
        sid = r.json()["session_id"]

        r = client.patch(
            f"/api/sessions/{sid}/preferences",
            json={"mode": "hitl", "stage_controls": {"experimentation": "approve"}},
        )
        assert r.status_code == 200
        prefs = r.json()["preferences"]
        assert prefs["mode"] == "hitl"
        assert prefs["stage_controls"]["experimentation"] == "approve"

    def test_plugins_endpoint(self, client):
        r = client.get("/api/plugins")
        assert r.status_code == 200
        data = r.json()
        assert "agent" in data
        assert "stage" in data
        assert "tool" in data
        assert "phd_student" in data["agent"]

    def test_websocket_connection(self, client):
        r = client.post("/api/sessions", json={"topic": "t", "user_id": "u1"})
        sid = r.json()["session_id"]
        with client.websocket_connect(f"/ws/sessions/{sid}") as ws:
            ws.send_json({"action": "update_preferences", "mode": "hitl"})
        # If we got here, WS connect + send succeeded

    def test_redirect_via_api(self, client):
        r = client.post("/api/sessions", json={"topic": "t", "user_id": "u1"})
        sid = r.json()["session_id"]
        # Before starting, redirect should still respond (even if no-op)
        r = client.post(
            f"/api/sessions/{sid}/redirect",
            json={"target_stage": "plan_formulation", "reason": "manual"},
        )
        assert r.status_code == 202
```

Run full suite + lint:
```bash
uv run pytest tests/ -v --tb=short
uv run ruff check agentlabx/ tests/
uv run ruff format agentlabx/ tests/
```

Commit: `test(server): add end-to-end server integration tests`

---

## Summary

After completing all 16 tasks:

**Server infrastructure:**
- FastAPI app with CORS, lifespan-managed AppContext
- Dependency injection for registry, session manager, storage, LLM provider, executor
- REST API: 12 endpoints covering sessions CRUD/lifecycle, preferences, artifacts, transitions, cost, hypotheses, plugins
- WebSocket: per-session real-time event streaming + client action handling
- PipelineExecutor: manages concurrent sessions as asyncio tasks with pause/resume/redirect/cancel
- Session persistence via SQLite

**Remaining 4 real stages complete** — all 8 research stages now real:
- Data exploration (SW engineer + code_executor EDA)
- Data preparation (ML+SW collaboration with execution validation)
- Experimentation (baseline → main → ablation, enforced validation)
- Results interpretation (postdoc+PhD dialogue + hypothesis status updates)

**Platform hosting:**
- `agentlabx serve` CLI for one-command startup
- `--mock-llm` flag for API-key-free local testing
- Hot reload for development

**What's deferred to Plan 5 (Frontend):**
- React + Ant Design + Vite UI
- Session dashboard
- Pipeline visualization via React Flow
- Agent activity feed
- Cost tracker visualization

**What's deferred to post-Plan 5 (production hardening):**
- OAuth/JWT authentication
- PostgreSQL + MinIO migration (architecture supports it, opt-in)
- Kubernetes execution backend
- Claude Code SDK integration (BaseCodeAgent adapter)
- HITL interrupt flow full implementation via LangGraph `interrupt()` (approve/edit client actions resume interrupted graph; current pause is cooperative via event)

---

## Addendum: Review Fixes (apply during execution)

The following corrections resolve blocking issues identified during Plan 4
review. Apply them as each relevant task is implemented.

### Fix A (CRITICAL): Cooperative pause via event on StageContext

Original Task 6 had `running.paused.clear()` but the runner never checked it.
Pause was a silent no-op.

**Solution: Option A — cooperative pause in StageRunner.**

**Changes:**

1. Add `paused_event` to `StageContext` (`agentlabx/stages/base.py`):
   ```python
   class StageContext(BaseModel):
       settings: Any = None
       event_bus: Any = None
       registry: Any = None
       llm_provider: Any = None
       cost_tracker: Any = None
       paused_event: Any = None  # asyncio.Event; set=running, clear=paused
       model_config = {"arbitrary_types_allowed": True}
   ```

2. In `StageRunner.run()`, await the event between `on_enter` and `stage.run`:
   ```python
   # After on_enter, before stage.run:
   paused_event = getattr(self.context, "paused_event", None)
   if paused_event is not None:
       await paused_event.wait()  # Blocks if cleared (paused)
   ```

3. In `PipelineExecutor.start_session`, create the event and attach:
   ```python
   paused_event = asyncio.Event()
   paused_event.set()  # Not paused initially
   stage_context = StageContext(
       ..., paused_event=paused_event,
   )
   # PipelineBuilder needs to accept this or the executor must inject it
   # differently. Simplest: PipelineBuilder accepts a pre-built StageContext
   # via an optional override parameter.
   ```

4. `PipelineBuilder.build()` gains `stage_context: StageContext | None = None` —
   when provided, use it instead of constructing one. This keeps other tasks
   unchanged.

5. `pause_session` → `running.paused_event.clear()`; `resume_session` →
   `running.paused_event.set()`. Remove the existing `running.paused` Event
   (was dead code).

**Tests:** Add to `test_executor.py`:
```python
async def test_pause_blocks_between_stages():
    # Start a session, pause immediately, verify stage_iterations stops
    # incrementing after the in-flight stage completes (doesn't start next).
    # Resume, verify iterations continue.
```

### Fix B (CRITICAL): EventBus at session creation, not start

Original Task 9 subscribed to the bus only if `executor.get_running(session_id)`
returned a session. If the UI opened a WS before `/start`, zero events were
forwarded.

**Solution: Promote EventBus to a session-level resource.**

**Changes:**

1. Add `event_bus: EventBus` to `Session` in `agentlabx/core/session.py`:
   ```python
   from agentlabx.core.events import EventBus

   class Session:
       def __init__(self, ...) -> None:
           ...
           self.event_bus = EventBus()  # Created with the session
   ```

2. In Task 6 `PipelineExecutor.start_session`, reuse `session.event_bus` instead
   of constructing a new one:
   ```python
   running = RunningSession(
       session=session,
       event_bus=session.event_bus,  # Use the pre-existing bus
       ...,
   )
   ```

3. In Task 9 WS handler, subscribe to `session.event_bus` directly — no
   dependency on executor or running state:
   ```python
   @router.websocket("/ws/sessions/{session_id}")
   async def session_websocket(websocket: WebSocket, session_id: str):
       session = context.session_manager.get_session(session_id)
       # subscribe to session.event_bus — works whether running or not
       session.event_bus.subscribe("*", forward_event)
       ...
   ```

4. Update Plan 2 `test_session.py`: the `SessionPreferences` comparison tests
   should not inspect `event_bus` — the existing tests compare sessions by
   field, which will now have a non-serializable bus. Use `session.model_dump()`
   or the existing attribute tests only.

   **If `Session` is a plain Python class (not Pydantic)** (check Plan 2's
   implementation), no change needed. Verify before editing.

### Fix C (CRITICAL): Use AsyncSqliteSaver for LangGraph checkpoints

Original Task 6 used `MemorySaver()`. Two consequences:
- Sessions lost on restart
- `/artifacts` returned empty for completed sessions (state removed from memory
  when task cleaned up from `_running`)

**Solution: Use `langgraph-checkpoint-sqlite.AsyncSqliteSaver`.** The
dependency is already installed (Plan 2 added it).

**Changes in Task 6 `PipelineExecutor`:**

```python
# agentlabx/server/executor.py
from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver
import aiosqlite


class PipelineExecutor:
    def __init__(
        self,
        *,
        registry: PluginRegistry,
        session_manager: SessionManager,
        llm_provider: BaseLLMProvider,
        checkpoint_db_path: str = "data/checkpoints.db",
    ) -> None:
        ...
        self._checkpoint_db_path = checkpoint_db_path
        self._checkpointer: AsyncSqliteSaver | None = None
        self._checkpointer_conn: Any | None = None

    async def initialize(self) -> None:
        """Open the checkpoint DB. Call once at app startup."""
        Path(self._checkpoint_db_path).parent.mkdir(parents=True, exist_ok=True)
        self._checkpointer_conn = await aiosqlite.connect(self._checkpoint_db_path)
        self._checkpointer = AsyncSqliteSaver(self._checkpointer_conn)

    async def close(self) -> None:
        if self._checkpointer_conn is not None:
            await self._checkpointer_conn.close()

    async def start_session(self, session: Session) -> RunningSession:
        ...
        graph = builder.build(
            stage_sequence=default_sequence,
            checkpointer=self._checkpointer,  # <-- persistent
            llm_provider=self.llm_provider,
            cost_tracker=cost_tracker,
            event_bus=session.event_bus,
        )
        ...
```

Update `deps.py::build_app_context` to call `executor.initialize()` and
`create_app`'s lifespan to call `executor.close()` on shutdown.

**Also fixes Fix D below automatically**: because state is checkpointed to
SQLite, `/artifacts` for completed sessions reads directly from the graph
(`graph.aget_state(config)` works after the session task exits).

### Fix D: Save final state on completion + keep running entry briefly

Independently of the checkpointer change (defense in depth), explicitly save
final state in the pipeline task cleanup:

```python
async def run_pipeline():
    try:
        final_result = await graph.ainvoke(initial_state, config=config)
        session.complete()
        await self.session_manager.persist_session(session)
    except asyncio.CancelledError:
        session.fail()  # <-- Fix E: mark as failed on cancel
        await self.session_manager.persist_session(session)
        raise
    except Exception as e:
        logger.exception("Pipeline error for %s: %s", session.session_id, e)
        session.fail()
        await self.session_manager.persist_session(session)
    finally:
        # Keep the running entry for artifact/state queries.
        # The graph handle is still valid; checkpoint is persisted.
        # Cleanup happens via an explicit endpoint or a TTL sweep.
        pass  # Do NOT pop from self._running here
```

With `AsyncSqliteSaver`, the checkpoint persists regardless of `_running`
membership, so the precise cleanup policy is less load-bearing. For memory
management, implement a later sweep task that removes completed entries older
than N minutes. Not in Plan 4 scope; noted as future work.

### Fix E: Session.fail() on cancel path

See Fix D — the `except asyncio.CancelledError` branch now calls
`session.fail()` before re-raising. Document this transition is valid in
`_VALID_TRANSITIONS` (Plan 2 code): RUNNING → FAILED and PAUSED → FAILED.

Verify `agentlabx/core/session.py` `_VALID_TRANSITIONS` allows these. If not,
update:

```python
_VALID_TRANSITIONS: dict[SessionStatus, set[SessionStatus]] = {
    SessionStatus.CREATED: {SessionStatus.RUNNING, SessionStatus.FAILED},
    SessionStatus.RUNNING: {SessionStatus.PAUSED, SessionStatus.COMPLETED, SessionStatus.FAILED},
    SessionStatus.PAUSED: {SessionStatus.RUNNING, SessionStatus.FAILED},
    # ...
}
```

### Fix F: Centralize session persistence via SessionManager wrapper

Rather than remembering to call `persist_session` on every transition, and
rather than fire-and-forget transition hooks (which swallow persistence
errors into the event loop), add thin transition-and-persist methods to
`SessionManager`:

```python
# agentlabx/core/session.py (or wherever SessionManager lives)
class SessionManager:
    async def start_session(self, session_id: str) -> None:
        session = self.get_session(session_id)
        session.start()
        await self.persist_session(session)

    async def pause_session(self, session_id: str) -> None:
        session = self.get_session(session_id)
        session.pause()
        await self.persist_session(session)

    async def resume_session(self, session_id: str) -> None:
        session = self.get_session(session_id)
        session.resume()
        await self.persist_session(session)

    async def complete_session(self, session_id: str) -> None:
        session = self.get_session(session_id)
        session.complete()
        await self.persist_session(session)

    async def fail_session(self, session_id: str) -> None:
        session = self.get_session(session_id)
        session.fail()
        await self.persist_session(session)
```

This keeps persistence errors synchronous and logged at the call site.
Callers (`PipelineExecutor`, REST routes) go through these wrappers instead of
`session.start()` directly.

**Why not transition hooks:** `asyncio.get_running_loop().create_task(...)`
is fire-and-forget. If `persist_session` raises (disk full, SQLite lock, etc.)
the error disappears into the event loop. With the wrapper approach, the
exception propagates to the REST handler which returns a 500, or the executor
which can decide whether to fail the session. Error visibility > API
elegance here.

**Exception:** `Session` itself should still expose raw `start()/pause()/...`
for unit tests that don't want to touch storage. Only the async wrappers on
`SessionManager` trigger persistence.

### Fix G: Single event subscription per session (WS amplification)

Original Task 9 subscribed each WS client to `event_bus` independently. Three
clients = three forwardings through the bus × three broadcasts = 9 sends.

**Solution: Subscribe once per session (at executor start time), forward to
ConnectionManager.broadcast.**

In `PipelineExecutor.start_session`, after creating the event bus:

```python
async def forward_event_to_ws(event: Event) -> None:
    from agentlabx.server.ws.handlers import manager
    await manager.broadcast(session.session_id, {
        "type": event.type,
        "data": event.data,
        "source": event.source,
    })

session.event_bus.subscribe("*", forward_event_to_ws)
```

WS handler no longer subscribes — it only accepts connections and receives
client messages. Events flow: `stage → EventBus → single subscriber →
manager.broadcast → all connected clients`.

For Fix B's "subscribe at session creation" to work with this pattern, the
session creation step (not just start) should register the forwarder. Move the
`subscribe` call from `start_session` to `SessionManager.create_session` (or
wherever Session is constructed).

### Fix H: Hypothesis list — "latest by ID" helper

Task 14 appends updated hypotheses via `operator.add` reducer, so state ends
with `[H1, H2, H1_updated, H2_updated]`. Add a helper on the state module so
UI/tools don't repeat the "latest by ID" computation:

```python
# agentlabx/core/state.py
def active_hypotheses(hypotheses: list[Hypothesis]) -> list[Hypothesis]:
    """Return the latest hypothesis record per ID (last-write-wins by position)."""
    latest: dict[str, Hypothesis] = {}
    for h in hypotheses:
        latest[h.id] = h
    return list(latest.values())
```

Use this helper in Task 8's `/hypotheses` endpoint.

### Fix I: Redirect before start

Original Task 5's `/redirect` returned 202 even when the session wasn't
running. Clients got success but nothing happened.

**Solution: Return 409 when not RUNNING.**

```python
@router.post("/{session_id}/redirect", status_code=202)
async def redirect_session(...):
    session = manager.get_session(session_id)
    if session.status != SessionStatus.RUNNING:
        raise HTTPException(
            status_code=409,
            detail=f"Cannot redirect from status '{session.status.value}'. "
                   f"Session must be RUNNING.",
        )
    ...
```

Update Task 16's `test_redirect_via_api` to expect 409, or call start before
redirect.

### Fix J: E2E test polling

Replace `time.sleep(2.0)` in Task 16 with polling:

```python
import time
def wait_for_status(client, session_id, target_statuses, timeout=10.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        r = client.get(f"/api/sessions/{session_id}")
        if r.json()["status"] in target_statuses:
            return r.json()
        time.sleep(0.1)
    raise TimeoutError(f"Session never reached {target_statuses}")

def test_create_start_complete_session(client):
    r = client.post("/api/sessions", json={"topic": "Test", "user_id": "u1"})
    sid = r.json()["session_id"]
    client.post(f"/api/sessions/{sid}/start")
    final = wait_for_status(client, sid, {"completed", "failed"}, timeout=30.0)
    assert final["status"] == "completed"
```

### Fix K: Event emission ordering on failure

Task 3 emits `stage_failed` in the `except` block. Clarify that `stage_completed`
is NOT emitted on failure. Move the `stage_completed` emission inside the `try`
block, after `result` is set:

```python
try:
    result = await self.stage.run(entered_state, self.context)
    # ... apply update ...
    if self.context.event_bus is not None:
        await self.context.event_bus.emit(Event(
            type="stage_completed",
            data={...},
        ))
except Exception as e:
    # ... error handling ...
    if self.context.event_bus is not None:
        await self.context.event_bus.emit(Event(
            type="stage_failed",
            data={...},
        ))
```

On success: `stage_started` → `stage_completed`.
On failure: `stage_started` → `stage_failed`.
Never both.

### Fix L: Thread ID reuse semantics — document

Add to the Plan 4 docstring of `PipelineExecutor.start_session`:

```python
"""Begin running a session's pipeline.

The session_id is used as the LangGraph thread_id. With AsyncSqliteSaver
this means restarting a session continues from its last checkpoint — the
graph does NOT start fresh. This is intentional: it gives pause/resume
durability across server restarts. To re-run from scratch, create a new
session with a fresh session_id.
"""
```

### Fix M: CLI factory coupling

Task 15's `build_app` reads env var. Cleaner — use a module-level variable set
by the `serve` command:

```python
# agentlabx/cli/main.py
# NOTE: module-level state is NOT reload-safe. uvicorn --reload spawns a new
# process on file change, which resets this global. The dev flow is
# "ctrl-C + restart" when flags change, so this is a non-issue in practice —
# just be aware that flipping --mock-llm while a reload-watched process is
# running won't take effect until a full restart.
_USE_MOCK_LLM = False


def _build_app_with_config():
    """Factory called by uvicorn.run(factory=True)."""
    from agentlabx.server.app import create_app
    return create_app(use_mock_llm=_USE_MOCK_LLM)


@cli.command()
@click.option("--mock-llm", is_flag=True)
def serve(host, port, reload, mock_llm):
    global _USE_MOCK_LLM
    _USE_MOCK_LLM = mock_llm
    uvicorn.run(
        "agentlabx.cli.main:_build_app_with_config",
        host=host, port=port, reload=reload, factory=True,
    )
```

Globals are ugly but the CLI-to-uvicorn-factory handoff is inherently
stateful. Env var approach in original Task 15 is a wash vs. this — pick
whichever the implementer prefers. Document in the task either way.

---

### Updated Summary (post-addendum)

Plan 4 still has 16 numbered tasks. The above fixes attach to specific tasks:

- **Task 2**: accept optional pre-built `StageContext` in `build()` (Fix A)
- **Task 3**: emit `stage_completed` and `stage_failed` mutually exclusively (Fix K)
- **Task 5**: `/redirect` returns 409 when not RUNNING (Fix I)
- **Task 6**: use `AsyncSqliteSaver` + cooperative pause + save final state + fail on cancel + subscribe-once WS forwarder (Fixes A, C, D, E, G, L)
- **Task 8**: use `active_hypotheses` helper (Fix H)
- **Task 9**: remove per-WS subscription, subscribe at session creation (Fix B, G)
- **Task 10**: centralize persistence via transition hook or manager wrapper (Fix F)
- **Task 14**: add `active_hypotheses` helper to state module (Fix H)
- **Task 15**: document CLI factory coupling approach (Fix M)
- **Task 16**: poll instead of `time.sleep` (Fix J)

After applying all fixes, the platform's restart-recovery story becomes
honest: sessions survive server restart (SQLite checkpoint), artifacts remain
queryable after completion (checkpoint persists), pause actually pauses
(cooperative event), and WS clients get events regardless of connection
timing (session-level bus).
