---
stage: 1
title: Auth + Encrypted User Config + Frontend Settings Panel
status: design
authors: [whats2000, claude]
created: 2026-04-15
---

# Stage 1 — Auth + Encrypted User Config Foundation

## 1. Purpose

Deliver an isolated foundation layer for AgentLabX: a logged-in user concept with pluggable authers (default single-user, OAuth device flow, bearer token), per-user encrypted API key storage, and the minimum frontend panel to manage both. No pipeline, no stages, no agents. This is the layer every later stage will build on for identity and secrets.

The prior implementation tangled identity, secrets, state, and pipeline orchestration inside a single monolithic `PipelineState` / `Session` object. API keys lived in `.env`, shared process-wide. This refactor isolates each concern so later stages can compose them without inheriting the coupling that made the previous design untestable.

## 2. Scope & goals

### Goals

1. Default user auto-login on first run — zero friction.
2. Account swap to OAuth (device flow) or Token auther via a pluggable `Auther` protocol.
3. Per-user API keys + default_model stored encrypted in SQLite (Fernet + OS-keyring master key).
4. Save-time API key validation against the provider (cheap probe endpoint).
5. Frontend settings panel exercising all of the above (React 19 + TS + Vite + shadcn/ui + Tailwind).
6. Project-wide strict typing enforced by ruff `ANN` rules, including `ANN401` which disallows `typing.Any`.

### Non-goals

- MCP tool integration (Stage 2).
- Any pipeline / stage / agent code.
- Multi-tenant server deployments with user-to-user data isolation.
- Refresh-token rotation beyond "store and auto-refresh on 401."
- Admin UI for managing OAuth provider configs — edit `providers.yaml` directly.

### Success criteria

- Launch app → redirected to gated settings → save a Gemini API key → key validated against Gemini → stored encrypted → shown masked in UI with a green "Valid" badge.
- Toggle to a GitHub OAuth account (if configured in `providers.yaml`) → device flow completes → user appears in account dropdown.
- Restart app → still logged in as last-active user; API keys still decrypt; still valid.
- All tests for auth / user-config / storage / crypto / LLM providers pass.
- `ruff check` passes with `ANN` rules enabled.

## 3. Architecture

### Module layout

```
agentlabx/
├── auth/
│   ├── user.py              # User dataclass (id, display_name, auther_type, created_at)
│   ├── auther.py            # Auther protocol
│   ├── default_auther.py    # single-user "local" — works out of the box
│   ├── oauth_auther.py      # OAuth device flow — pluggable providers
│   ├── token_auther.py      # Bearer token auther
│   ├── session.py           # "current user" in-memory + persisted across restarts
│   └── providers.py         # reads providers.yaml → typed ProviderConfig list
├── user/
│   ├── config.py            # UserConfig dataclass
│   ├── store.py             # UserConfigStore — reads/writes SQLite
│   └── validator.py         # save-time API key validation
├── crypto/
│   ├── fernet.py            # Fernet wrapper; encrypt/decrypt via master key
│   └── keyring.py           # OS-keyring accessor for master key
├── core/
│   ├── events.py            # generic pub/sub EventBus (no pipeline events)
│   ├── registry.py          # PluginType: TOOL, LLM_PROVIDER, STORAGE_BACKEND (no STAGE)
│   ├── config.py            # Settings: server bind, db path, providers_yaml_path, log_level
│   └── cost.py              # CostTracker — generic token/usd accumulator
├── providers/
│   ├── llm/
│   │   ├── base.py          # query(*, api_key, model, prompt, ...) — key per-call
│   │   ├── litellm_provider.py
│   │   └── mock_provider.py
│   └── storage/
│       ├── sqlite_backend.py
│       ├── models.py
│       └── migrations/
│           └── 001_initial.sql
├── server/
│   ├── app.py               # FastAPI bootstrap
│   ├── deps.py              # DI: auther, storage, registry
│   └── routes/
│       ├── auth.py
│       └── user_config.py
└── config/
    └── providers.yaml       # OAuth provider configs (shipped empty)

web/
├── src/
│   ├── features/
│   │   ├── auth/{AccountMenu,LoginDialog,DeviceFlowScreen,TokenLoginForm}.tsx
│   │   └── settings/{SettingsPanel,ApiKeyField,DefaultModelSelect}.tsx
│   ├── lib/{api,types}.ts
│   ├── App.tsx
│   └── main.tsx
├── tailwind.config.ts
├── components.json           # shadcn config
└── vite.config.ts

tests/
├── auth/, user/, crypto/, core/, providers/, server/, integration/
└── conftest.py              # fixtures: ephemeral SQLite, ephemeral keyring
```

### Module boundary contract

- `auth/` knows nothing about `user/config.py`'s shape — only owns identity.
- `user/` knows nothing about auth internals — only owns per-user-id config.
- `crypto/` is a pure utility — operates on bytes + a key.
- `providers/llm/` takes `api_key` as a parameter — zero env reads, zero user-store knowledge.
- `server/` wires via DI — replace any layer without touching routes.

Dependency direction (low-to-high): `crypto → storage → user → auth → server → frontend`.

## 4. Data flow

### First-run

1. App starts → `DefaultAuther.ensure_bootstrap()`:
   - `crypto/keyring.py`: master key not found → generate 32-byte key → store under service `agentlabx-local`.
   - storage: no users → create user `id="local"`, `display_name="Local User"`, `auther_type="default"`.
   - storage: create empty `user_configs` row for `id="local"`.
   - `app_state.last_active_user_id = "local"`.
2. Frontend boots → `GET /auth/me` → `{id: "local", display_name: "Local User"}`.
3. Frontend checks `GET /config` → `api_keys` empty → gated `SettingsPanel` shows "You need to configure at least one API key."

### Configure API key (save + validate)

1. User types Gemini key into `ApiKeyField` → clicks Save.
2. Frontend: `PUT /config` with `{api_keys: {gemini: "AIza..."}, default_model: null}`.
3. Backend: `user.validator.probe("gemini", "AIza...")`:
   - Calls Gemini `models` list endpoint with the key.
   - `200` → mark valid.
   - `401`/`403` → return `422 {field_errors: {"api_keys.gemini": "Invalid API key"}}`.
   - Network error → save succeeds with `warnings: [{provider, reason: "Could not verify"}]`.
4. Backend: encrypts `api_keys` values via `crypto/fernet` → writes `user_configs` row.
5. Frontend: shows green "Valid" badge (or red/gray per above).

### LLM query (runtime)

1. Caller: `llm_provider.query(api_key=<user_config.api_keys["gemini"]>, model="gemini/...", prompt=...)`.
2. LLM provider passes key through to LiteLLM — no env lookup, no user-store access.
3. Cost tracker appends turn cost; event bus emits `agent_llm_request` / `agent_llm_response` (no `stage` field).

### Account swap to OAuth (GitHub device flow)

1. User clicks `AccountMenu` → "Add Account" → picks "GitHub".
2. Frontend: `POST /auth/oauth/start {provider: "github"}`.
3. Backend: `OAuthAuther.start_device_flow("github")`:
   - Reads `providers.yaml` → `ProviderConfig{client_id, device_code_url, token_url, userinfo_url, scopes}`.
   - If `client_id` empty → `422 "GitHub not configured — see config/providers.yaml"`.
   - `POST` to `device_code_url` with `client_id` + `scopes` → receives `{device_code, user_code, verification_uri, interval, expires_in}`.
   - Returns `{user_code, verification_uri, expires_in, poll_token}` (`poll_token` is a server-side handle mapping to `device_code` + provider — never expose `device_code` to frontend).
4. Frontend: `DeviceFlowScreen` shows `user_code` + "Open `verification_uri`" button.
5. Frontend polls: `POST /auth/oauth/poll {poll_token}` every `interval` seconds.
6. Backend: `POST`s `token_url` with `device_code`:
   - `authorization_pending` → frontend continues polling.
   - Got token → `OAuthAuther.complete()`:
     - Fetches user info (`GET userinfo_url` with access_token).
     - Creates/updates `users` row (`id=f"github:{provider_user_id}"`).
     - Creates empty `user_configs` row if new.
     - Encrypts + stores access_token + refresh_token in `oauth_tokens` table.
     - `last_active_user_id` = this user.
   - Returns `{id, display_name}`.
7. Frontend closes dialog, refreshes `AccountMenu`.

### Account swap (existing account)

1. User clicks `AccountMenu` → picks an account from the list.
2. Frontend: `POST /auth/swap {user_id}`.
3. Backend: updates `last_active_user_id` → returns new current user.
4. Frontend refetches `/config`, re-gates if no keys.

### OAuth token refresh (transparent)

Any backend call that needs OAuth identity:
1. Read `oauth_tokens.access_token`; if `expires_at` passed, attempt refresh via `refresh_token`.
2. If refresh fails (revoked) → row marked stale; user force-swapped to `"local"` (always available). Frontend toast: "Your session for `{provider}` expired, please sign in again."

## 5. Storage schema (SQLite)

```sql
-- Timestamps: ISO 8601 TEXT. Encrypted blobs: BLOB (Fernet token bytes).

CREATE TABLE users (
    id            TEXT PRIMARY KEY,       -- "local", "github:42", "token:<hash>"
    display_name  TEXT NOT NULL,
    auther_type   TEXT NOT NULL,          -- "default" | "oauth" | "token"
    created_at    TEXT NOT NULL
);

CREATE TABLE user_configs (
    user_id            TEXT PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
    api_keys_encrypted BLOB NOT NULL,     -- Fernet(JSON.dumps({provider: key, ...}))
    default_model      TEXT,
    updated_at         TEXT NOT NULL
);

CREATE TABLE oauth_tokens (
    user_id                 TEXT PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
    provider                TEXT NOT NULL,
    access_token_encrypted  BLOB NOT NULL,
    refresh_token_encrypted BLOB,
    expires_at              TEXT,
    updated_at              TEXT NOT NULL
);

CREATE TABLE app_state (
    key    TEXT PRIMARY KEY,
    value  TEXT NOT NULL
);
-- Seeded rows:
--   ("last_active_user_id", "local")
--   ("schema_version", "1")
```

### Migration strategy

- `providers/storage/migrations/` holds SQL files: `001_initial.sql`, `002_*.sql`, etc.
- `sqlite_backend.py` on boot reads `schema_version`, runs pending migrations, updates `schema_version`.
- If version is ahead of what code supports (downgrade after upgrade) → refuse to boot with a clear error.

## 6. Frontend panel

### Layout

```
┌──────────────────────────────────────────────────────┐
│  AgentLabX                          [AccountMenu ▼]  │
├──────────────────────────────────────────────────────┤
│   Main content area (empty home for Stage 1)         │
│   If api_keys empty → gated onboarding modal         │
└──────────────────────────────────────────────────────┘
```

### Components

- **`AccountMenu`** — dropdown, current user + avatar (initials fallback), list of all users in the `users` table, "Add Account" → `LoginDialog`, "Sign out" → swap to Default (always available).
- **`LoginDialog`** — chooser with three cards: Default / OAuth (GitHub, Google, …) / Token.
- **`DeviceFlowScreen`** — user_code + copy button, "Open verification URI" button, polling status, cancel.
- **`TokenLoginForm`** — paste bearer token + display_name.
- **`SettingsPanel`** (`/settings` route, gated when no keys set):
  - API Keys section — one `ApiKeyField` per supported provider (Gemini, Anthropic, OpenAI, DeepSeek, Mistral).
  - Default Model section — `DefaultModelSelect` (freeform text with suggestions).
  - Save button: `PUT /config` with per-field validation badges on response.
- **`ApiKeyField`** — masked input, reveal toggle, right-aligned badge (green=Valid / red=Invalid / gray=Unverified).
- **`DefaultModelSelect`** — shadcn `Combobox` freeform, suggestions from valid providers.

### State management

TanStack Query for `/auth/me`, `/config`, `/auth/oauth/poll`. Context (or Zustand) for "current user" + "is onboarded." No Redux.

### API client

`lib/api.ts` — typed fetch wrappers; `lib/types.ts` — hand-written types mirroring backend dataclasses. Pydantic-to-TS generation deferred (small surface for Stage 1).

## 7. Error handling

### Crypto / keyring

- Keyring unavailable → fallback to `~/.agentlabx/master.key` (mode `0600`). Frontend banner: "Master key stored in file — not OS keyring."
- Decryption failure → `500 {error: "decryption_failed", hint: "master key mismatch"}`. Frontend recovery dialog: [Wipe encrypted data] [Help docs].

### Auth

- Device flow `expired_token` → `408` + frontend restart prompt.
- Device flow `access_denied` → `403` + frontend "You denied authorization."
- Polling timeout after `expires_in` → `504` + retry offer.
- Token malformed → `422 {field: "token", error: "Invalid token format"}`.
- `last_active_user_id` missing in `users` → silently reset to `"local"`, log warning.

### API key validation

- Provider `401`/`403` → `422 {field_errors: {"api_keys.<provider>": "Invalid API key"}}`; other valid fields still saved.
- Provider network error → save succeeds; `warnings: [{provider, reason: "Could not verify"}]`; badge "Unverified."
- Unknown provider → accepted, no validator registered, badge "Unverified."

### OAuth token refresh

- Refresh revoked → row marked stale → next request needing that identity returns `401` → frontend auto-swaps to `"local"` and toasts.

### Startup invariants

- Missing SQLite → create + run `001_initial.sql`.
- Partial migration failure → rollback + refuse to boot.
- `schema_version` ahead of code → refuse to boot.
- Keyring returns malformed master key → refuse to boot with recovery message.

### Logging

- Every error gets a structured log line with a stable `error_code` (e.g. `auth.device_flow.expired`, `crypto.decrypt.failed`).
- No secrets ever logged. API keys and tokens redacted as `"<redacted>"` before any log statement.

## 8. Testing

### Unit

- `tests/crypto/` — Fernet round-trip, key-mismatch raises, key-file fallback on keyring unavailable.
- `tests/auth/` — DefaultAuther bootstrap + idempotent + session persistence via `app_state`.
- `tests/auth/test_oauth_auther.py` — mock HTTP against fake device-code / token endpoints; encrypted token storage; refresh on 401.
- `tests/auth/test_token_auther.py` — add + reject invalid.
- `tests/user/` — `UserConfigStore` round-trip encrypted; concurrent saves serialize cleanly.
- `tests/user/test_validator.py` — `401→invalid`, `200→valid`, `timeout→unverified`.
- `tests/core/` — registry (no STAGE type), events pub/sub, config loader.
- `tests/providers/llm/` — `query(api_key=…)` passes through; never reads env; traced wrapper emits events without `stage` field.
- `tests/providers/storage/` — migrations up to v1; schema_version detection; FK cascade.

### Integration

- `tests/integration/test_first_run.py` — fresh DB + fresh keyring → bootstrap → PUT config with mock-validated key → decrypted round-trip.
- `tests/integration/test_account_swap.py` — add fake-OAuth user → swap → configs isolated per user.
- `tests/integration/test_startup_invariants.py` — missing SQLite auto-creates; version-ahead refuses boot; keyring-malformed refuses boot.

### HTTP routes

- `tests/server/test_auth_routes.py` — `/auth/me`, `/auth/swap`, `/auth/oauth/start`, `/auth/oauth/poll`, `/auth/token` — status codes + response shapes.
- `tests/server/test_config_routes.py` — `GET/PUT /config`, `422` shape, partial-save.

### Frontend

- `web/tests/unit/` (Vitest + React Testing Library):
  - `AccountMenu` renders current user + dropdown + swap callback.
  - `ApiKeyField` masks / reveals / badges per validation state.
  - `DeviceFlowScreen` shows `user_code`, polls at interval, auto-closes on success (mocked).
- `web/tests/e2e/` (Playwright, one happy path):
  - Launch app → gated settings → paste mock-Gemini key → validates → badge green → reload → persisted.

### Typing enforcement

- `ruff check` with `ANN` selected must pass on every module.
- Pre-commit check (or CI) fails on any `Any` usage or missing annotation.
- `mypy` / `pyright` optional as follow-up; ruff `ANN` is the Stage 1 gate.

### Determinism rules

- Every test uses an ephemeral SQLite file via `tmp_path`.
- Every test uses a fake keyring backend (in-memory substitute).
- No test depends on network. OAuth + API-key-validation tests use `httpx.MockTransport` or `respx`.
- LLM provider tests use `MockLLMProvider` — never hit real LiteLLM.

### Coverage target

- 100% of `auth/`, `crypto/`, `user/`, `providers/storage/`.
- 85%+ elsewhere.

## 9. Out of scope

- MCP tool integration (Stage 2).
- Any pipeline / stage / agent code.
- Admin UI for managing OAuth provider configs — edit `providers.yaml` directly.
- User-to-user data isolation in a multi-tenant server.
- User profile pictures / richer identity.
- Rate limiting on `/config` validation probes.
- Per-provider model catalog fetch (freeform text + static suggestions only).
- Key rotation policy.
- Audit log of config changes (only `updated_at`).
- Encrypted export / backup workflow.
- Mobile / native packaging.

## 10. Deliverables

1. Backend modules per §3: `auth/`, `user/`, `crypto/`, `core/`, `providers/`, `server/`, `config/providers.yaml`.
2. Frontend panel per §6: React 19 + TS + Vite + shadcn/ui + Tailwind; components listed above.
3. SQLite schema per §5 via migration `001_initial.sql`.
4. `pyproject.toml` updated with ruff `ANN` rules (including `ANN401`) and all project dependencies.
5. Tests per §8 — passing.
6. `ruff check` passing with `ANN` enabled; zero `Any` usage.
7. Playwright happy-path e2e passing.
