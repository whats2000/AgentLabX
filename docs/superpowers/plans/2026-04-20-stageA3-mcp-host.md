# Stage A3 — MCP Host + Bundled Servers Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development` (recommended) or `superpowers:executing-plans` to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship the Model Context Protocol (MCP) integration layer — a host that launches and manages MCP servers (stdio + streamable-HTTP transports), discovers their tools/capabilities at registration time, gates tool invocations against per-stage capability allow-lists, traces every tool call onto the event bus with secret redaction, and exposes a backend REST surface for runtime registration. **All bundled servers ship in this stage**, but the bias is **adopt > build**: use existing well-defined community/official MCP servers wherever they cover the SRS-mandated capability, and ship our own implementation only where no acceptable upstream exists (notably the `memory` server, whose schema is dictated by §3.3.5).

**Architecture (one-paragraph mental model).** A `MCPHost` owns a registry of `MCPServerHandle`s. Each handle wraps either a subprocess transport (stdio, for `npx`/`uvx`-launched servers) or an HTTP transport. On registration the host opens a session, calls `tools/list`, snapshots the tool schemas, and persists the server config (per-user or admin-scope) to SQLite. A `ToolDispatcher` is the only path from a stage to a tool: stages declare required `capabilities` (e.g., `paper_search`, `code_exec`); the dispatcher resolves capability → server → tool, checks the calling agent's per-stage allow-list (the field shape is added in A8 — A3 ships the gate with a no-op allow-list that accepts everything until A8 wires it), executes the call through the MCP session, and emits `mcp.tool.called` / `mcp.tool.error` events with redacted args. Bundled servers are configured via `agentlabx/mcp/bundles/<name>.py` modules that return a launch spec (command + env-var template) — they are not Python implementations of the tools, just launch descriptors for upstream packages. The `memory` server is the one exception: it ships as an in-process Python MCP server (`agentlabx.mcp.bundles.memory_server`) because its data model is defined by AgentLabX (§3.3.5) and there is no upstream that fits.

**Tech stack:** Python 3.12 · `mcp` (official Anthropic Python SDK, host + server primitives) · `anyio`/`asyncio` · FastAPI (A1) · SQLAlchemy async (A1) · A1 `FernetStore` + a new `SlotResolver` (added as a cross-cutting prereq — the shipped A2 `KeyResolver` is model-aware, not slot-aware) for secrets · EventBus (A1, with `payload` widened to `dict[str, JSONValue]` — see prereqs) · pluggable launchers via entry-point group `agentlabx.mcp_bundles` · `pytest` + `pytest-asyncio` · ruff (`ANN` incl. `ANN401`) · mypy strict.

**Verification gate (SRS §4.2 Stage A3):**

1. Each bundled server starts cleanly and a real `tools/list` + at least one real tool call succeeds.
2. A user-registered MCP server (added via REST, not config file) is reachable from the dispatcher within the same process — **no restart**.
3. Capability gating: a stage that does not declare a capability cannot invoke a tool requiring it; attempts emit `mcp.tool.refused`.
4. Every tool call emits `mcp.tool.called` (or `mcp.tool.error`) with secrets redacted (regex against known credential slot names + a deny-list of arg keys: `api_key`, `token`, `password`, `secret`, `authorization`).
5. Per-user isolation: user A's registered server is invisible to user B; admin-scope servers are visible to all.
6. All ruff (`ANN`/`ANN401`) and mypy `--strict` checks pass on production + test code.

**Adoption-over-implementation policy.** For each bundled capability the plan names a specific upstream package as the default launch target, plus a fallback if first-choice is unmaintained. Where two equivalent upstreams exist, the plan picks the one that (a) is published to a major package registry (`npm` / `pypi`) so users do not need to clone repos, (b) supports stdio transport without additional config, and (c) does not require a paid API key for the default smoke test.

---

## File structure (locked in before task decomposition)

```
agentlabx/
├── mcp/
│   ├── __init__.py                  # re-exports: MCPHost, ToolDispatcher, MCPServerSpec, ...
│   ├── protocol.py                  # MCPServerSpec, RegisteredServer, ToolDescriptor, CapabilityRequest dataclasses; exceptions
│   ├── transport.py                 # StdioLauncher + StreamableHTTPLauncher wrappers around mcp SDK transports
│   ├── host.py                      # MCPHost — manages handles, lifecycle, tools/list snapshot, restart policy
│   ├── dispatcher.py                # ToolDispatcher — capability→server resolution, gating, redaction, event emission
│   ├── redaction.py                 # redact_args() + redact_text() — pure functions, deny-list driven
│   ├── registry.py                  # ServerRegistry — SQLite persistence + per-user vs admin scope queries
│   ├── capabilities.py              # CapabilitySet, CapabilityResolver, default capability taxonomy seed
│   └── bundles/
│       ├── __init__.py              # entry-point exposed bundle loader
│       ├── filesystem.py            # launch spec → @modelcontextprotocol/server-filesystem (npx)
│       ├── arxiv.py                 # launch spec → blazickjp/arxiv-mcp-server (uvx)
│       ├── semantic_scholar.py      # launch spec → community semantic-scholar-mcp (uvx)
│       ├── browser.py               # launch spec → @modelcontextprotocol/server-fetch (uvx) — fetch is enough; puppeteer behind a flag
│       ├── code_execution.py        # launch spec for the Docker-sandboxed Python runner (Task 9)
│       ├── code_execution_server.py # AgentLabX-owned thin MCP wrapper that shells out to `docker run` — only created if no suitable upstream MCP server is adopted (Task 9)
│       └── memory_server.py         # AgentLabX-owned in-process MCP server: basic CRUD over experiment-memory entries (§3.3.5)

agentlabx/db/
└── schema.py                        # ADD: mcp_servers table (id, owner_id NULLABLE for admin-scope, name, scope, transport, command_json/url, env_slot_refs_json, capabilities_json, enabled, created_at)
└── migrations.py                    # ADD: v4→v5 migration `add_mcp_servers`

agentlabx/server/routers/
└── mcp.py                           # /api/mcp/* — list servers (scoped), register, update, delete, list tools, invoke (debug only, owner-gated)

agentlabx/cli/
└── ...                              # (unchanged — no new CLI commands in A3)

tests/
├── fakes/
│   └── echo_mcp_server.py           # tiny in-process stdio MCP server used as a deterministic dispatcher target
├── unit/mcp/
│   ├── __init__.py
│   ├── test_redaction.py
│   ├── test_capabilities.py
│   ├── test_dispatcher_gating.py    # gating + refusal events with a fake host
│   ├── test_registry.py             # SQLite round-trip, per-user vs admin scope visibility
│   └── test_memory_server_unit.py   # CRUD on the in-process memory server, no transport
└── integration/mcp/
    ├── test_host_lifecycle.py       # start/stop a handle backed by tests/fakes/echo_mcp_server.py
    ├── test_dispatcher_e2e.py       # capability→server→tool invocation via real MCP session
    ├── test_router_register_invoke.py  # full /api/mcp/* round-trip via httpx ASGI client
    └── test_bundled_smoke.py        # smoke each bundled server (skipped if launcher missing — see notes)
```

**No mock host class in production.** All test doubles live under `tests/`.

---

## Cross-cutting prerequisites (do these first; not a numbered task)

- [ ] Add `mcp>=1.0` (the official Python SDK) to `pyproject.toml` runtime deps.
- [ ] Add `pytest-asyncio` if not already present (A2 brought it in — confirm).
- [ ] Document `uvx`, `npx`, and Docker Engine as **required** system dependencies in the README install notes. CI runners and the dev environment must provide all three (used by the filesystem, arxiv/fetch, and code-execution bundles respectively). The unit-test suite still only needs Python, but integration/smoke tests assume these are present and do **not** skip on absence.
- [ ] **Introduce `JSONValue` / `JSONScalar` in a neutral module.** Create `agentlabx/core/json_types.py` (new package `agentlabx/core/` — a home for cross-cutting type aliases that both `events/` and `mcp/` depend on, avoiding any `events → mcp` reverse import). Contents: `JSONScalar = str | int | float | bool | None` and the recursive `JSONValue = JSONScalar | dict[str, "JSONValue"] | list["JSONValue"]`. Every other module that needs these types re-imports from here. `protocol.py` references in later tasks are shorthand — the canonical home is `agentlabx.core.json_types`.
- [ ] **Widen `Event.payload` type** from the current flat-scalar dict to `dict[str, JSONValue]` imported from `agentlabx.core.json_types`. This is a prerequisite for emitting `mcp.tool.called` / `mcp.tool.error` payloads that contain redacted nested arg dicts. Update `agentlabx/events/bus.py`, sweep every existing A1/A2 emitter + consumer (`TokenLogger`, audit sink, any test recorders) so they still type-check under `mypy --strict`, and re-run the full type-check. Treat as its own small PR-sized change landed before Task 6.
- [ ] **Introduce `SlotResolver`** at `agentlabx/security/slot_resolver.py` (new module — the shipped `agentlabx/llm/key_resolver.py` is model-aware, not slot-aware, and generalising it would muddy its single purpose). Signature: `class SlotResolver: def __init__(self, fernet_store: FernetStore, session_factory: async_sessionmaker[AsyncSession]) -> None: ...` and `async def resolve(self, *, owner_id: str | None, slot: str) -> str | None`. Behaviour: if `owner_id is not None`, query the user's `user_configs` row for that slot and decrypt via `FernetStore`; if `owner_id is None` (admin-scope), check in order (a) an `admin_configs` row (same shape as `user_configs`, added if not already present — Task 3 migration territory), (b) the OS process environment variable `AGENTLABX_SLOT_<SLOT_UPPER>`, returning the first hit. Returns `None` if the slot is unset — caller (`MCPHost.start`) decides whether the server can launch without it (bundle-dependent; see Task 9). Every reference to `UserConfigStore` in this plan is shorthand for this new resolver.
- [ ] Create the feature branch (already done: `stageA3-mcp-host`).

---

## Task 1: MCP protocol surface — dataclasses, exceptions, capability taxonomy

**Files:**
- Create: `agentlabx/mcp/__init__.py`
- Create: `agentlabx/mcp/protocol.py`
- Create: `agentlabx/mcp/capabilities.py`
- Create: `tests/unit/mcp/__init__.py`
- Create: `tests/unit/mcp/test_capabilities.py`

- [ ] **Step 1 — protocol.py.** `from agentlabx.core.json_types import JSONScalar, JSONValue` at the top — this module owns the MCP surface types but not the JSON type aliases. Define frozen dataclasses (use `pydantic.BaseModel` only at the REST boundary, not internally):
  - `Scope = Literal["user", "admin"]`
  - `Transport = Literal["stdio", "http", "inprocess"]`
  - `MCPServerSpec(name: str, scope: Scope, transport: Transport, command: tuple[str, ...] | None, url: str | None, inprocess_key: str | None, env_slot_refs: tuple[str, ...], declared_capabilities: tuple[str, ...])` — exactly one of `command` (stdio), `url` (http), or `inprocess_key` (inprocess) must be set; validator raises otherwise.
  - `ToolDescriptor(server_name: str, tool_name: str, description: str, input_schema: dict[str, JSONValue], capabilities: tuple[str, ...])` — `input_schema` is a real (recursively nested) JSON Schema object.
  - `ToolCallResult(content: tuple[ToolContentItem, ...], is_error: bool, structured: dict[str, JSONValue] | None)` — the AgentLabX-native shape for a tool invocation result. `ToolContentItem` is a tagged union: `TextContent(type: Literal["text"], text: str)`, `ImageContent(type: Literal["image"], data: str, mime_type: str)`, `ResourceRefContent(type: Literal["resource"], uri: str, mime_type: str | None)` — covers the MCP SDK's `CallToolResult.content` variants. `structured` mirrors the SDK's optional `structuredContent` field when present. The host adapts `CallToolResult` → `ToolCallResult` at the boundary; downstream code (dispatcher, REST) only ever sees `ToolCallResult` and never the raw SDK type.
  - `RegisteredServer(spec: MCPServerSpec, owner_id: str | None, tools: tuple[ToolDescriptor, ...], started_at: datetime | None)` — `owner_id is None` only for admin-scope.
  - `CapabilityRequest(stage_name: str, agent_name: str, capability: str)` — input to the gate.
  - Exceptions: `MCPError(Exception)` base; `ServerNotRunning`, `ToolNotFound`, `ToolExecutionFailed(server, tool, underlying)`, `CapabilityRefused(stage, agent, capability)`, `ServerStartupFailed(spec, reason)`, `RegistrationConflict(name)` — all with explicit `__init__` typed args, no `**kwargs`.

- [ ] **Step 2 — capabilities.py.** Define the seed capability taxonomy as a frozen `tuple[str, ...]`:
  - `paper_search`, `paper_fetch`, `code_exec`, `web_fetch`, `web_browse`, `fs_read`, `fs_write`, `memory_read`, `memory_write`.
  - `class CapabilitySet`: thin wrapper around `frozenset[str]` with `union`, `intersection`, `is_satisfied_by(declared: Iterable[str]) -> bool`. Hashable, equality-comparable.
  - `class CapabilityResolver`: holds a mapping `tool_name → CapabilitySet`. Method `for_tool(server: str, tool: str) -> CapabilitySet` (raises `ToolNotFound` if unmapped). The mapping is built at server-registration time from each `ToolDescriptor.capabilities`.

- [ ] **Step 3 — write unit tests** (`test_capabilities.py`):
  - `CapabilitySet` membership, union, equality.
  - `CapabilityResolver.for_tool` raises on unknown.
  - All capabilities in the seed taxonomy are unique.

**Verification:**
```bash
uv run ruff check agentlabx/mcp/ tests/unit/mcp/
uv run mypy --strict agentlabx/mcp/ tests/unit/mcp/
uv run pytest tests/unit/mcp/test_capabilities.py -q
```

---

## Task 2: Redaction primitive

**Files:**
- Create: `agentlabx/mcp/redaction.py`
- Create: `tests/unit/mcp/test_redaction.py`

- [ ] **Step 1 — redaction.py.** Pure functions (no I/O, no logging):
  - `SECRET_KEYS: frozenset[str] = frozenset({"api_key", "apikey", "x-api-key", "token", "access_token", "refresh_token", "password", "passphrase", "secret", "authorization", "bearer"})`
  - `def redact_args(args: Mapping[str, JSONValue]) -> dict[str, JSONValue]` — recursively walk; if a key (case-insensitive) is in `SECRET_KEYS`, replace its value with `"***"` (preserve type as string sentinel). Lists/tuples walked element-wise.
  - `def redact_text(text: str, slots: Iterable[str]) -> str` — replaces any literal occurrence of a slot value with `"***"`. Used to scrub stderr/stdout snippets the host captures from the subprocess. Slots are the actual decrypted secret values currently in flight; caller passes them in.
  - Import `JSONValue` from `agentlabx.core.json_types` (landed in prereqs). Do not re-define it here.

- [ ] **Step 2 — tests:** verify nested dict redaction, list-in-dict, mixed case keys, slot-value redaction inside arbitrary text, idempotency of `redact_args(redact_args(x)) == redact_args(x)`.

**Verification:**
```bash
uv run pytest tests/unit/mcp/test_redaction.py -q
```

---

## Task 3: SQLite schema + v4→v5 migration

**Files:**
- Modify: `agentlabx/db/schema.py` — add `mcp_servers` table.
- Modify: `agentlabx/db/migrations.py` — add `_migrate_v4_to_v5`, bump `CURRENT_SCHEMA_VERSION = 5`.
- Create: `tests/integration/mcp/__init__.py`
- Add: a migration round-trip test in `tests/integration/test_db_migrations.py` (extend the existing test file).

- [ ] **Step 1 — schema.** The v4→v5 migration adds **two** tables (`mcp_servers` for Task 4, `memory_entries` for Task 8 — bundled into one migration so A3 boots leave the DB at a single consistent version). Also add `admin_configs(slot TEXT PRIMARY KEY, value_encrypted TEXT NOT NULL, created_at TEXT NOT NULL)` required by `SlotResolver` for admin-scope slot storage (prereq).

  ```
  mcp_servers(
      id TEXT PRIMARY KEY,                -- uuid
      owner_id TEXT REFERENCES users(id) ON DELETE CASCADE,  -- NULL = admin scope
      name TEXT NOT NULL,                 -- per-scope unique
      scope TEXT NOT NULL,                -- 'user' | 'admin'
      transport TEXT NOT NULL,            -- 'stdio' | 'http' | 'inprocess'
      command_json TEXT,                  -- JSON-encoded list[str], NULL unless transport='stdio'
      url TEXT,                           -- NULL unless transport='http'
      inprocess_key TEXT,                 -- NULL unless transport='inprocess'; names an in-process factory (e.g. 'memory_server')
      env_slot_refs_json TEXT NOT NULL,   -- JSON list of credential slot names (resolved at launch via SlotResolver — see cross-cutting prereqs)
      declared_capabilities_json TEXT NOT NULL,  -- JSON list[str]
      enabled INTEGER NOT NULL DEFAULT 1,
      created_at TEXT NOT NULL,
      UNIQUE(scope, owner_id, name)
  )
  ```
  Index `idx_mcp_servers_owner` on `(owner_id, enabled)`.

  ```
  memory_entries(
      id TEXT PRIMARY KEY,              -- uuid
      category TEXT NOT NULL,           -- freeform tag from §3.3.5
      body TEXT NOT NULL,
      source_run_id TEXT,               -- NULL until Stage B links runs
      created_by TEXT REFERENCES users(id) ON DELETE SET NULL,
      created_at TEXT NOT NULL
  )
  ```
  Index `idx_memory_entries_category` on `(category)` to support Task 8's `memory.search` LIKE filter.

- [ ] **Step 2 — migration.** Add `_migrate_v4_to_v5` in `agentlabx/db/migrations.py` following the same table-exists-guard pattern A1's `_migrate_v3_to_v4` (`drop_token_revoked`) used — check `PRAGMA table_info` / `sqlite_master` before applying the DDL, so re-running the migration is a no-op. Bump `CURRENT_SCHEMA_VERSION` from `4` to `5`. (A2 did not ship a migration; v3→v4 is the correct precedent.)

- [ ] **Step 3 — round-trip test.** Open a fresh DB at v4, run migrations, assert `schema_version == 5` and the table is queryable.

**Verification:**
```bash
uv run pytest tests/integration/test_db_migrations.py -q
```

---

## Task 4: Server registry (SQLite persistence layer)

**Files:**
- Create: `agentlabx/mcp/registry.py`
- Create: `tests/unit/mcp/test_registry.py`

- [ ] **Step 1 — registry.py.** Class `ServerRegistry`:
  - Constructor: `(session_factory: async_sessionmaker[AsyncSession])`.
  - `async def register(spec: MCPServerSpec, owner_id: str | None) -> RegisteredServer` — INSERT; raises `RegistrationConflict` on UNIQUE violation (catch `sqlalchemy.exc.IntegrityError`, narrow).
  - `async def list_visible_to(user_id: str) -> list[RegisteredServer]` — admin-scope (owner_id IS NULL) UNION user's own (owner_id = user_id). Tools field returns `()` here — that's filled by the host at runtime, the registry only persists the spec.
  - `async def get(server_id: str) -> RegisteredServer | None`.
  - `async def delete(server_id: str, requester_id: str, requester_is_admin: bool) -> bool` — admin can delete admin-scope; user can delete own; returns True iff a row was deleted.
  - `async def set_enabled(server_id: str, enabled: bool) -> None`.

- [ ] **Step 2 — tests** (per-user fixture builds two users):
  - User A registers → User B's `list_visible_to` does not see it.
  - Admin-scope server visible to both A and B.
  - `RegistrationConflict` on duplicate `(scope, owner, name)`.
  - User cannot delete admin-scope without admin flag.

**Verification:**
```bash
uv run pytest tests/unit/mcp/test_registry.py -q
```

---

## Task 5: Transport launchers + MCPHost lifecycle

**Files:**
- Create: `agentlabx/mcp/transport.py`
- Create: `agentlabx/mcp/host.py`
- Create: `tests/fakes/echo_mcp_server.py`
- Create: `tests/integration/mcp/test_host_lifecycle.py`

- [ ] **Step 1 — `tests/fakes/echo_mcp_server.py`.** A standalone Python script that uses the `mcp` SDK's server primitives to expose two tools: `echo(message: str) -> str` and `boom() -> NoReturn` (raises). Runs over stdio. This is our deterministic dispatcher target — every dispatcher / host integration test launches this script via `python -m tests.fakes.echo_mcp_server`. Keep dependencies to the `mcp` SDK only.

- [ ] **Step 2 — transport.py.** Three thin wrappers over the SDK, all exposing the same `async def open(self) -> AsyncContextManager[ClientSession]` shape so `MCPHost.start` can dispatch on `spec.transport` uniformly:
  - `class StdioLauncher`: `(command: tuple[str, ...], env: dict[str, str])` → async context manager yielding an open `ClientSession`. Internally uses `mcp.client.stdio.stdio_client`.
  - `class StreamableHTTPLauncher`: `(url: str, headers: dict[str, str])` → async context manager yielding `ClientSession`. Uses the SDK's streamable-HTTP client.
  - `class InProcessLauncher`: `(inprocess_key: str, factories: Mapping[str, Callable[[], mcp.server.Server]])` → async context manager yielding `ClientSession` wired via `mcp.shared.memory.create_connected_server_and_client_streams`. **`MCPHost` owns the master factory registry** (passed to its constructor as `inprocess_factories`); each time the host constructs an `InProcessLauncher` in `start()`, it hands the same registry reference in. The registry starts with `{"memory_server": memory_server.build_server}` (Task 8 provides the value; Task 7 Step 3 wires the dict together at lifespan startup) and is extensible for future in-process bundles by extending that dict at construction time.
  - All three raise `ServerStartupFailed` if the underlying open fails (catch the SDK's specific error, narrow — do NOT bare-except).

- [ ] **Step 3 — host.py.** `class MCPHost`:
  - Constructor: `(registry: ServerRegistry, slot_resolver: SlotResolver, event_bus: EventBus, inprocess_factories: Mapping[str, Callable[[], mcp.server.Server]])`. The `SlotResolver` (introduced in the cross-cutting prereqs) materialises `env_slot_refs` into actual env-var values at launch for both user-scope (per-user secrets) and admin-scope (process env or admin-stored slots) paths. `inprocess_factories` is threaded into `InProcessLauncher` when `transport=="inprocess"`.
  - State: `_handles: dict[str, _Handle]` keyed by server id. `_Handle` = `(session: ClientSession, tools: tuple[ToolDescriptor, ...], exit_stack: contextlib.AsyncExitStack, slot_values: tuple[str, ...])`. The `AsyncExitStack` owns the launcher's async context manager and (if needed) an inner `anyio` task group — entering them inside the stack keeps the session alive beyond the scope of `start()` and guarantees ordered teardown in `stop()`.
  - `async def start(server: RegisteredServer, owner_id: str | None) -> RegisteredServer` — builds an `AsyncExitStack`, enters the appropriate launcher's context manager on the stack (which yields a live `ClientSession`), calls `session.list_tools()`, snapshots descriptors with capabilities mapped per Step 4, stores the stack+session in `_handles`, emits `mcp.server.started`, returns a fresh `RegisteredServer` with `tools` filled. If any step fails, the partially-built stack is rolled back via `await stack.aclose()` before re-raising as `ServerStartupFailed`.
  - `async def stop(server_id: str) -> None` — looks up the handle, `await handle.exit_stack.aclose()` (which tears down session + launcher + any tasks), removes the handle, emits `mcp.server.stopped`.
  - `async def stop_all() -> None` — for graceful shutdown.
  - `tools_for(server_id: str) -> tuple[ToolDescriptor, ...]` — sync read.
  - `async def call(server_id: str, tool: str, args: dict[str, JSONValue]) -> ToolCallResult` — looks up the session, calls `session.call_tool(tool, args)`, adapts the returned `CallToolResult` into `ToolCallResult`. Raises `ServerNotRunning` / `ToolNotFound`. Any SDK-level invocation exception is wrapped in a new `ToolExecutionFailed(server, tool, underlying: BaseException)` exception (add to Task 1's exception list) and re-raised — the dispatcher catches this to emit `mcp.tool.error`.
  - `def slot_values_for(server_id: str) -> tuple[str, ...]` — sync accessor returning the decrypted secret values currently in flight for a given handle (sourced from `_Handle.slot_values`). Used by `ToolDispatcher.invoke` to scrub result text. Raises `ServerNotRunning` if the handle is absent.

- [ ] **Step 4 — capability mapping at start time.** A bundled spec declares `declared_capabilities` for the *server*; per-tool capability is by default the union of the server's declared caps. A tool whose schema explicitly opts in via a recognised metadata key (`x-agentlabx-capabilities`) overrides this. **Canonical source of truth for gating is `ToolDescriptor.capabilities`** — the dispatcher never consults `MCPServerSpec.declared_capabilities` at invocation time. The spec's field is the *seed* used at registration to populate tool descriptors; the DB column persists the spec as a mirror. On conflict, the dispatcher trusts the tool descriptor.

  **SDK-round-trip verification is owned by this step** (Task 5, not Task 8): before implementing the override, write a unit test that registers a fake MCP server whose tool schema contains `x-agentlabx-capabilities`, calls `session.list_tools()`, and asserts the key survives. If the MCP SDK strips unknown schema keys (Pydantic strict mode), adopt a name-prefix convention as the fallback mechanism — document the chosen mechanism here, and Task 8 Step 3 inherits whichever was picked. Either way, this decision must be made *before* Task 8 starts, not discovered during memory-server implementation.

- [ ] **Step 5 — `test_host_lifecycle.py`.** Boot the echo server, list tools (assert `echo` and `boom` present), call `echo("hi")` → `ToolCallResult` whose first `TextContent.text == "hi"`, call `boom()` and assert `ToolExecutionFailed` is raised with a non-None `underlying`. Stop and re-start the same server (re-entering `start` with the same id succeeds after `stop`). Verify `mcp.server.started`/`mcp.server.stopped` events were emitted by subscribing a recorder to the bus.

**Verification:**
```bash
uv run pytest tests/integration/mcp/test_host_lifecycle.py -q
uv run mypy --strict agentlabx/mcp/transport.py agentlabx/mcp/host.py
```

---

## Task 6: Tool dispatcher + capability gating + tracing

**Files:**
- Create: `agentlabx/mcp/dispatcher.py`
- Create: `tests/unit/mcp/test_dispatcher_gating.py`
- Create: `tests/integration/mcp/test_dispatcher_e2e.py`

- [ ] **Step 1 — dispatcher.py.** `class ToolDispatcher`:
  - Constructor: `(host: MCPHost, event_bus: EventBus, allow_list_provider: AllowListProvider)`.
  - `class AllowListProvider(Protocol)`: single method `def allowed(self, request: CapabilityRequest) -> bool`. A3 ships `class AlwaysAllow(AllowListProvider)` (returns True) — A8 will inject the real per-stage/per-agent allow-list. Keep this seam clean so A8 is a one-line swap.
  - `async def resolve_capability(capability: str, visible_servers: Iterable[RegisteredServer]) -> tuple[RegisteredServer, ToolDescriptor]` — picks the *first* server whose tool advertises the capability. Deterministic ordering: sort by `(scope=='admin' first, name asc)`. Raises `CapabilityRefused` if none.
  - `async def invoke(stage: str, agent: str, capability: str, server_id: str, tool: str, args: dict[str, JSONValue]) -> ToolCallResult` — checks `allow_list_provider.allowed(...)`; on refusal emit `mcp.tool.refused` and raise `CapabilityRefused`. On allow: pulls `slot_values = self._host.slot_values_for(server_id)` directly (no caller plumbing), calls `self._host.call(server_id, tool, args)`, emits `mcp.tool.called` with `redact_args(args)` + `redact_text(<content stringified via `"\n".join(c.text for c in result.content if isinstance(c, TextContent))`>, slot_values)`. On `ToolExecutionFailed`, emit `mcp.tool.error` with `error_type=type(exc.underlying).__name__` (no traceback in payload) and re-raise. Returns the `ToolCallResult` unchanged.
  - The dispatcher does NOT consult the registry directly — its caller passes the resolved set in. This keeps the dispatcher pure for unit tests.

- [ ] **Step 2 — gating unit test.** Use a `FakeHost` (just a Protocol stand-in) and an `AllowListProvider` that denies one specific capability. Assert refusal event fires and `CapabilityRefused` is raised. Assert allowed call emits `mcp.tool.called` with redacted `api_key` arg.

- [ ] **Step 3 — e2e dispatcher test.** Wire the real `MCPHost` + echo server + `ToolDispatcher` + `AlwaysAllow`. Resolve capability `echo` → tool `echo`, invoke, assert success event. Trigger `boom()` and assert `mcp.tool.error` event with `error_type` payload field.

**Verification:**
```bash
uv run pytest tests/unit/mcp/test_dispatcher_gating.py tests/integration/mcp/test_dispatcher_e2e.py -q
```

---

## Task 7: REST surface — `/api/mcp/*`

**Files:**
- Create: `agentlabx/mcp/api_models.py` (Pydantic request/response models — keep separate from internal dataclasses).
- Create: `agentlabx/server/routers/mcp.py`
- Modify: `agentlabx/server/app.py` — register the router; instantiate `MCPHost` + `ToolDispatcher` in startup; `await host.stop_all()` in shutdown.
- Create: `tests/integration/mcp/test_router_register_invoke.py`

- [ ] **Step 1 — api_models.py.** `MCPServerCreateRequest`, `MCPServerResponse`, `MCPToolResponse`, `ToolInvokeRequest`, `ToolInvokeResponse`. No `Any`. JSON arg payloads typed as `dict[str, JSONValue]` at the boundary (using the recursive union from `agentlabx.mcp.protocol`); Pydantic validates shape, the dispatcher re-validates against the tool's `input_schema` before invocation.

- [ ] **Step 2 — router endpoints (all behind the existing session auth):**
  - `GET  /api/mcp/servers` → list visible to caller. Includes a `tools: list[MCPToolResponse]` field per server (live snapshot from host if started, else `[]`).
  - `POST /api/mcp/servers` → register + start. Body validates one-of `command` / `url`. Admin scope requires admin capability — reject with 403 otherwise. Returns the started `MCPServerResponse`.
  - `GET  /api/mcp/servers/{id}` → detail (404 if not visible).
  - `PATCH /api/mcp/servers/{id}` → toggle `enabled`. On enable: if the server has a running host handle, no-op; otherwise call `MCPHost.start` (same code path as first-start from boot — `start` is idempotent w.r.t. the handle registry). On disable: if running, `MCPHost.stop`; otherwise no-op. Either way, update the DB `enabled` column and return the updated resource.
  - `DELETE /api/mcp/servers/{id}` → stop + remove (owner or admin).
  - `GET  /api/mcp/tools` → flat aggregate of all tools across visible servers (frontend in Layer C uses this for the agent allow-list editor).
  - `POST /api/mcp/servers/{id}/tools/{tool}/invoke` → debug-only manual invocation. **Gating for A3: caller must be the server's owner or an admin** — that is the entire access check. The "could-the-user-have-invoked-this-via-a-stage" logic belongs to A8's per-agent allow-list and is explicitly out of scope here. The debug endpoint uses the same `AlwaysAllow` dispatcher path as stage-driven calls, so the trace events (`mcp.tool.called`/`refused`/`error`) are emitted identically. Body: `ToolInvokeRequest`.

- [ ] **Step 3 — startup wiring.** In `app.py` lifespan, the ordering is load-bearing. Sequence:
  1. Run DB migrations (already done by A1's startup). After migrations return, re-read schema version by inlining a `SELECT version FROM schema_migrations ORDER BY version DESC LIMIT 1` (no new helper needed in `migrations.py`) and assert `== 5`; raise on mismatch so boot fails loudly if the migration regressed.
  2. Build `SlotResolver` (prereq component).
  3. **Discover bundles** via `importlib.metadata.entry_points(group="agentlabx.mcp_bundles")` into an in-memory list (no DB writes).
  4. Build `inprocess_factories: dict[str, Callable[[], mcp.server.Server]]` by iterating discovered bundles that declare `transport="inprocess"` and collecting their `build_server` factories. For A3 this yields `{"memory_server": memory_server.build_server}`; the pattern extends automatically as future in-process bundles are added.
  5. Construct `ServerRegistry`, `MCPHost(registry, slot_resolver, event_bus, inprocess_factories)`, `ToolDispatcher(host, event_bus, AlwaysAllow())`.
  6. **Seed admin-scope bundle registrations idempotently on every startup** (not "first boot only" — the seed step is a reconcile, not a one-shot): for each discovered bundle, `INSERT ... ON CONFLICT(scope, owner_id, name) DO UPDATE SET ...` a row with `scope='admin'`, `owner_id=NULL`, `enabled` set per Task 9's rules. For required-slot bundles, consult `SlotResolver.resolve(owner_id=None, slot=<each ref>)` — if any required slot resolves to `None`, persist with `enabled=0`; if all resolve, `enabled=1`. Admin-scope rows are owned by "the installation," not by a specific user, so they are seedable before any admin identity exists; a non-admin user simply cannot *mutate* them (Task 7's POST with `scope=admin` returns 403). **This supersedes the "first server start" wording at the bottom of Task 9 — the canonical seeding policy is "idempotent every startup" defined here.**
  7. **Start all enabled servers** from the registry (fire-and-forget per server; failures emit `mcp.server.startup_failed` and continue — one bad bundle does not block boot).
  8. On shutdown, `await host.stop_all()`.

  User-scope bundle registrations are never auto-seeded — they are created on demand via `POST /api/mcp/servers` by the logged-in user. The admin-identity concern only applies to *mutating* admin-scope rows, and Task 7's router enforces that via session auth, not via startup ordering.

- [ ] **Step 4 — router test.** Full path: register an echo-server entry via REST, GET the server list (assert tools present), invoke the `echo` tool via the debug endpoint, DELETE, assert subsequent GET 404. Repeat as user B and verify isolation. Try to register an admin-scope server as a non-admin user — assert 403.

**Verification:**
```bash
uv run pytest tests/integration/mcp/test_router_register_invoke.py -q
```

---

## Task 8: Memory MCP server (in-process, AgentLabX-owned)

**Why this one is custom:** the data model (entries with `category`, `source_run`, `endorsements`, `freshness`, `provenance`) is dictated by §3.3.5. No upstream covers it. **Scope for A3:** *basic CRUD only* — the curator-governance layer (§3.3.5 freshness signals, supersede/retire, multi-curator endorsements) is deferred to Stage C4 per the SRS table.

**Files:**
- Create: `agentlabx/mcp/bundles/memory_server.py`
- (`memory_entries` schema + v4→v5 migration already landed in Task 3 — no schema/migration changes in this task.)
- Create: `tests/unit/mcp/test_memory_server_unit.py`

- [ ] **Step 1 — memory_server.py.** Use the `mcp` SDK's `Server` primitives. Tools:
  - `memory.create(category: str, body: str, source_run_id: str | None) -> {"id": str}`.
  - `memory.get(id: str) -> {"id": str, "category": str, "body": str, ...}`.
  - `memory.search(query_text: str, category_filter: str | None, max_results: int) -> [{...}, ...]` — A3 implementation is **plain SQLite LIKE-based search**; the embedded vector index is a C4 addition and the tool signature is forward-compatible.
  - `memory.delete(id: str) -> {"deleted": bool}` (admin or `memory_curator` only — but the gate sits in the dispatcher's allow-list, not inside the server; the server trusts its host).

- [ ] **Step 2 — launch model.** The memory server runs **in-process via stdio over an in-memory pipe** rather than as a subprocess (the SDK supports this with `mcp.shared.memory.create_connected_server_and_client_streams`). The bundle's launch spec returns `transport="inprocess"` with `inprocess_key="memory_server"`; a new `InProcessLauncher` in `agentlabx/mcp/transport.py` looks the key up in a registry of `MCPServer` factories (initially just `{"memory_server": memory_server.build_server}`) and wires the in-memory streams to an MCP `ClientSession`. This preserves the SRS §3.3.5 promise that switching to a remote memory server is config-only: change the bundle's spec from `inprocess` to `stdio`/`http`, same `ClientSession` on the host side. The `x-agentlabx-capabilities` per-tool override path **must be exercised by the memory server's unit tests** (see Step 4) since `memory_read`/`memory_write` depend on it — confirm the MCP SDK round-trips unknown schema keys through `list_tools()`, and if not, fall back to a name-prefix convention (`memory.read_*`, `memory.write_*`) documented here.

- [ ] **Step 3 — declared capabilities.** `("memory_read", "memory_write")` at the server level; `memory.search`/`memory.get` map to `memory_read`, `memory.create`/`memory.delete` to `memory_write` via the `x-agentlabx-capabilities` metadata key from Task 5 Step 4.

- [ ] **Step 4 — unit tests** call the tools directly (no transport) for arithmetic correctness; integration smoke happens in Task 10.

**Verification:**
```bash
uv run pytest tests/unit/mcp/test_memory_server_unit.py -q
```

---

## Task 9: Bundled launch specs (adopt-over-build for the other five)

**Files:** five small modules under `agentlabx/mcp/bundles/`.

**Each module exports a single `def spec() -> MCPServerSpec`.** They do *not* implement tool logic — they are launch descriptors pointing at upstream packages.

- [ ] **filesystem.py** → official `@modelcontextprotocol/server-filesystem` via `npx -y @modelcontextprotocol/server-filesystem <workspace-root>`. Capabilities `("fs_read", "fs_write")`. Workspace root is read from `AppSettings.workspace_root`.

- [ ] **arxiv.py** → `blazickjp/arxiv-mcp-server` via `uvx arxiv-mcp-server`. Capabilities `("paper_search", "paper_fetch")`. **Fallback:** if the user prefers a different upstream, the spec is overridable via env `AGENTLABX_BUNDLE_ARXIV_COMMAND`.

- [ ] **semantic_scholar.py** → community `semanticscholar-mcp` via `uvx semanticscholar-mcp` (verify exact package name during implementation; if unmaintained, drop to `arxiv` only and emit a startup warning rather than crash). Capabilities `("paper_search",)`. Optional API key slot `user:key:semantic_scholar`.

- [ ] **browser.py** → official `mcp-server-fetch` (Anthropic reference server, published on PyPI) launched via `uvx mcp-server-fetch` — verify the package's exact invocation at implementation time (some versions use `python -m mcp_server_fetch`; if `uvx` can't resolve the console script, fall back to `uvx --from mcp-server-fetch python -m mcp_server_fetch`). Capabilities `("web_fetch",)`. **Note:** the SRS calls this `browser` for JS-rendered pages; full headless-browser (`web_browse`) is *out of scope for A3* — `mcp-server-fetch` covers `web_fetch` for the literature-review use case in B1, and a real puppeteer-backed bundle can ship later as an addendum bundle without changing the host.

- [ ] **code_execution.py** → **Docker-sandboxed Python runner**, matching SRS §4.2. `code_execution.py` is always the launch-spec module (a `def spec() -> MCPServerSpec`). The *implementation* has two possible shapes, decided at implementation time:
  - **Adopt path:** if a maintained upstream MCP server wraps a Docker-isolated Python runner (evaluate `mcp-run-python` and alternatives), `code_execution.py`'s spec points at it (`uvx <pkg>` or `npx <pkg>`) and **`code_execution_server.py` is NOT created** — remove it from the file tree in that case.
  - **Build path:** if no suitable upstream exists, create `agentlabx/mcp/bundles/code_execution_server.py` as an AgentLabX-owned MCP server (stdio subprocess, not in-process — execution is heavyweight) that shells out to `docker run --rm --network=none --memory=512m --cpus=1 --read-only --pids-limit=64 <image> python -c <code>` per call, with `<image>` pinned to a `python:3.12-slim` digest. `code_execution.py`'s spec then invokes this module via `python -m agentlabx.mcp.bundles.code_execution_server`.

  The decision is recorded in this bullet at implementation time; the file tree above reflects the build-path assumption and should be pruned if the adopt path is taken. Capabilities `("code_exec",)`. **Docker Engine is a required system dependency per the cross-cutting prereqs — ship running, not disabled.** Per the user's 2026-04-21 decision, the Docker sandbox is expected in A3 rather than deferred.

- [ ] Add an entry-point group `agentlabx.mcp_bundles` in `pyproject.toml` exposing all six bundles (`filesystem`, `arxiv`, `semantic_scholar`, `browser`, `code_execution`, `memory`). The host uses `importlib.metadata.entry_points(group="agentlabx.mcp_bundles")` at startup to discover them. **Third parties can ship additional bundles by registering this entry point — this satisfies NFR-5 for MCP bundles.**

- [ ] Admin-scope registrations are **seeded idempotently on every startup** by Task 7 Step 3 item 6 (not "first boot only" — every startup reconciles). Bundles whose required slots are unresolved are seeded with `enabled=0` and flip to `enabled=1` on the next startup after the user fills the slot (or via an admin-issued `PATCH`). This bullet is a cross-reference, not a separate action item.

**Verification:** structural only at this task — Task 10 covers the actual launch smoke.
```bash
uv run mypy --strict agentlabx/mcp/bundles/
uv run ruff check agentlabx/mcp/bundles/
```

---

## Task 10: Bundled-server smoke test + bootstrap audit

**Files:**
- Create: `tests/integration/mcp/test_bundled_smoke.py`
- Modify: `agentlabx/server/app.py` — add the bootstrap seeding logic from Task 9.

- [ ] **Step 1 — smoke test, one parameterised case per bundle.** Per the cross-cutting prereqs, `uvx`, `npx`, and Docker Engine are required system dependencies on every environment that runs integration tests — **no skipping on launcher absence**. Each case starts the server through the host, calls `tools/list`, asserts ≥1 tool present, asserts `mcp.server.started` was emitted, calls the cheapest read-only tool for that bundle (**exact tool name to be confirmed by the implementing engineer against the upstream package's `tools/list` output at implementation time — do not hard-code names from this plan**; for memory use `memory.search`, which AgentLabX owns), then tears down. Placeholder shapes to adapt: filesystem → a "read file" tool on the workspace `README.md`; fetch/browser → a "fetch URL" tool on a stable test URL (e.g. `https://example.com`); arxiv → a paper-search tool with a one-result cap; code_execution → a simple expression like `"print(1+1)"`. If `uvx`/`npx`/Docker is genuinely unavailable the test *fails* and the environment is misconfigured — skip only for the optional `semantic_scholar` API key slot (`pytest.skip(reason="SEMANTIC_SCHOLAR_API_KEY unset")`). Memory server case is in-process and always runs.

- [ ] **Step 2 — bootstrap audit.** Add a startup log line that summarises bundle status: e.g. `"MCP bundles: 7 registered, 6 started, 1 disabled (semantic_scholar: missing key)"`. Docker, `uvx`, and `npx` are required system deps (prereqs) — their absence is a misconfiguration, not a tolerated disabled state, and should surface as `mcp.server.startup_failed` per bundle, not as a silent "disabled" count. This is the operator's at-a-glance health check.

- [ ] **Step 3 — capability coverage assertion.** Add a backend invariant test: across the started bundles, every capability in `agentlabx.mcp.capabilities.SEED_CAPABILITIES` is provided by at least one server *or* explicitly marked in a `KNOWN_UNCOVERED_CAPABILITIES: frozenset[str]` constant in `capabilities.py`. For A3 that constant is `frozenset({"web_browse"})` (deferred to a future puppeteer/playwright bundle per the "Out of scope" section). The test iterates `SEED_CAPABILITIES - KNOWN_UNCOVERED_CAPABILITIES` and asserts each is served by ≥1 started bundle; CI fails on silent gaps.

**Verification:**
```bash
uv run pytest tests/integration/mcp/test_bundled_smoke.py -q
```

---

## Task 11: Final verification gate (the SRS A3 list)

- [ ] **Gate 1 — bundled servers.** `pytest tests/integration/mcp/test_bundled_smoke.py` passes. Memory, filesystem, browser (`web_fetch`), arxiv, and code-execution **must run** (launchers are required system deps). Skips are only acceptable for the optional `semantic_scholar` API-key slot case. The bundle package name is `browser.py` and its capability is `web_fetch` — do not rename to "fetch" elsewhere; the capability string is the durable identifier.
- [ ] **Gate 2 — runtime registration without restart.** `pytest tests/integration/mcp/test_router_register_invoke.py` passes; manually verify on the live dev server (port 8765) by registering the echo server via `curl` and immediately invoking it.
- [ ] **Gate 3 — capability gating.** `pytest tests/unit/mcp/test_dispatcher_gating.py tests/integration/mcp/test_dispatcher_e2e.py` passes; `mcp.tool.refused` event recorded.
- [ ] **Gate 4 — tracing + redaction.** Inspect emitted events from `test_dispatcher_e2e.py` and assert no plaintext slot value or `api_key` field appears in any event payload.
- [ ] **Gate 5 — per-user isolation.** `pytest tests/unit/mcp/test_registry.py tests/integration/mcp/test_router_register_invoke.py` passes (both contain isolation cases).
- [ ] **Gate 6 — types.** `uv run ruff check . && uv run mypy --strict agentlabx tests`.

- [ ] **Manual live-server check** (mirroring the A2 procedure):
  1. `uv run agentlabx serve` on `http://127.0.0.1:8765`.
  2. Log in as the admin test account (`whats2000mc@gmail.com` / `whats2000`).
  3. `GET /api/mcp/servers` — confirm the seeded bundles list.
  4. `POST /api/mcp/servers` registering a user-scope echo server (command: `("python", "-m", "tests.fakes.echo_mcp_server")`) — requires the dev server to be launched from the repo root so `tests/` is on `sys.path`; `uv run agentlabx serve` already satisfies this, but a future wheel-install path will not, so treat this as a dev-only manual check.
  5. `POST /api/mcp/servers/{id}/tools/echo/invoke {"args": {"message": "hello"}}` — confirm `"hello"` returned.
  6. Tail `<workspace>/events/audit.jsonl` and confirm the chain `mcp.server.started → mcp.tool.called → mcp.tool.refused (induced) → mcp.server.stopped`.

---

## Out of scope for A3 (explicitly deferred — do NOT add)

- **Frontend UI for MCP server management.** Layer C1 — the REST surface here is the contract C1 will consume.
- **Memory governance.** Curator approval, supersede/retire, freshness, vector index — Stage C4.
- **Per-stage capability allow-lists tied to agents.** A8 wires `ToolDispatcher.allow_list_provider` to a real per-agent/per-stage policy. A3 ships the seam (`AllowListProvider` Protocol + `AlwaysAllow`) so A8 is a one-line wiring change.
- **Full headless browser bundle** (`web_browse` capability). A3 ships `web_fetch` only via `mcp-server-fetch`. A puppeteer/playwright bundle is a future addendum bundle; no host changes required.
- **Further sandbox hardening of `code-execution`.** A3 ships a Docker-isolated runner (no network, memory/CPU limits, pinned image) per the user's 2026-04-21 decision. Additional hardening beyond that — seccomp profiles, gVisor/Kata, per-user resource quotas, egress-proxy allow-lists — is a future pass.

---

## Risks + mitigations

| Risk | Likelihood | Mitigation |
|------|------------|------------|
| `mcp` SDK API churn between releases | Med | Pin `mcp>=1.0,<2.0` in `pyproject.toml`; the host's surface area on top of the SDK is small (transport + session + list_tools + call_tool) so a future bump is ~one file. |
| Upstream bundles unmaintained or renamed | High | Each bundle reads command from an `AGENTLABX_BUNDLE_<NAME>_COMMAND` env override; users can swap upstreams without code changes. |
| Subprocess leaks on test failure | Med | All host integration tests use `anyio.create_task_group` + `MCPHost.stop_all()` in a fixture finalizer; CI runs with `pytest-timeout` to surface hangs. |
| Capability gate blocking legitimate calls during A3 (before A8) | Low | A3 ships `AlwaysAllow` as the default `AllowListProvider`; the gating events fire so we can observe traffic, but nothing is refused unless a test explicitly installs a denying provider. |
| Memory server schema collides with Layer B run-notes (A7) | Low | A3 memory entries are persistent, cross-run. A7 notes are per-run and live on a separate table (`run_notes`, designed in A7). Distinct table names; documented in §3.3.5. |
| Docker daemon unavailable in dev/CI | Med | Docker Engine is a required system dep (prereqs). Absence surfaces as `mcp.server.startup_failed` for the `code_execution` bundle and a failing `test_bundled_smoke.py::test_code_execution` — i.e. it fails loudly instead of silently disabling the capability. Document a one-line "install Docker Desktop or dockerd" check in the README troubleshooting section. |
| Code-execution sandbox escape or resource exhaustion | Med | First-pass defences: `--network=none`, `--memory=512m`, `--cpus=1`, `--rm`, image pinned by digest, no volume mounts. Hardening beyond this (seccomp, gVisor, per-user quotas, egress-proxy) is explicitly deferred (see Out of scope). Any caller-controlled arg path that could influence the docker invocation must go through an allow-list, never string interpolation. |

---

## Ordering note for the executing engineer

**Cross-cutting prereqs** (new `SlotResolver`, widened `Event.payload`) land before anything else — they are small, isolated, and unblock Tasks 5/6/7.

**Tasks 1–6 are the host core** and must land in order.

**Task 8 (memory server) depends on Task 3** — it extends the same v4→v5 migration created there, so Task 3 must be merged before Task 8 starts. Beyond that, Task 7 (REST) and Task 8 can run in parallel.

**Task 9 (bundle launch specs)** needs Tasks 1 + 5.

**Task 10** needs Tasks 7 + 8 + 9.

**Task 11** is the final verification pass.

When executing via `superpowers:subagent-driven-development`, each task above is one subagent assignment. Each subagent must run its task's verification block before reporting completion. A failing verification means the task is not complete — fix in the same subagent.
