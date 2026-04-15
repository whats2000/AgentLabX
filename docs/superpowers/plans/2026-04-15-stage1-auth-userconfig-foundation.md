# Stage 1 — Auth + Encrypted User Config Foundation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Ship an isolated foundation layer — default auto-login + pluggable OAuth (device flow) + Token authers, per-user encrypted API key storage in SQLite (Fernet + OS keyring), save-time API key validation, and a React/Vite/shadcn frontend settings panel.

**Architecture:** Backend FastAPI process wiring `crypto → storage → user → auth → server` layers, each in its own module with typed interfaces. Frontend Vite React app using shadcn/ui + Tailwind, talking to the backend via typed `fetch`. No pipeline / stages / agents.

**Tech stack:** Python 3.12 (FastAPI, Pydantic v2, SQLAlchemy async + aiosqlite, `cryptography` Fernet, `keyring`, `httpx`, LiteLLM passthrough, `respx`, pytest + pytest-asyncio, ruff with `ANN` rules). React 19 + TypeScript + Vite + shadcn/ui + Tailwind + TanStack Query + Vitest + Playwright.

**Reference:** [stage1-auth-userconfig-foundation-design.md](../specs/2026-04-15-stage1-auth-userconfig-foundation-design.md), [agentlabx-vision.md](../specs/2026-04-15-agentlabx-vision.md).

**Plan style:** This plan declares **contracts** (file boundaries, public interfaces, behaviour, tests). Implementer subagents own the **code** (how to satisfy the contract). Where a code shape is shown, it's an interface signature, not a finished implementation.

---

## Project-wide rules (all tasks, all subagents)

### Strict typing — enforced by ruff `ANN` family

- Every Python function (production AND tests) has typed parameters and a `-> ReturnType` annotation.
- `typing.Any` is disallowed (`ANN401`).
- **`object` is also disallowed** as a type annotation. Use a `Protocol`, `TypedDict`, Pydantic model, or concrete type / union.
- `**kwargs: Any` is disallowed. Use `TypedDict` or explicit kwargs.
- `typing.cast(Any, ...)` and `typing.cast(object, ...)` are disallowed.
- Frontend: `tsconfig.json` carries `strict: true`, `noImplicitAny: true`, `noUncheckedIndexedAccess: true`, `exactOptionalPropertyTypes: true`. No `any`. Narrow `unknown` before use.
- `pyproject.toml` has NO test-file exception that loosens `ANN001` / `ANN201`.
- CI gate: `uv run ruff check .` (backend) + `npm run lint && npx tsc --noEmit` (frontend) must pass on every commit.

### Commit discipline

- Targeted `git add <paths>` only. Never `git add .` or `-A`.
- One task = one commit (or one commit per sub-task if natural). Commit message format: `<type>(<scope>): <summary> (Stage 1 T<N>)`.
- Test passes + ruff passes BEFORE commit. No exceptions.

### Test requirements

- TDD per task: failing test → implement → passing test.
- Every test uses ephemeral SQLite (`tmp_path`) and the `fake_keyring` fixture (T3) — never touches the host keyring or a persistent DB.
- LLM tests use `MockLLMProvider` or `respx` HTTP mocking — never hit a live API.
- Coverage targets: 100% for `auth/`, `crypto/`, `user/`, `providers/storage/`; ≥85% elsewhere.

---

## File structure (locked in plan)

```
agentlabx/
├── crypto/{keyring,fernet}.py
├── providers/
│   ├── storage/{models,sqlite_backend}.py + migrations/001_initial.sql
│   └── llm/{base,mock_provider,litellm_provider,traced}.py
├── user/{config,store,validator}.py
├── auth/{user,auther,default_auther,token_auther,oauth_auther,providers,session}.py
├── core/{events,registry,config,cost}.py
├── server/
│   ├── {app,deps}.py
│   └── routes/{auth,user_config}.py
└── cli/main.py

config/providers.yaml
web/{package.json,tsconfig.json,vite.config.ts,tailwind.config.ts,components.json,index.html}
web/src/{main.tsx,App.tsx,index.css,lib/{api,types,queryClient}.ts,components/ui/*,features/{auth,settings}/*.tsx}
tests/{conftest.py, crypto/, providers/{storage,llm}/, user/, auth/, core/, server/, integration/}
web/tests/{unit/*, e2e/*}
```

Every `__init__.py` in this tree is empty (no re-exports). All imports are explicit.

---

## Part A — Project bootstrap

### Task 1 — Trim `pyproject.toml`

**Files:** `pyproject.toml`

**Contract:**
- Dependencies: `pydantic>=2`, `pydantic-settings>=2`, `pyyaml`, `litellm>=1.82`, `aiosqlite>=0.19`, `fastapi>=0.115`, `uvicorn[standard]`, `click`, `cryptography>=42`, `keyring>=25`, `httpx>=0.27`. Drop everything pipeline / stage related.
- Dev deps: `pytest>=8`, `pytest-asyncio>=0.24`, `pytest-cov`, `respx>=0.21`, `ruff>=0.4`.
- `[tool.ruff.lint]` selects `["E","F","I","N","W","UP","ANN","B","SIM","RET"]`, ignores `["ANN101","ANN102"]` only.
- **No `per-file-ignores` for tests.** Tests must satisfy `ANN001`/`ANN201`.
- `[tool.pytest.ini_options]` keeps `asyncio_mode = "auto"`.

**Acceptance:** `uv lock && uv sync --extra dev` succeeds; `uv run ruff check .` returns "All checks passed!" (no Python files yet).

**Commit:** `chore(stage1): trim deps + ruff ANN rules (Stage 1 T1)`

---

### Task 2 — Backend + tests directory scaffold

**Files:** All directories listed in the file structure section above. Every `__init__.py` is empty.

**Acceptance:** `uv run pytest --collect-only -q` reports `0 tests collected`, zero errors.

**Commit:** `chore(stage1): scaffold backend + tests packages (Stage 1 T2)`

---

### Task 3 — Shared `tests/conftest.py`

**Files:** `tests/conftest.py`, `tests/test_conftest_fixtures.py`

**Contract:**
- Public class `InMemoryKeyringBackend(keyring.backend.KeyringBackend)` — in-memory `dict[(service, username), password]`. Public so other test modules can import-and-type their `fake_keyring` fixture parameter.
- Fixture `tmp_path_sqlite(tmp_path) -> Path` — returns `tmp_path / "agentlabx-test.db"` (file does not yet exist).
- Fixture `fake_keyring() -> Iterator[InMemoryKeyringBackend]` — installs the in-memory backend; restores original on teardown.

**Acceptance:** smoke test asserts `tmp_path_sqlite` is a `Path` and `keyring.set_password / get_password` round-trips through the fake; ruff passes; both tests typed (`-> None`, `fake_keyring: InMemoryKeyringBackend`).

**Commit:** `test(stage1): shared conftest + InMemoryKeyringBackend (Stage 1 T3)`

---

## Part B — Crypto layer

### Task 4 — `agentlabx/crypto/keyring.py`

**Files:** `agentlabx/crypto/keyring.py`, `tests/crypto/test_keyring.py`

**Public interface:**
- `class MasterKeyError(Exception)`
- `def load_or_create_master_key(*, service: str, username: str, fallback_path: Path | None = None) -> bytes` — returns 32-byte master key. Generates on first call, retrieves on subsequent. If keyring backend raises `NoKeyringError` and `fallback_path` is provided, reads/writes a base64 key file (mode 0600 where supported).

**Acceptance tests:**
1. First call generates a 32-byte key and stores it.
2. Second call returns the same key.
3. `NoKeyringError` falls back to file at `fallback_path`; round-trips on second call.
4. Malformed stored key raises `MasterKeyError`.

**Commit:** `feat(crypto): OS-keyring master key + file fallback (Stage 1 T4)`

---

### Task 5 — `agentlabx/crypto/fernet.py`

**Files:** `agentlabx/crypto/fernet.py`, `tests/crypto/test_fernet.py`

**Public interface:**
- `class DecryptionError(Exception)`
- `class FernetCrypto` — constructor `__init__(*, master_key: bytes)` (raises `ValueError` if not 32 bytes); methods `encrypt(plaintext: bytes) -> bytes`, `decrypt(ciphertext: bytes) -> bytes` (raises `DecryptionError` on `InvalidToken`).

**Acceptance tests:**
1. Round-trip encrypt + decrypt.
2. Different keys cannot decrypt.
3. Empty bytes round-trip.
4. Invalid ciphertext raises `DecryptionError`.
5. Wrong key length raises `ValueError`.

**Commit:** `feat(crypto): Fernet wrapper (Stage 1 T5)`

---

### Task 6 — Crypto integration

**Files:** `tests/crypto/test_integration.py`

**Acceptance:** Two tests asserting `load_or_create_master_key()` produces a 32-byte key that drives `FernetCrypto` round-trips, and that two consecutive calls produce ciphertext that round-trips across "process boundaries" (re-instantiated `FernetCrypto`).

**Commit:** `test(crypto): keyring → Fernet integration (Stage 1 T6)`

---

## Part C — Storage layer

### Task 7 — `agentlabx/providers/storage/models.py`

**Files:** `agentlabx/providers/storage/models.py`, `tests/providers/storage/test_models.py`

**Public interface (frozen dataclasses + enum):**
- `class AutherType(str, Enum): DEFAULT="default"; OAUTH="oauth"; TOKEN="token"`
- `@dataclass(frozen=True) class UserRow: id, display_name, auther_type, created_at`
- `@dataclass(frozen=True) class UserConfigRow: user_id, api_keys_encrypted: bytes, default_model: str | None, updated_at`
- `@dataclass(frozen=True) class OAuthTokenRow: user_id, provider, access_token_encrypted: bytes, refresh_token_encrypted: bytes | None, expires_at: datetime | None, updated_at`
- `@dataclass(frozen=True) class AppStateRow: key: str, value: str`

**Acceptance:** Smoke tests instantiating each row, checking field access + enum values.

**Commit:** `feat(storage): typed row dataclasses (Stage 1 T7)`

---

### Task 8 — Migration `001_initial.sql`

**Files:** `agentlabx/providers/storage/migrations/001_initial.sql`

**Contract:** SQL creating tables `users`, `user_configs`, `oauth_tokens`, `app_state` matching schemas in spec §5; `PRAGMA foreign_keys = ON`; FK `ON DELETE CASCADE` from `user_configs.user_id` and `oauth_tokens.user_id` to `users.id`; `INSERT OR IGNORE` seed of `(schema_version, "1")` into `app_state`.

**Acceptance:** No tests for the SQL alone — exercised via Task 9.

**Commit:** `feat(storage): migration 001 initial schema (Stage 1 T8)`

---

### Task 9 — `agentlabx/providers/storage/sqlite_backend.py`

**Files:** `agentlabx/providers/storage/sqlite_backend.py`, `tests/providers/storage/test_sqlite_backend.py`

**Public interface:**
- `CURRENT_SCHEMA_VERSION: int = 1`
- `class SchemaVersionMismatchError(Exception)`
- `class SQLiteBackend`:
  - `__init__(*, db_path: Path)`
  - `async def initialize() -> None` — opens connection, enables FK, applies migrations, validates schema_version == `CURRENT_SCHEMA_VERSION` (raises `SchemaVersionMismatchError` if higher or lower)
  - `async def close() -> None`
  - `async def get_schema_version() -> int`, `async def set_schema_version(int) -> None`
  - Users CRUD: `upsert_user(UserRow)`, `get_user(id) -> UserRow | None`, `list_users() -> list[UserRow]`, `delete_user(id) -> None`
  - User configs: `upsert_user_config(UserConfigRow)`, `get_user_config(user_id) -> UserConfigRow | None`
  - OAuth tokens: `upsert_oauth_token(OAuthTokenRow)`, `get_oauth_token(user_id) -> OAuthTokenRow | None`
  - App state: `get_app_state(key) -> str | None`, `set_app_state(key, value) -> None`

**Acceptance tests:**
1. `initialize()` creates tables and seeds `schema_version=1`.
2. User CRUD round-trip + `list_users` + `delete_user`.
3. UserConfig CRUD round-trip.
4. OAuthToken CRUD round-trip.
5. AppState CRUD round-trip + missing key returns `None`.
6. FK cascade: deleting a user removes its `user_configs` row.
7. Initializing against a DB whose `schema_version > CURRENT_SCHEMA_VERSION` raises `SchemaVersionMismatchError`.

**Commit:** `feat(storage): async SQLite backend + migration runner (Stage 1 T9)`

---

## Part D — User config layer

### Task 10 — `agentlabx/user/config.py`

**Files:** `agentlabx/user/config.py`, `tests/user/test_config.py`

**Public interface:**
- `@dataclass(frozen=True) class UserConfig: user_id: str; api_keys: dict[str, str]; default_model: str | None; updated_at: datetime | None`

**Acceptance:** Field round-trip + frozen behaviour assertion.

**Commit:** `feat(user): UserConfig dataclass (Stage 1 T10)`

---

### Task 11 — `agentlabx/user/store.py`

**Files:** `agentlabx/user/store.py`, `tests/user/test_store.py`

**Public interface:**
- `class UserConfigStore`:
  - `__init__(*, backend: SQLiteBackend, crypto: FernetCrypto)`
  - `async def save(cfg: UserConfig) -> UserConfig` — stamps `updated_at`, encrypts `api_keys` (JSON-serialized) into the row blob.
  - `async def load(user_id: str) -> UserConfig | None`

**Acceptance tests:**
1. Save then load returns matching `UserConfig` with timestamp.
2. Load missing user returns `None`.
3. Encrypted blob in storage does NOT contain plaintext key string.
4. Overwriting updates `updated_at` monotonically.

**Commit:** `feat(user): UserConfigStore encrypted at rest (Stage 1 T11)`

---

### Task 12 — `agentlabx/user/validator.py`

**Files:** `agentlabx/user/validator.py`, `tests/user/test_validator.py`

**Public interface:**
- `class ValidationStatus(str, Enum): VALID="valid"; INVALID="invalid"; UNVERIFIED="unverified"`
- `@dataclass(frozen=True) class ValidationResult: provider: str; status: ValidationStatus; detail: str | None`
- `async def probe_provider(provider: str, api_key: str) -> ValidationResult` — registry of probes for `gemini`, `anthropic`, `openai`. Each probe: 200 → VALID; 401/403 → INVALID; network error → UNVERIFIED. Unknown provider → UNVERIFIED with detail mentioning unknown.

**Acceptance tests (with `respx`):** valid/invalid/network-error/unknown-provider for at least Gemini.

**Commit:** `feat(user): save-time API key validator (Stage 1 T12)`

---

## Part E — Auth core

### Task 13 — `agentlabx/auth/user.py`

**Files:** `agentlabx/auth/user.py`, `tests/auth/test_user.py`

**Public interface:**
- `@dataclass(frozen=True) class User: id; display_name; auther_type: AutherType; created_at`
- Class methods `from_row(UserRow) -> User` and `to_row() -> UserRow` (round-trip).

**Acceptance:** Field round-trip + `from_row`/`to_row` round-trip.

**Commit:** `feat(auth): User dataclass (Stage 1 T13)`

---

### Task 14 — `agentlabx/auth/auther.py`

**Files:** `agentlabx/auth/auther.py` (no tests — protocol only).

**Public interface:**
- `@runtime_checkable class Auther(Protocol)`:
  - `name: str`
  - `async def ensure_bootstrap() -> User` — idempotent; ensures at least one user exists for this auther and returns the user to treat as current post-bootstrap.

**Acceptance:** ruff passes.

**Commit:** `feat(auth): Auther protocol (Stage 1 T14)`

---

### Task 15 — `agentlabx/auth/default_auther.py`

**Files:** `agentlabx/auth/default_auther.py`, `tests/auth/test_default_auther.py`

**Public interface:**
- `class DefaultAuther`:
  - `name: str = "default"`, `USER_ID: str = "local"`
  - `__init__(*, backend: SQLiteBackend)`
  - `async def ensure_bootstrap() -> User` — creates `id="local", display_name="Local User", auther_type=DEFAULT` if absent; returns the User.

**Acceptance tests:** first bootstrap creates user; second bootstrap returns same user (no duplicate); `name == "default"`.

**Commit:** `feat(auth): DefaultAuther single-user bootstrap (Stage 1 T15)`

---

### Task 16 — `agentlabx/auth/session.py`

**Files:** `agentlabx/auth/session.py`, `tests/auth/test_session.py`

**Public interface:**
- `LAST_ACTIVE_KEY: str = "last_active_user_id"`
- `class AuthSession`:
  - `__init__(*, backend: SQLiteBackend)`
  - `async def get_current() -> User | None` — reads `app_state.last_active_user_id`; returns `None` if unset, empty, or pointing at a deleted user (clears stale pointer in that case).
  - `async def set_current(user_id: str) -> None` — raises `ValueError` if the user does not exist.

**Acceptance tests:** empty → None; set + get returns user; unknown id raises; swap between users; deleted user resets pointer to None on next `get_current`.

**Commit:** `feat(auth): AuthSession persistent current-user pointer (Stage 1 T16)`

---

## Part F — Authers continued

### Task 17 — `config/providers.yaml` + `agentlabx/auth/providers.py`

**Files:** `config/providers.yaml`, `agentlabx/auth/providers.py`, `tests/auth/test_providers.py`

**Contract — `providers.yaml` shipped shape:**
- Top-level `providers:` list. Each entry: `name`, `display_name`, `client_id` (empty string by default = hidden), `device_code_url`, `token_url`, `userinfo_url`, `scopes: [str]`.
- Ship two entries (GitHub + Google) with empty `client_id` and correct device-flow endpoints.

**Public interface (`providers.py`):**
- `@dataclass(frozen=True) class ProviderConfig: name; display_name; client_id; device_code_url; token_url; userinfo_url; scopes: list[str]`
- `class ProviderNotConfiguredError(Exception)`
- `def load_providers(path: Path) -> list[ProviderConfig]` — returns empty list if file missing; filters out entries with empty `client_id`.
- `def get_provider_or_raise(providers: list[ProviderConfig], name: str) -> ProviderConfig`

**Acceptance tests:** loads non-empty entries; skips empty `client_id`; missing file → empty list; `get_provider_or_raise` raises on unknown.

**Commit:** `feat(auth): OAuth provider loader + shipped providers.yaml (Stage 1 T17)`

---

### Task 18 — `agentlabx/auth/token_auther.py`

**Files:** `agentlabx/auth/token_auther.py`, `tests/auth/test_token_auther.py`

**Public interface:**
- `class TokenValidationError(Exception)`
- `class TokenAuther`:
  - `name: str = "token"`
  - `__init__(*, backend: SQLiteBackend)`
  - `async def register_token(*, token: str, display_name: str) -> User` — `user_id = "token:" + sha256(token)[:16]`. Empty token or display_name → `TokenValidationError`. Re-registering the same token returns the same id; updates display_name.
  - `async def ensure_bootstrap() -> User` — raises `RuntimeError` (auther is interactive; no implicit bootstrap).

**Acceptance tests:** register creates user; id is hash-derived; empty inputs rejected; idempotent re-register updates display name.

**Commit:** `feat(auth): TokenAuther bearer token registration (Stage 1 T18)`

---

### Task 19 — `agentlabx/auth/oauth_auther.py`

**Files:** `agentlabx/auth/oauth_auther.py`, `tests/auth/test_oauth_auther.py`

**Public interface:**
- `class OAuthError(Exception)`, `class DeviceFlowPending(Exception)`
- `@dataclass(frozen=True) class DeviceFlowStart: user_code; verification_uri; interval; expires_in; poll_token`
- `class OAuthAuther`:
  - `name: str = "oauth"`
  - `__init__(*, backend: SQLiteBackend, crypto: FernetCrypto, providers: list[ProviderConfig])`
  - `def providers() -> list[ProviderConfig]`
  - `async def start_device_flow(provider_name: str) -> DeviceFlowStart` — POSTs `device_code_url`; stashes `(device_code, provider)` keyed by opaque `poll_token`.
  - `async def poll(poll_token: str) -> User` — POSTs `token_url`; on `authorization_pending` / `slow_down` → raise `DeviceFlowPending`; other error → `OAuthError`. Success → fetches userinfo, creates/updates `users` row (`id = f"{provider}:{provider_user_id}"`), encrypts and stores `OAuthTokenRow`, returns `User`.

**Acceptance tests (with `respx`):**
1. `start_device_flow` returns `user_code`, `verification_uri`, non-empty `poll_token`.
2. `poll` raises `DeviceFlowPending` on `authorization_pending`.
3. `poll` success path creates user + stores encrypted token blob (NOT plaintext access token).
4. `poll` raises `OAuthError` on `access_denied`.
5. Unconfigured provider → `OAuthError`.

**Commit:** `feat(auth): OAuthAuther device flow + encrypted token storage (Stage 1 T19)`

---

### Task 20 — Integration tests

**Files:** `tests/integration/test_first_run.py`, `tests/integration/test_account_swap.py`

**Acceptance:**
- `test_first_run` — fresh DB + fake keyring → DefaultAuther bootstraps `local`; AuthSession sets current; UserConfigStore saves a key; load returns decrypted; current user persists.
- `test_account_swap` — DefaultAuther + TokenAuther produce two distinct users; configs stored per-user; swap doesn't bleed config between users.

**Commit:** `test(integration): first-run + account swap (Stage 1 T20)`

---

## Part G — Core utilities

### Task 21 — `agentlabx/core/events.py`

**Files:** `agentlabx/core/events.py`, `tests/core/test_events.py`

**Public interface:**
- `EventData = dict[str, object]` is **NOT acceptable** — define `EventData` as a `TypedDict` if uniform, or a Pydantic model; in this stage use a `Mapping[str, str | int | float | bool | None]` union as the bus payload type.
- `@dataclass(frozen=True) class Event: type: str; data: Mapping[str, str | int | float | bool | None]`
- `EventHandler = Callable[[Event], Awaitable[None]]`
- `class EventBus`:
  - `def subscribe(event_type: str, handler: EventHandler) -> None` — `"*"` is a wildcard for all events.
  - `async def publish(event: Event) -> None` — fan-out via `asyncio.gather` to type-specific + wildcard handlers.

**Acceptance tests:** specific subscribe receives match; wildcard receives all; no subscribers → no-op; multiple handlers all invoked.

**Commit:** `feat(core): generic EventBus (Stage 1 T21)`

---

### Task 22 — `agentlabx/core/registry.py`

**Files:** `agentlabx/core/registry.py`, `tests/core/test_registry.py`

**Public interface:**
- `class PluginNotFoundError(Exception)`
- `class PluginRegistry(Generic[T])`:
  - `def register(name: str, value: T) -> None`
  - `def resolve(name: str) -> T` — raises `PluginNotFoundError` if absent.
  - `def list_names() -> list[str]` — sorted.

Callers instantiate one per kind: `PluginRegistry[BaseLLMProvider]`, etc. No common `object` bag.

**Acceptance tests:** register + typed-resolve; missing raises; duplicate replaces; sorted listing; two distinct typed registries don't conflict.

**Commit:** `feat(core): generic PluginRegistry[T] (Stage 1 T22)`

---

### Task 23 — `agentlabx/core/config.py`

**Files:** `agentlabx/core/config.py`, `tests/core/test_config.py`

**Public interface (Pydantic `BaseSettings`):**
- `class Settings(BaseSettings)`:
  - `model_config = SettingsConfigDict(env_prefix="AGENTLABX_", case_sensitive=False)`
  - `server_host: str = "127.0.0.1"`, `server_port: int = 8000`
  - `db_path: Path = Path("data/agentlabx.db")`
  - `providers_yaml_path: Path = Path("config/providers.yaml")`
  - `keyring_service: str = "agentlabx-local"`, `keyring_username: str = "master"`, `keyring_fallback_path: Path = Path("data/master.key")`
  - `log_level: str = "INFO"`

**Acceptance tests:** defaults present; env override (e.g., `AGENTLABX_SERVER_PORT=9001`) wins.

**Commit:** `feat(core): Settings — server/db/providers/keyring only (Stage 1 T23)`

---

## Part H — LLM providers

### Task 24 — `agentlabx/providers/llm/base.py`

**Public interface:**
- `@dataclass(frozen=True) class LLMResponse: content; model; tokens_in: int; tokens_out: int; cost_usd: float`
- `class BaseLLMProvider(ABC)`:
  - `name: str = ""`, `is_mock: bool = False`
  - `@abstractmethod async def query(*, api_key: str, model: str, prompt: str, system_prompt: str = "", temperature: float = 0.0) -> LLMResponse`

**Acceptance:** `LLMResponse` field check; `BaseLLMProvider` is abstract.

**Commit:** `feat(llm): BaseLLMProvider + LLMResponse — api_key per call (Stage 1 T24)`

---

### Task 25 — `MockLLMProvider`

**Public interface:** `name="mock"`, `is_mock=True`. `query` returns a deterministic echo `[MOCK] echo: <prompt>`, non-zero `tokens_in`/`tokens_out`, `cost_usd=0.0`. Never stores `api_key`.

**Acceptance tests:** echo content; `is_mock` flag; instance attrs do NOT leak `api_key`.

**Commit:** `feat(llm): MockLLMProvider (Stage 1 T25)`

---

### Task 26 — `LiteLLMProvider`

**Public interface:** `name="litellm"`, `is_mock=False`. `query` raises `ValueError` if `model` or `api_key` is empty; otherwise calls `litellm.acompletion(model, messages, api_key, temperature)` and returns parsed `LLMResponse` (cost via `litellm.completion_cost`, fallback `0.0` on cost calc errors). NEVER reads any environment variable.

**Acceptance tests (with patches on `acompletion` / `completion_cost`):** empty model → ValueError; empty api_key → ValueError; happy path returns parsed response with correct token counts and cost.

**Commit:** `feat(llm): LiteLLMProvider — api_key per call, no env reads (Stage 1 T26)`

---

### Task 27 — `TracedLLMProvider`

**Public interface:** Wraps an inner `BaseLLMProvider` + `EventBus`. Emits `llm_request` (with `model`, `prompt_chars`, `system_prompt_chars`, `temperature`, `is_mock`) before delegating; emits `llm_response` (with `model`, `tokens_in`, `tokens_out`, `cost_usd`, `response_chars`, `is_mock`) after. `api_key` MUST NOT appear in any event payload. No `stage` field.

**Acceptance tests:** request + response events emitted; no `stage` key in any payload; `api_key` value does not appear stringified anywhere in events.

**Commit:** `feat(llm): TracedLLMProvider — events without stage coupling (Stage 1 T27)`

---

## Part I — FastAPI server

### Task 28 — `agentlabx/server/deps.py`

**Public interface:**
- `@dataclass class ServerDeps: settings, backend, crypto, user_store, auth_session, default_auther, token_auther, oauth_auther`
- `async def build_deps(settings: Settings) -> ServerDeps` — initializes backend, loads master key (with fallback), wires UserConfigStore + AuthSession + all three authers (loading providers.yaml). Bootstraps DefaultAuther's `local` user; sets it as current if no current user exists.

**Acceptance:** ruff passes (smoke-tested via Task 29's app test).

**Commit:** `feat(server): DI container build_deps (Stage 1 T28)`

---

### Task 29 — `agentlabx/server/app.py`

**Public interface:**
- `def build_app(settings: Settings) -> FastAPI` — registers a lifespan that calls `build_deps(settings)` + stores result on `app.state.deps`; exposes `/health` returning `{"status": "ok"}`; mounts `/auth` and `/config` routers.
- Helper `def get_deps(request: Request) -> ServerDeps` — uses `isinstance(request.app.state.deps, ServerDeps)` to narrow; raises `RuntimeError` if absent or wrong type.
- Helper `def build_default_app() -> FastAPI` — zero-arg factory used by `uvicorn --factory`.

**Acceptance test:** TestClient against `/health` returns 200 `{"status": "ok"}`; lifespan sets `app.state.deps`.

**Commit:** `feat(server): FastAPI factory + lifespan + /health (Stage 1 T29)`

---

### Task 30 — `agentlabx/server/routes/auth.py`

**Public interface (Pydantic models for request/response, NO `Any`/`object`):**
- Routes:
  - `GET /auth/me → UserOut` — 401 if no current user.
  - `GET /auth/users → UsersOut`
  - `POST /auth/swap {user_id} → UserOut` — 404 if unknown.
  - `POST /auth/token {token, display_name} → UserOut` — 422 on `TokenValidationError`; sets new user as current.
  - `POST /auth/oauth/start {provider} → OAuthStartOut` — 422 if not configured.
  - `POST /auth/oauth/poll {poll_token} → UserOut` — 202 on `DeviceFlowPending`; 422 on `OAuthError`; sets user as current on success.

**Acceptance tests (FastAPI TestClient):** `/auth/me` returns `local`; `/auth/users` includes `local`; token register + auto-swap; swap to unknown user → 404; oauth/start with unconfigured provider → 422.

**Commit:** `feat(server): /auth routes (Stage 1 T30)`

---

### Task 31 — `agentlabx/server/routes/user_config.py`

**Public interface:**
- `GET /config → ConfigOut` — returns current user's config (empty if none); 401 if no current user.
- `PUT /config {api_keys, default_model} → ConfigOut` — runs `probe_provider` for each entry; on any `INVALID` returns 422 with `{detail: {field_errors: {provider: msg}, validation: {provider: status}}}`; on success encrypts + saves; response includes `validation` map.

**Acceptance tests:** GET on fresh install returns empty `api_keys`; PUT with mocked-valid probe stores + returns `validation: {provider: "valid"}`; PUT with mocked-invalid probe returns 422 with `field_errors`.

**Commit:** `feat(server): /config routes with save-time validation (Stage 1 T31)`

---

### Task 32 — `agentlabx/cli/main.py`

**Public interface:**
- `cli` Click group with one `serve` subcommand. `serve --host --port` overrides Settings; runs uvicorn with `agentlabx.server.app:build_default_app`, `factory=True`.

**Acceptance tests:** CLI `--help` lists `serve`; `serve --help` mentions `--port`.

**Commit:** `feat(cli): agentlabx serve (Stage 1 T32)`

---

## Part J — Frontend bootstrap

### Task 33 — Vite + React 19 + TS + Tailwind + shadcn scaffold

**Files:** `web/package.json`, `web/tsconfig.json`, `web/vite.config.ts`, `web/tailwind.config.ts`, `web/postcss.config.js`, `web/components.json`, `web/index.html`, `web/src/{main.tsx,App.tsx,index.css,lib/utils.ts}`.

**Contract:**
- React 19, TypeScript 5, Vite 5, Tailwind 3, shadcn/ui, TanStack Query 5, lucide-react, react-router-dom 6.
- Dev: `vitest`, `@testing-library/react`, `@testing-library/jest-dom`, `jsdom`, `@playwright/test`, `eslint`, `@typescript-eslint/*`, `prettier`.
- `tsconfig.json`: `strict: true`, `noImplicitAny: true`, `noUncheckedIndexedAccess: true`, `exactOptionalPropertyTypes: true`. `any` is disallowed (eslint enforces `@typescript-eslint/no-explicit-any: error`).
- `vite.config.ts`: dev proxy `/auth` and `/config` → `http://localhost:8000`.
- `npx shadcn@latest add button input dialog dropdown-menu badge select form label alert-dialog`.
- `.gitignore` covers `web/node_modules/`, `web/dist/`, `web/*.tsbuildinfo`.

**Acceptance:** `npm run dev` serves; `npm run build` produces `dist/`; `npm run lint` + `npx tsc --noEmit` pass on the placeholder app.

**Commit:** `feat(web): Vite + React 19 + TS + Tailwind + shadcn scaffold (Stage 1 T33)`

---

### Task 34 — Typed API client + shared types

**Files:** `web/src/lib/api.ts`, `web/src/lib/types.ts`, `web/src/lib/queryClient.ts`, `web/tests/unit/api.test.ts`

**Contract — types mirror backend exactly:**
- `AutherType = "default" | "oauth" | "token"`
- `User { id; display_name; auther_type }`, `UsersList { users: User[] }`
- `Config { user_id; api_keys: Record<string,string>; default_model: string | null; validation: Record<string, ValidationStatus> }`
- `OAuthStartResponse { user_code; verification_uri; interval; expires_in; poll_token }`
- `ValidationStatus = "valid" | "invalid" | "unverified"`
- `ApiError { status; detail }` (typed `detail` shape for the 422 case = `{ field_errors: Record<string,string>; validation: Record<string, ValidationStatus> }`)

**API client:** Typed wrappers for every backend route. Throws `ApiError` on non-2xx. NO `any` anywhere.

**Acceptance tests (Vitest, mock `fetch`):** `fetchMe` parses User; `putConfig` 422 throws ApiError with `field_errors`; `pollOAuth` 202 raises a recognizable pending signal.

**Commit:** `feat(web): typed API client + shared types (Stage 1 T34)`

---

### Task 35 — App shell + onboarding modal

**Files:** `web/src/App.tsx`, `web/src/features/layout/TopBar.tsx`, `web/tests/unit/App.test.tsx`

**Contract:**
- TopBar with title "AgentLabX" + AccountMenu placeholder slot.
- Routes: `/` (placeholder home), `/settings` (placeholder until T40).
- `/config` empty `api_keys` → renders gated `OnboardingModal` with "Go to Settings" CTA navigating to `/settings`.

**Acceptance tests:** TopBar renders; modal appears on empty config; modal absent on populated config; CTA navigates.

**Commit:** `feat(web): app shell + gated onboarding modal (Stage 1 T35)`

---

## Part K — Frontend components

Each component is one task: typed props, behaviour, test acceptance. All use shadcn primitives. Zero `any`.

### Task 36 — `AccountMenu`

Reads `/auth/me` + `/auth/users`. Dropdown lists all users; click → `POST /auth/swap` + invalidate caches. "Add Account" → opens `LoginDialog`. "Sign out" → swap to `local`.

Tests: dropdown opens; swap fires + invalidates; current user label correct.

Commit: `feat(web): AccountMenu (Stage 1 T36)`

---

### Task 37 — `LoginDialog`

Props: `open: boolean; onOpenChange: (b: boolean) => void`. Three cards: Default (closes) / OAuth (provider Select → DeviceFlowScreen) / Token (TokenLoginForm). Stage 1 hardcodes provider list `[{name:"github",display_name:"GitHub"},{name:"google",display_name:"Google"}]` — backend's 422 surfaces unconfigured providers.

Tests: renders three cards; each opens correct successor.

Commit: `feat(web): LoginDialog (Stage 1 T37)`

---

### Task 38 — `DeviceFlowScreen`

Props: `provider: string; onSuccess: (u: User) => void; onCancel: () => void`. On mount POSTs `/auth/oauth/start`. Shows `user_code` (with copy), opens `verification_uri` in new tab, polls `/auth/oauth/poll` every `interval`s. 202 → keep polling. Success → `onSuccess`. 422 (other OAuth error) → error message + cancel. Times out at `expires_in`.

Tests: poll cadence, success path, 422 path, expiry path (mocked).

Commit: `feat(web): DeviceFlowScreen (Stage 1 T38)`

---

### Task 39 — `TokenLoginForm`

Props: `onSuccess: (u: User) => void; onCancel: () => void`. Two required inputs (token, display_name); submit POSTs `/auth/token`; 422 surfaces inline field errors.

Tests: required validation; 422 path; success path.

Commit: `feat(web): TokenLoginForm (Stage 1 T39)`

---

### Task 40 — `SettingsPanel`

Route `/settings`. Loads `/config`. API Keys section: one `ApiKeyField` per provider in `["gemini","anthropic","openai"]` bound to `config.api_keys[provider]`. Default Model: shadcn Select with suggestions derived from valid-key providers; bound to `config.default_model`. Save → `PUT /config`. On 200 paints per-provider badges from `validation`. On 422 paints red badges from `field_errors` (preserves valid fields the backend partial-saved).

Tests: empty state; save valid; save invalid (422 partial); badge state per provider.

Commit: `feat(web): SettingsPanel (Stage 1 T40)`

---

### Task 41 — `ApiKeyField`

Props: `provider: string; value: string; status: ValidationStatus | "untouched"; onChange: (next: string) => void`. Masked Input with reveal toggle (eye icon); right-aligned Badge whose variant maps from `status` (green/red/gray); blur trims whitespace; "untouched" hides badge.

Tests: masks by default, reveal toggle, badge variant per status, trim on blur.

Commit: `feat(web): ApiKeyField (Stage 1 T41)`

---

## Part L — E2E + final checks

### Task 42 — Playwright happy-path

**Files:** `web/playwright.config.ts`, `web/tests/e2e/happy-path.spec.ts`

**Scenario:** Backend boots (uvicorn against tmp SQLite + fake keyring + validator-stubbed-to-return-valid), Vite dev server boots. Test: load `/` → modal appears → "Go to Settings" → paste mock Gemini key → save → green badge → reload → still logged in as Local + key persists.

**Acceptance:** `npx playwright test` passes.

**Commit:** `test(e2e): happy path login → save key → persist (Stage 1 T42)`

---

### Task 43 — Final ruff / typecheck / coverage sweep

Run:
- `uv run ruff check .` — All checks passed!
- `uv run pytest --cov=agentlabx --cov-report=term-missing` — 100% for `auth/`, `crypto/`, `user/`, `providers/storage/`; ≥85% elsewhere.
- `cd web && npm run lint && npx tsc --noEmit && npm run test` — all pass.

Fix any failures. No skipping. Commit any closing tests with `test: close coverage gaps (Stage 1 T43)`.

---

### Task 44 — Tag

Run all checks one last time. Then:

```bash
git tag -a stage1-complete -m "Stage 1 foundation: auth + encrypted user config + frontend settings panel"
git push origin main
git push origin stage1-complete
```

Report verification command outputs to user.

---

## Self-review — spec coverage

| Spec section | Tasks |
|---|---|
| §2 Goals 1-6 | T15+T20+T28; T16+T17-T19+T30; T4+T5+T10+T11; T12+T31; T33-T41; T1 + every task |
| §3 Module layout | T2 scaffold, T4-T32 implementations |
| §4 Data flow (first-run/save+validate/LLM/OAuth/swap/refresh) | T15+T28 / T12+T31 / T24-T27 / T17+T19+T30+T38 / T16+T30+T36 / (refresh deferred) |
| §5 Storage schema | T7-T9 |
| §6 Frontend layout + components | T33-T41 |
| §7 Error handling | T4 fallback / T5 DecryptionError / T9 SchemaVersionMismatch / T12 probe policy / T19 OAuthError / T30+T31 HTTP error mapping |
| §8 Testing | every task + T42 e2e + T43 sweep |
| §9 Out of scope | acknowledged |
| §10 Deliverables | all 44 tasks |

**Type consistency check:** every interface name (`User`, `UserConfig`, `*Row`, `ProviderConfig`, `LLMResponse`, `Event`, `ValidationResult`, `ValidationStatus`, `AutherType`, `PluginRegistry[T]`, `ServerDeps`) defined once and reused.

---

## Execution handoff

Plan complete and saved to `docs/superpowers/plans/2026-04-15-stage1-auth-userconfig-foundation.md`.

**1. Subagent-Driven (recommended)** — fresh subagent per task, two-stage review (spec then code-quality). Uses `superpowers:subagent-driven-development`.

**2. Inline Execution** — `superpowers:executing-plans`, batch with checkpoints.

Which approach?
