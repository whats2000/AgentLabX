# Stage 1 — Auth + Encrypted User Config Foundation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship an isolated foundation layer — default auto-login + pluggable OAuth (device flow) + Token authers, per-user encrypted API key storage in SQLite (Fernet + OS keyring), save-time API key validation, and a React/Vite/shadcn frontend settings panel — with strict typing enforced project-wide (no `Any`).

**Architecture:** Backend is a FastAPI process wiring `crypto → storage → user → auth → server` layers, each in its own module with typed interfaces. Frontend is a Vite React app using shadcn/ui + Tailwind, talking to the backend via typed `fetch`. No pipeline / stages / agents in this stage — foundation only.

**Tech Stack:** Python 3.12, FastAPI, uvicorn, Pydantic v2, SQLAlchemy async + aiosqlite, `cryptography` (Fernet), `keyring`, `httpx`, LiteLLM (provider passthrough), `respx` (test HTTP mocking), pytest + pytest-asyncio, ruff (`ANN` rules enabled). React 19 + TypeScript + Vite + shadcn/ui + Tailwind + TanStack Query + Vitest + Playwright.

**Reference spec:** [2026-04-15-stage1-auth-userconfig-foundation-design.md](../specs/2026-04-15-stage1-auth-userconfig-foundation-design.md)

**Coding standard — strict typing (project-wide, ENFORCED):**
- Every function parameter and return value MUST have a concrete, discoverable type.
- `typing.Any` is DISALLOWED (ruff `ANN401`).
- **`object` is ALSO DISALLOWED as a type annotation.** `object` accepts every value and exposes nothing — it's `Any` with a different name. Replace with one of:
  - A `Protocol` describing the minimum interface you actually use.
  - A Pydantic model for boundary data (HTTP request/response bodies, config files).
  - A concrete type or union (`int | str`, `BaseLLMProvider`, `SQLiteBackend`, …).
  - For plugin registries / heterogeneous collections: a separate typed surface per plugin kind, not a common `object` bag.
- `**kwargs: Any` is DISALLOWED. Use `TypedDict` or explicit kwargs.
- `typing.cast` to widen back into `Any` / `object` is DISALLOWED except in narrowly-scoped test shims that are themselves typed with a specific `Protocol`.
- Dataclass fields and module-level variables get explicit annotations unless the literal's type is unambiguous.
- **Test functions are NOT exempt.** Every test function must have a `-> None` return annotation AND typed parameters (fixture types included). This is enforced — `pyproject.toml` does not contain a test-file exception for `ANN001`/`ANN201`.
- CI-equivalent check: `uv run ruff check .` must pass on every commit.

**Commit discipline:**
- Small focused commits per task or sub-task.
- Use targeted `git add <paths>`. NEVER `git add .` or `git add -A`.
- Every task ends with tests passing and a commit.

---

## Part structure

- **Part A — Project bootstrap** (Tasks 1-3): pyproject trim, ruff ANN rules, dev dependencies, directory scaffold, test fixtures.
- **Part B — Crypto layer** (Tasks 4-6): keyring master-key, Fernet wrapper.
- **Part C — Storage layer** (Tasks 7-9): SQLite models, migration 001, async backend.
- **Part D — User config layer** (Tasks 10-12): UserConfig dataclass, UserConfigStore (encrypted), save-time validator.
- **Part E — Auth core** (Tasks 13-16): User model, Auther protocol, DefaultAuther, session persistence.
- **Part F — Authers continued** (Tasks 17-20): providers.yaml loader, TokenAuther, OAuthAuther device flow.
- **Part G — Core utilities** (Tasks 21-23): events, registry, trimmed Settings.
- **Part H — LLM providers** (Tasks 24-27): BaseLLMProvider, MockLLMProvider, LiteLLMProvider, TracedLLMProvider.
- **Part I — FastAPI server** (Tasks 28-32): app factory, deps injection, /auth routes, /config routes, error handlers.
- **Part J — Frontend bootstrap** (Tasks 33-35): Vite + shadcn + Tailwind scaffold, API client, types.
- **Part K — Frontend components** (Tasks 36-41): AccountMenu, LoginDialog, DeviceFlowScreen, TokenLoginForm, SettingsPanel, ApiKeyField.
- **Part L — E2E + final checks** (Tasks 42-44): Playwright happy path, ruff sweep, coverage report.

Total: 44 tasks.

---

## File structure overview

```
agentlabx/
├── __init__.py
├── crypto/
│   ├── __init__.py
│   ├── keyring.py                 # OS-keyring master key accessor (with key-file fallback)
│   └── fernet.py                  # Fernet encrypt/decrypt wrappers over bytes
├── providers/
│   ├── __init__.py
│   ├── storage/
│   │   ├── __init__.py
│   │   ├── models.py              # Typed row dataclasses: UserRow, UserConfigRow, OAuthTokenRow, AppStateRow
│   │   ├── sqlite_backend.py      # Async CRUD + migration runner + schema_version checks
│   │   └── migrations/
│   │       └── 001_initial.sql
│   └── llm/
│       ├── __init__.py
│       ├── base.py                # BaseLLMProvider Protocol — query(api_key, model, prompt, ...)
│       ├── mock_provider.py       # MockLLMProvider for tests
│       ├── litellm_provider.py    # LiteLLM passthrough — api_key per call
│       └── traced.py              # TracedLLMProvider — emits events, no 'stage' field
├── user/
│   ├── __init__.py
│   ├── config.py                  # UserConfig dataclass
│   ├── store.py                   # UserConfigStore — encrypted CRUD on top of storage
│   └── validator.py               # probe_provider(provider, api_key) -> ValidationResult
├── auth/
│   ├── __init__.py
│   ├── user.py                    # User dataclass
│   ├── auther.py                  # Auther Protocol
│   ├── default_auther.py          # DefaultAuther — single-user "local"
│   ├── token_auther.py            # TokenAuther
│   ├── oauth_auther.py            # OAuthAuther — device flow over httpx
│   ├── providers.py               # ProviderConfig + providers.yaml loader
│   └── session.py                 # "current user" context — reads/writes app_state
├── core/
│   ├── __init__.py
│   ├── events.py                  # Generic EventBus (pub/sub)
│   ├── registry.py                # PluginRegistry (TOOL, LLM_PROVIDER, STORAGE_BACKEND)
│   ├── config.py                  # Settings (server host/port, db path, providers_yaml_path, log_level)
│   └── cost.py                    # CostTracker
└── server/
    ├── __init__.py
    ├── app.py                     # FastAPI factory
    ├── deps.py                    # Request-scoped DI: auther, storage, current_user
    └── routes/
        ├── __init__.py
        ├── auth.py                # /auth/me, /auth/swap, /auth/oauth/start, /auth/oauth/poll, /auth/token
        └── user_config.py         # GET /config, PUT /config

config/
└── providers.yaml                 # OAuth provider configs (shipped with empty client_id fields)

web/
├── package.json
├── tsconfig.json
├── vite.config.ts
├── tailwind.config.ts
├── postcss.config.js
├── components.json                # shadcn config
├── index.html
└── src/
    ├── main.tsx
    ├── App.tsx
    ├── index.css                  # Tailwind directives
    ├── lib/
    │   ├── api.ts                 # Typed fetch client
    │   ├── types.ts               # Shared types mirroring backend dataclasses
    │   └── queryClient.ts         # TanStack Query client
    ├── components/ui/             # shadcn-generated primitives (Button, Dialog, Input, etc.)
    └── features/
        ├── auth/
        │   ├── AccountMenu.tsx
        │   ├── LoginDialog.tsx
        │   ├── DeviceFlowScreen.tsx
        │   └── TokenLoginForm.tsx
        └── settings/
            ├── SettingsPanel.tsx
            ├── ApiKeyField.tsx
            └── DefaultModelSelect.tsx

tests/
├── conftest.py                    # Shared fixtures: tmp_path_sqlite, fake_keyring, test_client
├── crypto/
│   ├── test_keyring.py
│   └── test_fernet.py
├── providers/
│   ├── storage/
│   │   ├── test_models.py
│   │   └── test_sqlite_backend.py
│   └── llm/
│       ├── test_base.py
│       ├── test_mock_provider.py
│       ├── test_litellm_provider.py
│       └── test_traced.py
├── user/
│   ├── test_config.py
│   ├── test_store.py
│   └── test_validator.py
├── auth/
│   ├── test_user.py
│   ├── test_default_auther.py
│   ├── test_token_auther.py
│   ├── test_oauth_auther.py
│   ├── test_providers.py
│   └── test_session.py
├── core/
│   ├── test_events.py
│   ├── test_registry.py
│   └── test_config.py
├── server/
│   ├── test_app.py
│   ├── test_auth_routes.py
│   └── test_config_routes.py
└── integration/
    ├── test_first_run.py
    ├── test_account_swap.py
    └── test_startup_invariants.py

web/tests/
├── unit/
│   ├── AccountMenu.test.tsx
│   ├── ApiKeyField.test.tsx
│   └── DeviceFlowScreen.test.tsx
└── e2e/
    └── happy-path.spec.ts          # Playwright
```

**Rule:** every `agentlabx/**/__init__.py` created in this plan is empty (no re-exports in Stage 1 — explicit imports only).

---

## Test-code annotation rule (applies to every test in this plan)

The test sketches below sometimes omit `-> None` return annotations or fixture parameter types for readability. When copying a sketch into the codebase, the implementer MUST add full annotations before committing — ruff `ANN` rules will otherwise reject the commit. Specifically:

- Every `def test_*()` / `async def test_*()` gets `-> None`.
- Every fixture parameter gets a concrete type:
  - `tmp_path: Path`
  - `tmp_path_sqlite: Path`
  - `tmp_path_factory: pytest.TempPathFactory`
  - `monkeypatch: pytest.MonkeyPatch`
  - `fake_keyring: InMemoryKeyringBackend` (imported from `tests.conftest`)
- Helper functions inside test modules get full annotations too (`def _helper(x: int) -> str:`).
- Mock/patch helper classes (e.g. test-only `_FakeResp`) get annotated `__init__` / method signatures or use a typed `Protocol`.

If a sketch below shows `def test_x(fake_keyring):` treat it as shorthand for `def test_x(fake_keyring: InMemoryKeyringBackend) -> None:` in the actual code you commit.

---

## Part A — Project bootstrap

### Task 1: Trim `pyproject.toml` to Stage 1 dependencies + enable ruff ANN rules

**Files:**
- Modify: `pyproject.toml`

- [ ] **Step 1: Replace `pyproject.toml` contents** with the Stage 1 set. All pipeline/stage deps removed; crypto/keyring/httpx/respx added; ruff `ANN` rules enabled.

```toml
[project]
name = "agentlabx"
version = "0.2.0"
description = "Modular multi-instance research automation platform"
requires-python = ">=3.12"
dependencies = [
    "pydantic>=2.0,<3.0",
    "pydantic-settings>=2.0,<3.0",
    "pyyaml>=6.0,<7.0",
    "litellm>=1.82,<2.0",
    "sqlalchemy[asyncio]>=2.0,<3.0",
    "aiosqlite>=0.19,<1.0",
    "fastapi>=0.115,<1.0",
    "uvicorn[standard]>=0.32,<1.0",
    "click>=8.1,<9.0",
    "cryptography>=42.0,<44.0",
    "keyring>=25.0,<26.0",
    "httpx>=0.27,<1.0",
]

[project.scripts]
agentlabx = "agentlabx.cli.main:cli"

[project.optional-dependencies]
dev = [
    "pytest>=8.0",
    "pytest-asyncio>=0.24",
    "pytest-cov>=5.0",
    "respx>=0.21,<1.0",
    "ruff>=0.4",
]

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.ruff]
target-version = "py312"
line-length = 100

[tool.ruff.lint]
select = ["E", "F", "I", "N", "W", "UP", "ANN", "B", "SIM", "RET"]
ignore = [
    "ANN101",  # Missing annotation for self
    "ANN102",  # Missing annotation for cls
]

[tool.pytest.ini_options]
testpaths = ["tests"]
asyncio_mode = "auto"

[tool.hatch.build.targets.wheel]
packages = ["agentlabx"]
```

- [ ] **Step 2: Regenerate lock + verify install**

Run:
```bash
uv lock
uv sync --extra dev
```
Expected: lock + install succeed. No missing package errors.

- [ ] **Step 3: Run ruff on the (currently tiny) repo — should pass with no files**

Run: `uv run ruff check .`
Expected: `All checks passed!` (no Python files yet, nothing to lint).

- [ ] **Step 4: Commit**

```bash
git add pyproject.toml uv.lock
git commit -m "chore(stage1): trim deps to foundation set + enable ruff ANN rules"
```

---

### Task 2: Create backend directory scaffold (empty `__init__.py` files)

**Files:**
- Create: `agentlabx/__init__.py`
- Create: `agentlabx/crypto/__init__.py`
- Create: `agentlabx/providers/__init__.py`
- Create: `agentlabx/providers/storage/__init__.py`
- Create: `agentlabx/providers/storage/migrations/__init__.py`
- Create: `agentlabx/providers/llm/__init__.py`
- Create: `agentlabx/user/__init__.py`
- Create: `agentlabx/auth/__init__.py`
- Create: `agentlabx/core/__init__.py`
- Create: `agentlabx/server/__init__.py`
- Create: `agentlabx/server/routes/__init__.py`
- Create: `tests/__init__.py`
- Create: `tests/crypto/__init__.py`
- Create: `tests/providers/__init__.py`
- Create: `tests/providers/storage/__init__.py`
- Create: `tests/providers/llm/__init__.py`
- Create: `tests/user/__init__.py`
- Create: `tests/auth/__init__.py`
- Create: `tests/core/__init__.py`
- Create: `tests/server/__init__.py`
- Create: `tests/integration/__init__.py`

- [ ] **Step 1: Create all listed files empty** (size = 0 bytes each). Use your editor / OS as preferred; every file should literally be empty.

- [ ] **Step 2: Verify pytest collects cleanly**

Run: `uv run pytest --collect-only -q`
Expected: `0 tests collected` (no tests yet), zero errors.

- [ ] **Step 3: Commit**

```bash
git add agentlabx/ tests/
git commit -m "chore(stage1): scaffold backend + test package directories"
```

---

### Task 3: Shared `tests/conftest.py` with `tmp_path_sqlite` and `fake_keyring` fixtures

**Files:**
- Create: `tests/conftest.py`

- [ ] **Step 1: Write the conftest** providing fixtures used across all subsequent tests.

```python
"""Shared test fixtures.

Fixtures:
- tmp_path_sqlite: yields a path to a per-test SQLite file under pytest's tmp_path.
- fake_keyring: installs an in-memory keyring backend for the duration of the test
  so crypto/keyring.py exercises real code paths without touching the host OS keyring.
"""
from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import keyring
import keyring.backend
import keyring.errors
import pytest


class InMemoryKeyringBackend(keyring.backend.KeyringBackend):
    """Public so tests can type their `fake_keyring` fixture parameter."""

    priority: float = 1.0  # pyright: ignore[reportAssignmentType]

    def __init__(self) -> None:
        self._store: dict[tuple[str, str], str] = {}

    def get_password(self, service: str, username: str) -> str | None:
        return self._store.get((service, username))

    def set_password(self, service: str, username: str, password: str) -> None:
        self._store[(service, username)] = password

    def delete_password(self, service: str, username: str) -> None:
        try:
            del self._store[(service, username)]
        except KeyError as e:
            raise keyring.errors.PasswordDeleteError(str(e)) from e


@pytest.fixture
def tmp_path_sqlite(tmp_path: Path) -> Path:
    """Per-test SQLite file path. File does not yet exist."""
    return tmp_path / "agentlabx-test.db"


@pytest.fixture
def fake_keyring() -> Iterator[InMemoryKeyringBackend]:
    """Install an in-memory keyring backend; restore original on teardown."""
    original = keyring.get_keyring()
    fake = InMemoryKeyringBackend()
    keyring.set_keyring(fake)
    try:
        yield fake
    finally:
        keyring.set_keyring(original)
```

- [ ] **Step 2: Write a trivial test exercising both fixtures** at `tests/test_conftest_fixtures.py`:

```python
from pathlib import Path

import keyring

from tests.conftest import InMemoryKeyringBackend


def test_tmp_path_sqlite_is_a_path(tmp_path_sqlite: Path) -> None:
    assert isinstance(tmp_path_sqlite, Path)
    assert tmp_path_sqlite.name == "agentlabx-test.db"
    assert not tmp_path_sqlite.exists()


def test_fake_keyring_isolates_host(fake_keyring: InMemoryKeyringBackend) -> None:
    keyring.set_password("agentlabx-test", "master", "secret-value")
    assert keyring.get_password("agentlabx-test", "master") == "secret-value"
```

- [ ] **Step 3: Run test**

Run: `uv run pytest tests/test_conftest_fixtures.py -v`
Expected: 2 passed.

- [ ] **Step 4: Run ruff** — passes with ANN rules.

Run: `uv run ruff check tests/conftest.py tests/test_conftest_fixtures.py`
Expected: `All checks passed!`

- [ ] **Step 5: Commit**

```bash
git add tests/conftest.py tests/test_conftest_fixtures.py
git commit -m "test(stage1): shared conftest with tmp_path_sqlite + fake_keyring fixtures"
```

---

## Part B — Crypto layer

### Task 4: `agentlabx/crypto/keyring.py` — OS-keyring master-key accessor (+ key-file fallback)

**Files:**
- Create: `agentlabx/crypto/keyring.py`
- Create: `tests/crypto/test_keyring.py`

- [ ] **Step 1: Write the failing test**

```python
"""Unit tests for crypto/keyring — master key get-or-create + file fallback."""
from __future__ import annotations

from pathlib import Path

import keyring as keyring_lib
import pytest

from agentlabx.crypto.keyring import MasterKeyError, load_or_create_master_key


SERVICE = "agentlabx-test"
USERNAME = "master"


def test_first_call_generates_and_stores_key(fake_keyring):
    key = load_or_create_master_key(service=SERVICE, username=USERNAME)
    assert isinstance(key, bytes)
    assert len(key) == 32
    stored = keyring_lib.get_password(SERVICE, USERNAME)
    assert stored is not None


def test_second_call_returns_same_key(fake_keyring):
    first = load_or_create_master_key(service=SERVICE, username=USERNAME)
    second = load_or_create_master_key(service=SERVICE, username=USERNAME)
    assert first == second


def test_file_fallback_when_keyring_unavailable(tmp_path: Path, monkeypatch):
    def _raise(*args, **kwargs):
        raise keyring_lib.errors.NoKeyringError("no backend")

    monkeypatch.setattr(keyring_lib, "get_password", _raise)
    monkeypatch.setattr(keyring_lib, "set_password", _raise)
    key_file = tmp_path / "master.key"
    key = load_or_create_master_key(service=SERVICE, username=USERNAME, fallback_path=key_file)
    assert len(key) == 32
    assert key_file.exists()
    again = load_or_create_master_key(service=SERVICE, username=USERNAME, fallback_path=key_file)
    assert key == again


def test_malformed_stored_key_raises(fake_keyring):
    keyring_lib.set_password(SERVICE, USERNAME, "not-valid-base64!!!")
    with pytest.raises(MasterKeyError):
        load_or_create_master_key(service=SERVICE, username=USERNAME)
```

- [ ] **Step 2: Run — expect ImportError.**

Run: `uv run pytest tests/crypto/test_keyring.py -v`

- [ ] **Step 3: Implement `agentlabx/crypto/keyring.py`**

```python
"""Master key management.

Stores a 32-byte Fernet master key in the OS keyring under a configurable
service+username. Falls back to a key file if the keyring backend raises.
"""
from __future__ import annotations

import base64
import os
from pathlib import Path

import keyring as keyring_lib
import keyring.errors


class MasterKeyError(Exception):
    """Raised when the stored master key is malformed or inaccessible."""


def _encode(key: bytes) -> str:
    return base64.urlsafe_b64encode(key).decode("ascii")


def _decode(encoded: str) -> bytes:
    try:
        raw = base64.urlsafe_b64decode(encoded.encode("ascii"))
    except (ValueError, TypeError) as exc:
        raise MasterKeyError(f"Stored master key not valid base64: {exc}") from exc
    if len(raw) != 32:
        raise MasterKeyError(f"Master key must be 32 bytes, got {len(raw)}")
    return raw


def load_or_create_master_key(
    *,
    service: str,
    username: str,
    fallback_path: Path | None = None,
) -> bytes:
    """Return the 32-byte master key for (service, username), creating if absent.

    If the keyring backend raises NoKeyringError and `fallback_path` is provided,
    the key is read from / written to that file (mode 0600) instead.
    """
    try:
        existing = keyring_lib.get_password(service, username)
    except keyring_lib.errors.NoKeyringError:
        if fallback_path is None:
            raise
        return _load_or_create_in_file(fallback_path)

    if existing is not None:
        return _decode(existing)

    new_key = os.urandom(32)
    try:
        keyring_lib.set_password(service, username, _encode(new_key))
    except keyring_lib.errors.NoKeyringError:
        if fallback_path is None:
            raise
        return _load_or_create_in_file(fallback_path)
    return new_key


def _load_or_create_in_file(path: Path) -> bytes:
    if path.exists():
        return _decode(path.read_text(encoding="ascii").strip())
    path.parent.mkdir(parents=True, exist_ok=True)
    new_key = os.urandom(32)
    path.write_text(_encode(new_key), encoding="ascii")
    try:
        path.chmod(0o600)
    except (OSError, NotImplementedError):
        pass  # Windows may reject chmod
    return new_key
```

- [ ] **Step 4: Run — expect 4 passed.**

- [ ] **Step 5: Ruff + commit**

```bash
uv run ruff check agentlabx/crypto/ tests/crypto/
git add agentlabx/crypto/keyring.py tests/crypto/test_keyring.py
git commit -m "feat(crypto): OS-keyring master key with file fallback (Stage 1 T4)"
```

---

### Task 5: `agentlabx/crypto/fernet.py` — Fernet encrypt/decrypt wrappers

**Files:**
- Create: `agentlabx/crypto/fernet.py`
- Create: `tests/crypto/test_fernet.py`

- [ ] **Step 1: Write the failing test**

```python
from __future__ import annotations

import pytest

from agentlabx.crypto.fernet import DecryptionError, FernetCrypto


def test_encrypt_decrypt_round_trip():
    key = b"\x00" * 32
    crypto = FernetCrypto(master_key=key)
    ciphertext = crypto.encrypt(b"hello world")
    assert ciphertext != b"hello world"
    assert crypto.decrypt(ciphertext) == b"hello world"


def test_different_keys_cannot_decrypt():
    c1 = FernetCrypto(master_key=b"\x00" * 32)
    c2 = FernetCrypto(master_key=b"\x01" * 32)
    ct = c1.encrypt(b"secret")
    with pytest.raises(DecryptionError):
        c2.decrypt(ct)


def test_encrypt_empty_bytes():
    crypto = FernetCrypto(master_key=b"\x00" * 32)
    ct = crypto.encrypt(b"")
    assert crypto.decrypt(ct) == b""


def test_decrypt_invalid_ciphertext_raises():
    crypto = FernetCrypto(master_key=b"\x00" * 32)
    with pytest.raises(DecryptionError):
        crypto.decrypt(b"not-a-real-fernet-token")


def test_master_key_must_be_32_bytes():
    with pytest.raises(ValueError):
        FernetCrypto(master_key=b"\x00" * 16)
```

- [ ] **Step 2: Run — expect ImportError.**

- [ ] **Step 3: Implement `agentlabx/crypto/fernet.py`**

```python
"""Fernet wrapper for symmetric encryption of byte payloads."""
from __future__ import annotations

import base64

from cryptography.fernet import Fernet, InvalidToken


class DecryptionError(Exception):
    """Raised when ciphertext cannot be decrypted (wrong key, corrupted, etc.)."""


class FernetCrypto:
    def __init__(self, *, master_key: bytes) -> None:
        if len(master_key) != 32:
            raise ValueError(f"master_key must be 32 bytes, got {len(master_key)}")
        fernet_key = base64.urlsafe_b64encode(master_key)
        self._fernet = Fernet(fernet_key)

    def encrypt(self, plaintext: bytes) -> bytes:
        return self._fernet.encrypt(plaintext)

    def decrypt(self, ciphertext: bytes) -> bytes:
        try:
            return self._fernet.decrypt(ciphertext)
        except InvalidToken as exc:
            raise DecryptionError("Failed to decrypt ciphertext — wrong key or corrupted") from exc
```

- [ ] **Step 4: Run — expect 5 passed.**

- [ ] **Step 5: Ruff + commit**

```bash
uv run ruff check agentlabx/crypto/fernet.py tests/crypto/test_fernet.py
git add agentlabx/crypto/fernet.py tests/crypto/test_fernet.py
git commit -m "feat(crypto): Fernet encrypt/decrypt wrapper (Stage 1 T5)"
```

---

### Task 6: Crypto integration smoke test

**Files:**
- Create: `tests/crypto/test_integration.py`

- [ ] **Step 1: Write the test**

```python
from __future__ import annotations

from agentlabx.crypto.fernet import FernetCrypto
from agentlabx.crypto.keyring import load_or_create_master_key


def test_keyring_master_key_drives_fernet_round_trip(fake_keyring):
    key = load_or_create_master_key(service="agentlabx-local", username="master")
    crypto = FernetCrypto(master_key=key)
    ciphertext = crypto.encrypt(b"API_KEY_VALUE")
    assert crypto.decrypt(ciphertext) == b"API_KEY_VALUE"


def test_same_keyring_entry_across_process_simulation(fake_keyring):
    key1 = load_or_create_master_key(service="agentlabx-local", username="master")
    key2 = load_or_create_master_key(service="agentlabx-local", username="master")
    c1 = FernetCrypto(master_key=key1)
    c2 = FernetCrypto(master_key=key2)
    ct = c1.encrypt(b"persisted")
    assert c2.decrypt(ct) == b"persisted"
```

- [ ] **Step 2: Run — expect 2 passed. Full crypto suite: 11 passed.**

Run: `uv run pytest tests/crypto/ -v`

- [ ] **Step 3: Commit**

```bash
git add tests/crypto/test_integration.py
git commit -m "test(crypto): integration — keyring key drives Fernet round-trip (Stage 1 T6)"
```

---

## Part C — Storage layer

### Task 7: `agentlabx/providers/storage/models.py` — typed row dataclasses

**Files:**
- Create: `agentlabx/providers/storage/models.py`
- Create: `tests/providers/storage/test_models.py`

- [ ] **Step 1: Write failing test**

```python
from __future__ import annotations

from datetime import datetime, timezone

from agentlabx.providers.storage.models import (
    AppStateRow,
    AutherType,
    OAuthTokenRow,
    UserConfigRow,
    UserRow,
)


def test_user_row_fields():
    now = datetime.now(timezone.utc)
    row = UserRow(id="local", display_name="Local", auther_type=AutherType.DEFAULT, created_at=now)
    assert row.id == "local"
    assert row.auther_type is AutherType.DEFAULT
    assert row.created_at == now


def test_user_config_row_fields():
    row = UserConfigRow(
        user_id="local",
        api_keys_encrypted=b"fernet-blob",
        default_model=None,
        updated_at=datetime.now(timezone.utc),
    )
    assert row.api_keys_encrypted == b"fernet-blob"
    assert row.default_model is None


def test_oauth_token_row_fields():
    row = OAuthTokenRow(
        user_id="github:42",
        provider="github",
        access_token_encrypted=b"a",
        refresh_token_encrypted=b"r",
        expires_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )
    assert row.provider == "github"
    assert row.refresh_token_encrypted == b"r"


def test_app_state_row_fields():
    row = AppStateRow(key="last_active_user_id", value="local")
    assert row.key == "last_active_user_id"
    assert row.value == "local"


def test_auther_type_values():
    assert AutherType.DEFAULT.value == "default"
    assert AutherType.OAUTH.value == "oauth"
    assert AutherType.TOKEN.value == "token"
```

- [ ] **Step 2: Run — expect ImportError.**

- [ ] **Step 3: Implement `agentlabx/providers/storage/models.py`**

```python
"""Typed row dataclasses mirroring the SQLite schema.

Kept as plain dataclasses (not Pydantic) for zero-overhead internal use.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum


class AutherType(str, Enum):
    DEFAULT = "default"
    OAUTH = "oauth"
    TOKEN = "token"


@dataclass(frozen=True)
class UserRow:
    id: str
    display_name: str
    auther_type: AutherType
    created_at: datetime


@dataclass(frozen=True)
class UserConfigRow:
    user_id: str
    api_keys_encrypted: bytes
    default_model: str | None
    updated_at: datetime


@dataclass(frozen=True)
class OAuthTokenRow:
    user_id: str
    provider: str
    access_token_encrypted: bytes
    refresh_token_encrypted: bytes | None
    expires_at: datetime | None
    updated_at: datetime


@dataclass(frozen=True)
class AppStateRow:
    key: str
    value: str
```

- [ ] **Step 4: Run + ruff + commit**

```bash
uv run pytest tests/providers/storage/test_models.py -v
uv run ruff check agentlabx/providers/storage/models.py tests/providers/storage/test_models.py
git add agentlabx/providers/storage/models.py tests/providers/storage/test_models.py
git commit -m "feat(storage): typed row dataclasses (Stage 1 T7)"
```

Expected: 5 passed.

---

### Task 8: `agentlabx/providers/storage/migrations/001_initial.sql`

**Files:**
- Create: `agentlabx/providers/storage/migrations/001_initial.sql`

- [ ] **Step 1: Write the migration SQL**

```sql
-- Migration 001 — initial schema for users, user_configs, oauth_tokens, app_state.
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS users (
    id            TEXT PRIMARY KEY,
    display_name  TEXT NOT NULL,
    auther_type   TEXT NOT NULL CHECK (auther_type IN ('default', 'oauth', 'token')),
    created_at    TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS user_configs (
    user_id            TEXT PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
    api_keys_encrypted BLOB NOT NULL,
    default_model      TEXT,
    updated_at         TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS oauth_tokens (
    user_id                 TEXT PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
    provider                TEXT NOT NULL,
    access_token_encrypted  BLOB NOT NULL,
    refresh_token_encrypted BLOB,
    expires_at              TEXT,
    updated_at              TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS app_state (
    key    TEXT PRIMARY KEY,
    value  TEXT NOT NULL
);

INSERT OR IGNORE INTO app_state (key, value) VALUES ('schema_version', '1');
```

- [ ] **Step 2: Commit**

```bash
git add agentlabx/providers/storage/migrations/001_initial.sql
git commit -m "feat(storage): migration 001 initial schema (Stage 1 T8)"
```

---

### Task 9: `agentlabx/providers/storage/sqlite_backend.py` — async CRUD + migration runner

**Files:**
- Create: `agentlabx/providers/storage/sqlite_backend.py`
- Create: `tests/providers/storage/test_sqlite_backend.py`

This is the largest task in Part C. Implementation is async using `aiosqlite` directly (no SQLAlchemy ORM — keeps the surface small and predictable).

- [ ] **Step 1: Write the failing test**

```python
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pytest

from agentlabx.providers.storage.models import (
    AppStateRow,
    AutherType,
    OAuthTokenRow,
    UserConfigRow,
    UserRow,
)
from agentlabx.providers.storage.sqlite_backend import (
    SchemaVersionMismatchError,
    SQLiteBackend,
)


async def test_initialize_creates_tables_and_seeds_schema_version(tmp_path_sqlite: Path):
    backend = SQLiteBackend(db_path=tmp_path_sqlite)
    await backend.initialize()
    try:
        version = await backend.get_schema_version()
        assert version == 1
    finally:
        await backend.close()


async def test_user_crud(tmp_path_sqlite: Path):
    backend = SQLiteBackend(db_path=tmp_path_sqlite)
    await backend.initialize()
    try:
        now = datetime.now(timezone.utc)
        user = UserRow(id="local", display_name="Local", auther_type=AutherType.DEFAULT, created_at=now)
        await backend.upsert_user(user)
        loaded = await backend.get_user("local")
        assert loaded == user
        assert await backend.get_user("does-not-exist") is None
        all_users = await backend.list_users()
        assert [u.id for u in all_users] == ["local"]
    finally:
        await backend.close()


async def test_user_config_crud(tmp_path_sqlite: Path):
    backend = SQLiteBackend(db_path=tmp_path_sqlite)
    await backend.initialize()
    try:
        now = datetime.now(timezone.utc)
        await backend.upsert_user(UserRow(id="local", display_name="L", auther_type=AutherType.DEFAULT, created_at=now))
        cfg = UserConfigRow(user_id="local", api_keys_encrypted=b"blob", default_model="g/m", updated_at=now)
        await backend.upsert_user_config(cfg)
        loaded = await backend.get_user_config("local")
        assert loaded == cfg
    finally:
        await backend.close()


async def test_oauth_token_crud(tmp_path_sqlite: Path):
    backend = SQLiteBackend(db_path=tmp_path_sqlite)
    await backend.initialize()
    try:
        now = datetime.now(timezone.utc)
        await backend.upsert_user(UserRow(id="github:42", display_name="GH", auther_type=AutherType.OAUTH, created_at=now))
        tok = OAuthTokenRow(
            user_id="github:42",
            provider="github",
            access_token_encrypted=b"at",
            refresh_token_encrypted=b"rt",
            expires_at=now,
            updated_at=now,
        )
        await backend.upsert_oauth_token(tok)
        assert await backend.get_oauth_token("github:42") == tok
    finally:
        await backend.close()


async def test_app_state_crud(tmp_path_sqlite: Path):
    backend = SQLiteBackend(db_path=tmp_path_sqlite)
    await backend.initialize()
    try:
        await backend.set_app_state("last_active_user_id", "local")
        assert await backend.get_app_state("last_active_user_id") == "local"
        assert await backend.get_app_state("missing") is None
    finally:
        await backend.close()


async def test_fk_cascade_on_user_delete(tmp_path_sqlite: Path):
    backend = SQLiteBackend(db_path=tmp_path_sqlite)
    await backend.initialize()
    try:
        now = datetime.now(timezone.utc)
        await backend.upsert_user(UserRow(id="local", display_name="L", auther_type=AutherType.DEFAULT, created_at=now))
        await backend.upsert_user_config(UserConfigRow(user_id="local", api_keys_encrypted=b"b", default_model=None, updated_at=now))
        await backend.delete_user("local")
        assert await backend.get_user_config("local") is None
    finally:
        await backend.close()


async def test_version_ahead_refuses(tmp_path_sqlite: Path):
    backend = SQLiteBackend(db_path=tmp_path_sqlite)
    await backend.initialize()
    await backend.set_app_state("schema_version", "999")
    await backend.close()
    backend2 = SQLiteBackend(db_path=tmp_path_sqlite)
    with pytest.raises(SchemaVersionMismatchError):
        await backend2.initialize()
```

- [ ] **Step 2: Run — expect ImportError.**

- [ ] **Step 3: Implement `agentlabx/providers/storage/sqlite_backend.py`**

```python
"""Async SQLite backend for AgentLabX foundation tables.

Opens a per-instance aiosqlite connection, runs pending migrations on
initialize(), exposes typed CRUD for users, user_configs, oauth_tokens,
and app_state. Enforces schema_version invariants.
"""
from __future__ import annotations

from datetime import datetime
from importlib import resources
from pathlib import Path

import aiosqlite

from agentlabx.providers.storage.models import (
    AppStateRow,
    AutherType,
    OAuthTokenRow,
    UserConfigRow,
    UserRow,
)


CURRENT_SCHEMA_VERSION = 1


class SchemaVersionMismatchError(Exception):
    """Raised when DB schema_version is ahead of or behind what the code supports."""


def _iso(dt: datetime) -> str:
    return dt.isoformat()


def _parse_iso(value: str) -> datetime:
    return datetime.fromisoformat(value)


class SQLiteBackend:
    def __init__(self, *, db_path: Path) -> None:
        self._db_path: Path = db_path
        self._conn: aiosqlite.Connection | None = None

    async def initialize(self) -> None:
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = await aiosqlite.connect(self._db_path)
        await self._conn.execute("PRAGMA foreign_keys = ON")
        await self._apply_migrations()
        version = await self.get_schema_version()
        if version > CURRENT_SCHEMA_VERSION:
            await self.close()
            raise SchemaVersionMismatchError(
                f"DB schema_version={version} is ahead of code version {CURRENT_SCHEMA_VERSION}"
            )
        if version < CURRENT_SCHEMA_VERSION:
            await self.close()
            raise SchemaVersionMismatchError(
                f"DB schema_version={version} is behind code version {CURRENT_SCHEMA_VERSION} "
                "— missing migrations"
            )

    async def close(self) -> None:
        if self._conn is not None:
            await self._conn.close()
            self._conn = None

    def _require_conn(self) -> aiosqlite.Connection:
        if self._conn is None:
            raise RuntimeError("SQLiteBackend not initialized — call initialize() first")
        return self._conn

    async def _apply_migrations(self) -> None:
        conn = self._require_conn()
        sql_001 = (
            resources.files("agentlabx.providers.storage.migrations")
            .joinpath("001_initial.sql")
            .read_text(encoding="utf-8")
        )
        await conn.executescript(sql_001)
        await conn.commit()

    # -- schema_version ---------------------------------------------------
    async def get_schema_version(self) -> int:
        raw = await self.get_app_state("schema_version")
        return int(raw) if raw is not None else 0

    async def set_schema_version(self, version: int) -> None:
        await self.set_app_state("schema_version", str(version))

    # -- users ------------------------------------------------------------
    async def upsert_user(self, user: UserRow) -> None:
        conn = self._require_conn()
        await conn.execute(
            "INSERT INTO users (id, display_name, auther_type, created_at) VALUES (?, ?, ?, ?) "
            "ON CONFLICT(id) DO UPDATE SET display_name=excluded.display_name, "
            "auther_type=excluded.auther_type",
            (user.id, user.display_name, user.auther_type.value, _iso(user.created_at)),
        )
        await conn.commit()

    async def get_user(self, user_id: str) -> UserRow | None:
        conn = self._require_conn()
        async with conn.execute(
            "SELECT id, display_name, auther_type, created_at FROM users WHERE id = ?",
            (user_id,),
        ) as cur:
            row = await cur.fetchone()
        if row is None:
            return None
        return UserRow(
            id=row[0],
            display_name=row[1],
            auther_type=AutherType(row[2]),
            created_at=_parse_iso(row[3]),
        )

    async def list_users(self) -> list[UserRow]:
        conn = self._require_conn()
        async with conn.execute(
            "SELECT id, display_name, auther_type, created_at FROM users ORDER BY created_at ASC"
        ) as cur:
            rows = await cur.fetchall()
        return [
            UserRow(
                id=r[0],
                display_name=r[1],
                auther_type=AutherType(r[2]),
                created_at=_parse_iso(r[3]),
            )
            for r in rows
        ]

    async def delete_user(self, user_id: str) -> None:
        conn = self._require_conn()
        await conn.execute("DELETE FROM users WHERE id = ?", (user_id,))
        await conn.commit()

    # -- user_configs -----------------------------------------------------
    async def upsert_user_config(self, cfg: UserConfigRow) -> None:
        conn = self._require_conn()
        await conn.execute(
            "INSERT INTO user_configs (user_id, api_keys_encrypted, default_model, updated_at) "
            "VALUES (?, ?, ?, ?) "
            "ON CONFLICT(user_id) DO UPDATE SET "
            "api_keys_encrypted=excluded.api_keys_encrypted, "
            "default_model=excluded.default_model, updated_at=excluded.updated_at",
            (cfg.user_id, cfg.api_keys_encrypted, cfg.default_model, _iso(cfg.updated_at)),
        )
        await conn.commit()

    async def get_user_config(self, user_id: str) -> UserConfigRow | None:
        conn = self._require_conn()
        async with conn.execute(
            "SELECT user_id, api_keys_encrypted, default_model, updated_at "
            "FROM user_configs WHERE user_id = ?",
            (user_id,),
        ) as cur:
            row = await cur.fetchone()
        if row is None:
            return None
        return UserConfigRow(
            user_id=row[0],
            api_keys_encrypted=row[1],
            default_model=row[2],
            updated_at=_parse_iso(row[3]),
        )

    # -- oauth_tokens -----------------------------------------------------
    async def upsert_oauth_token(self, tok: OAuthTokenRow) -> None:
        conn = self._require_conn()
        await conn.execute(
            "INSERT INTO oauth_tokens (user_id, provider, access_token_encrypted, "
            "refresh_token_encrypted, expires_at, updated_at) "
            "VALUES (?, ?, ?, ?, ?, ?) "
            "ON CONFLICT(user_id) DO UPDATE SET "
            "provider=excluded.provider, "
            "access_token_encrypted=excluded.access_token_encrypted, "
            "refresh_token_encrypted=excluded.refresh_token_encrypted, "
            "expires_at=excluded.expires_at, updated_at=excluded.updated_at",
            (
                tok.user_id,
                tok.provider,
                tok.access_token_encrypted,
                tok.refresh_token_encrypted,
                _iso(tok.expires_at) if tok.expires_at is not None else None,
                _iso(tok.updated_at),
            ),
        )
        await conn.commit()

    async def get_oauth_token(self, user_id: str) -> OAuthTokenRow | None:
        conn = self._require_conn()
        async with conn.execute(
            "SELECT user_id, provider, access_token_encrypted, refresh_token_encrypted, "
            "expires_at, updated_at FROM oauth_tokens WHERE user_id = ?",
            (user_id,),
        ) as cur:
            row = await cur.fetchone()
        if row is None:
            return None
        return OAuthTokenRow(
            user_id=row[0],
            provider=row[1],
            access_token_encrypted=row[2],
            refresh_token_encrypted=row[3],
            expires_at=_parse_iso(row[4]) if row[4] is not None else None,
            updated_at=_parse_iso(row[5]),
        )

    # -- app_state --------------------------------------------------------
    async def get_app_state(self, key: str) -> str | None:
        conn = self._require_conn()
        async with conn.execute("SELECT value FROM app_state WHERE key = ?", (key,)) as cur:
            row = await cur.fetchone()
        return row[0] if row is not None else None

    async def set_app_state(self, key: str, value: str) -> None:
        conn = self._require_conn()
        await conn.execute(
            "INSERT INTO app_state (key, value) VALUES (?, ?) "
            "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
            (key, value),
        )
        await conn.commit()
```

- [ ] **Step 4: Run + ruff + commit**

```bash
uv run pytest tests/providers/storage/test_sqlite_backend.py -v
uv run ruff check agentlabx/providers/storage/ tests/providers/storage/
git add agentlabx/providers/storage/sqlite_backend.py tests/providers/storage/test_sqlite_backend.py
git commit -m "feat(storage): async SQLite backend + migration runner (Stage 1 T9)"
```

Expected: 7 passed.

---

## Part D — User config layer

### Task 10: `agentlabx/user/config.py` — UserConfig dataclass

**Files:**
- Create: `agentlabx/user/config.py`
- Create: `tests/user/test_config.py`

- [ ] **Step 1: Write failing test**

```python
from __future__ import annotations

from datetime import datetime, timezone

from agentlabx.user.config import UserConfig


def test_user_config_fields():
    now = datetime.now(timezone.utc)
    cfg = UserConfig(
        user_id="local",
        api_keys={"gemini": "AIza..."},
        default_model="gemini/gemini-2.5-flash",
        updated_at=now,
    )
    assert cfg.user_id == "local"
    assert cfg.api_keys["gemini"] == "AIza..."
    assert cfg.default_model == "gemini/gemini-2.5-flash"


def test_user_config_empty_api_keys():
    cfg = UserConfig(user_id="x", api_keys={}, default_model=None, updated_at=datetime.now(timezone.utc))
    assert cfg.api_keys == {}
    assert cfg.default_model is None


def test_user_config_is_frozen():
    import dataclasses
    cfg = UserConfig(user_id="x", api_keys={}, default_model=None, updated_at=datetime.now(timezone.utc))
    try:
        cfg.user_id = "y"  # type: ignore[misc]
    except dataclasses.FrozenInstanceError:
        pass
    else:
        raise AssertionError("UserConfig should be frozen")
```

- [ ] **Step 2: Run — expect ImportError.**

- [ ] **Step 3: Implement**

```python
"""UserConfig dataclass — per-user non-secret + secret settings (plaintext in memory)."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime


@dataclass(frozen=True)
class UserConfig:
    user_id: str
    api_keys: dict[str, str] = field(default_factory=dict)
    default_model: str | None = None
    updated_at: datetime | None = None
```

- [ ] **Step 4: Run + ruff + commit**

```bash
uv run pytest tests/user/test_config.py -v
uv run ruff check agentlabx/user/config.py tests/user/test_config.py
git add agentlabx/user/config.py tests/user/test_config.py
git commit -m "feat(user): UserConfig dataclass (Stage 1 T10)"
```

Expected: 3 passed.

---

### Task 11: `agentlabx/user/store.py` — UserConfigStore (encrypted)

**Files:**
- Create: `agentlabx/user/store.py`
- Create: `tests/user/test_store.py`

- [ ] **Step 1: Write failing test**

```python
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from agentlabx.crypto.fernet import FernetCrypto
from agentlabx.providers.storage.models import AutherType, UserRow
from agentlabx.providers.storage.sqlite_backend import SQLiteBackend
from agentlabx.user.config import UserConfig
from agentlabx.user.store import UserConfigStore


async def _with_store(tmp_path_sqlite: Path):
    backend = SQLiteBackend(db_path=tmp_path_sqlite)
    await backend.initialize()
    await backend.upsert_user(
        UserRow(
            id="local",
            display_name="L",
            auther_type=AutherType.DEFAULT,
            created_at=datetime.now(timezone.utc),
        )
    )
    crypto = FernetCrypto(master_key=b"\x00" * 32)
    return backend, UserConfigStore(backend=backend, crypto=crypto)


async def test_save_then_load(tmp_path_sqlite: Path):
    backend, store = await _with_store(tmp_path_sqlite)
    try:
        cfg = UserConfig(user_id="local", api_keys={"gemini": "AIza"}, default_model=None, updated_at=None)
        saved = await store.save(cfg)
        assert saved.updated_at is not None
        loaded = await store.load("local")
        assert loaded is not None
        assert loaded.api_keys == {"gemini": "AIza"}
        assert loaded.default_model is None
    finally:
        await backend.close()


async def test_load_missing_returns_none(tmp_path_sqlite: Path):
    backend, store = await _with_store(tmp_path_sqlite)
    try:
        assert await store.load("nope") is None
    finally:
        await backend.close()


async def test_encryption_at_rest(tmp_path_sqlite: Path):
    backend, store = await _with_store(tmp_path_sqlite)
    try:
        await store.save(
            UserConfig(
                user_id="local",
                api_keys={"gemini": "PLAINTEXT_GEMINI_KEY"},
                default_model=None,
                updated_at=None,
            )
        )
        row = await backend.get_user_config("local")
        assert row is not None
        assert b"PLAINTEXT_GEMINI_KEY" not in row.api_keys_encrypted
    finally:
        await backend.close()


async def test_overwrite_updates_timestamp(tmp_path_sqlite: Path):
    backend, store = await _with_store(tmp_path_sqlite)
    try:
        s1 = await store.save(
            UserConfig(user_id="local", api_keys={"a": "1"}, default_model=None, updated_at=None)
        )
        s2 = await store.save(
            UserConfig(user_id="local", api_keys={"a": "2"}, default_model="m", updated_at=None)
        )
        assert s2.updated_at is not None and s1.updated_at is not None
        assert s2.updated_at >= s1.updated_at
        loaded = await store.load("local")
        assert loaded is not None
        assert loaded.api_keys == {"a": "2"}
        assert loaded.default_model == "m"
    finally:
        await backend.close()
```

- [ ] **Step 2: Run — expect ImportError.**

- [ ] **Step 3: Implement `agentlabx/user/store.py`**

```python
"""UserConfigStore — encrypted persistence for UserConfig on top of SQLiteBackend."""
from __future__ import annotations

import json
from dataclasses import replace
from datetime import datetime, timezone

from agentlabx.crypto.fernet import FernetCrypto
from agentlabx.providers.storage.models import UserConfigRow
from agentlabx.providers.storage.sqlite_backend import SQLiteBackend
from agentlabx.user.config import UserConfig


class UserConfigStore:
    def __init__(self, *, backend: SQLiteBackend, crypto: FernetCrypto) -> None:
        self._backend: SQLiteBackend = backend
        self._crypto: FernetCrypto = crypto

    async def save(self, cfg: UserConfig) -> UserConfig:
        now = datetime.now(timezone.utc)
        blob = self._crypto.encrypt(json.dumps(cfg.api_keys).encode("utf-8"))
        row = UserConfigRow(
            user_id=cfg.user_id,
            api_keys_encrypted=blob,
            default_model=cfg.default_model,
            updated_at=now,
        )
        await self._backend.upsert_user_config(row)
        return replace(cfg, updated_at=now)

    async def load(self, user_id: str) -> UserConfig | None:
        row = await self._backend.get_user_config(user_id)
        if row is None:
            return None
        decrypted = self._crypto.decrypt(row.api_keys_encrypted).decode("utf-8")
        keys_map = json.loads(decrypted)
        if not isinstance(keys_map, dict):
            raise TypeError(f"Decrypted api_keys is not a dict: {type(keys_map)!r}")
        api_keys: dict[str, str] = {str(k): str(v) for k, v in keys_map.items()}
        return UserConfig(
            user_id=row.user_id,
            api_keys=api_keys,
            default_model=row.default_model,
            updated_at=row.updated_at,
        )
```

- [ ] **Step 4: Run + ruff + commit**

```bash
uv run pytest tests/user/test_store.py -v
uv run ruff check agentlabx/user/store.py tests/user/test_store.py
git add agentlabx/user/store.py tests/user/test_store.py
git commit -m "feat(user): UserConfigStore encrypted at rest (Stage 1 T11)"
```

Expected: 4 passed.

---

### Task 12: `agentlabx/user/validator.py` — provider API-key probe

**Files:**
- Create: `agentlabx/user/validator.py`
- Create: `tests/user/test_validator.py`

- [ ] **Step 1: Write failing test**

```python
from __future__ import annotations

import httpx
import pytest
import respx

from agentlabx.user.validator import (
    ValidationResult,
    ValidationStatus,
    probe_provider,
)


@respx.mock
async def test_gemini_valid_key():
    respx.get("https://generativelanguage.googleapis.com/v1beta/models").mock(
        return_value=httpx.Response(200, json={"models": []})
    )
    result = await probe_provider("gemini", "AIza-valid")
    assert result == ValidationResult(provider="gemini", status=ValidationStatus.VALID, detail=None)


@respx.mock
async def test_gemini_invalid_key():
    respx.get("https://generativelanguage.googleapis.com/v1beta/models").mock(
        return_value=httpx.Response(401, json={"error": "bad key"})
    )
    result = await probe_provider("gemini", "AIza-bad")
    assert result.status is ValidationStatus.INVALID


@respx.mock
async def test_gemini_network_error_unverified():
    respx.get("https://generativelanguage.googleapis.com/v1beta/models").mock(
        side_effect=httpx.ConnectError("boom")
    )
    result = await probe_provider("gemini", "AIza-net")
    assert result.status is ValidationStatus.UNVERIFIED


async def test_unknown_provider_unverified():
    result = await probe_provider("totally-unknown", "xxx")
    assert result.status is ValidationStatus.UNVERIFIED
    assert "unknown" in (result.detail or "").lower()
```

- [ ] **Step 2: Run — expect ImportError.**

- [ ] **Step 3: Implement `agentlabx/user/validator.py`**

```python
"""Save-time API key validation via cheap provider probe endpoints.

One registered probe per provider. Unknown providers return UNVERIFIED.
Network errors → UNVERIFIED. 401/403 → INVALID. 2xx → VALID.
"""
from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from enum import Enum

import httpx


class ValidationStatus(str, Enum):
    VALID = "valid"
    INVALID = "invalid"
    UNVERIFIED = "unverified"


@dataclass(frozen=True)
class ValidationResult:
    provider: str
    status: ValidationStatus
    detail: str | None


ProbeFn = Callable[[str], Awaitable[ValidationResult]]


async def _probe_gemini(api_key: str) -> ValidationResult:
    url = "https://generativelanguage.googleapis.com/v1beta/models"
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(url, params={"key": api_key})
    except httpx.HTTPError as exc:
        return ValidationResult(provider="gemini", status=ValidationStatus.UNVERIFIED, detail=f"network: {exc}")
    if resp.status_code in (401, 403):
        return ValidationResult(provider="gemini", status=ValidationStatus.INVALID, detail="auth rejected")
    if 200 <= resp.status_code < 300:
        return ValidationResult(provider="gemini", status=ValidationStatus.VALID, detail=None)
    return ValidationResult(provider="gemini", status=ValidationStatus.UNVERIFIED, detail=f"status {resp.status_code}")


async def _probe_anthropic(api_key: str) -> ValidationResult:
    url = "https://api.anthropic.com/v1/models"
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(url, headers={"x-api-key": api_key, "anthropic-version": "2023-06-01"})
    except httpx.HTTPError as exc:
        return ValidationResult(provider="anthropic", status=ValidationStatus.UNVERIFIED, detail=f"network: {exc}")
    if resp.status_code in (401, 403):
        return ValidationResult(provider="anthropic", status=ValidationStatus.INVALID, detail="auth rejected")
    if 200 <= resp.status_code < 300:
        return ValidationResult(provider="anthropic", status=ValidationStatus.VALID, detail=None)
    return ValidationResult(provider="anthropic", status=ValidationStatus.UNVERIFIED, detail=f"status {resp.status_code}")


async def _probe_openai(api_key: str) -> ValidationResult:
    url = "https://api.openai.com/v1/models"
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(url, headers={"Authorization": f"Bearer {api_key}"})
    except httpx.HTTPError as exc:
        return ValidationResult(provider="openai", status=ValidationStatus.UNVERIFIED, detail=f"network: {exc}")
    if resp.status_code in (401, 403):
        return ValidationResult(provider="openai", status=ValidationStatus.INVALID, detail="auth rejected")
    if 200 <= resp.status_code < 300:
        return ValidationResult(provider="openai", status=ValidationStatus.VALID, detail=None)
    return ValidationResult(provider="openai", status=ValidationStatus.UNVERIFIED, detail=f"status {resp.status_code}")


_PROBES: dict[str, ProbeFn] = {
    "gemini": _probe_gemini,
    "anthropic": _probe_anthropic,
    "openai": _probe_openai,
}


async def probe_provider(provider: str, api_key: str) -> ValidationResult:
    probe = _PROBES.get(provider)
    if probe is None:
        return ValidationResult(
            provider=provider,
            status=ValidationStatus.UNVERIFIED,
            detail=f"unknown provider: {provider}",
        )
    return await probe(api_key)
```

- [ ] **Step 4: Run + ruff + commit**

```bash
uv run pytest tests/user/test_validator.py -v
uv run ruff check agentlabx/user/validator.py tests/user/test_validator.py
git add agentlabx/user/validator.py tests/user/test_validator.py
git commit -m "feat(user): save-time API key probe validator (Stage 1 T12)"
```

Expected: 4 passed.

---

## Part E — Auth core

### Task 13: `agentlabx/auth/user.py` — User dataclass

**Files:**
- Create: `agentlabx/auth/user.py`
- Create: `tests/auth/test_user.py`

- [ ] **Step 1: Write failing test**

```python
from __future__ import annotations

from datetime import datetime, timezone

from agentlabx.auth.user import User
from agentlabx.providers.storage.models import AutherType


def test_user_fields():
    now = datetime.now(timezone.utc)
    u = User(id="local", display_name="Local", auther_type=AutherType.DEFAULT, created_at=now)
    assert u.id == "local"
    assert u.auther_type is AutherType.DEFAULT


def test_user_from_row_round_trip():
    from agentlabx.providers.storage.models import UserRow
    now = datetime.now(timezone.utc)
    row = UserRow(id="github:1", display_name="G", auther_type=AutherType.OAUTH, created_at=now)
    user = User.from_row(row)
    assert user.id == "github:1"
    assert user.auther_type is AutherType.OAUTH
    back = user.to_row()
    assert back == row
```

- [ ] **Step 2: Run — expect ImportError.**

- [ ] **Step 3: Implement**

```python
"""User dataclass — identity only; no config or secrets."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from agentlabx.providers.storage.models import AutherType, UserRow


@dataclass(frozen=True)
class User:
    id: str
    display_name: str
    auther_type: AutherType
    created_at: datetime

    @classmethod
    def from_row(cls, row: UserRow) -> "User":
        return cls(
            id=row.id,
            display_name=row.display_name,
            auther_type=row.auther_type,
            created_at=row.created_at,
        )

    def to_row(self) -> UserRow:
        return UserRow(
            id=self.id,
            display_name=self.display_name,
            auther_type=self.auther_type,
            created_at=self.created_at,
        )
```

- [ ] **Step 4: Run + ruff + commit**

```bash
uv run pytest tests/auth/test_user.py -v
uv run ruff check agentlabx/auth/user.py tests/auth/test_user.py
git add agentlabx/auth/user.py tests/auth/test_user.py
git commit -m "feat(auth): User dataclass (Stage 1 T13)"
```

Expected: 2 passed.

---

### Task 14: `agentlabx/auth/auther.py` — Auther Protocol

**Files:**
- Create: `agentlabx/auth/auther.py`

This task defines the protocol only — no tests yet; tests land with each concrete auther.

- [ ] **Step 1: Write `agentlabx/auth/auther.py`**

```python
"""Auther protocol — what every auther implementation must provide.

Pluggable authers:
- DefaultAuther: auto-creates a single "local" user, always available.
- TokenAuther: accepts an opaque bearer token + display_name.
- OAuthAuther: drives OAuth 2.0 Device Authorization Flow against a
  provider config from config/providers.yaml.

Each auther's `ensure_bootstrap` is idempotent: safe to call many times.
"""
from __future__ import annotations

from typing import Protocol, runtime_checkable

from agentlabx.auth.user import User


@runtime_checkable
class Auther(Protocol):
    """Minimum shape every auther must satisfy."""

    name: str

    async def ensure_bootstrap(self) -> User:
        """Ensure at least one user exists for this auther and return the
        user to treat as 'current' post-bootstrap. Idempotent."""
        ...
```

- [ ] **Step 2: Commit**

```bash
git add agentlabx/auth/auther.py
git commit -m "feat(auth): Auther protocol (Stage 1 T14)"
```

---

### Task 15: `agentlabx/auth/default_auther.py`

**Files:**
- Create: `agentlabx/auth/default_auther.py`
- Create: `tests/auth/test_default_auther.py`

- [ ] **Step 1: Write failing test**

```python
from __future__ import annotations

from pathlib import Path

from agentlabx.auth.default_auther import DefaultAuther
from agentlabx.providers.storage.models import AutherType
from agentlabx.providers.storage.sqlite_backend import SQLiteBackend


async def _make(tmp_path_sqlite: Path) -> tuple[SQLiteBackend, DefaultAuther]:
    backend = SQLiteBackend(db_path=tmp_path_sqlite)
    await backend.initialize()
    return backend, DefaultAuther(backend=backend)


async def test_first_bootstrap_creates_local_user(tmp_path_sqlite: Path):
    backend, auther = await _make(tmp_path_sqlite)
    try:
        user = await auther.ensure_bootstrap()
        assert user.id == "local"
        assert user.auther_type is AutherType.DEFAULT
        persisted = await backend.get_user("local")
        assert persisted is not None
    finally:
        await backend.close()


async def test_bootstrap_is_idempotent(tmp_path_sqlite: Path):
    backend, auther = await _make(tmp_path_sqlite)
    try:
        u1 = await auther.ensure_bootstrap()
        u2 = await auther.ensure_bootstrap()
        assert u1 == u2
        users = await backend.list_users()
        assert len(users) == 1
    finally:
        await backend.close()


async def test_name_is_default(tmp_path_sqlite: Path):
    backend, auther = await _make(tmp_path_sqlite)
    try:
        assert auther.name == "default"
    finally:
        await backend.close()
```

- [ ] **Step 2: Run — expect ImportError.**

- [ ] **Step 3: Implement**

```python
"""DefaultAuther — single-user, auto-creates id='local'."""
from __future__ import annotations

from datetime import datetime, timezone

from agentlabx.auth.user import User
from agentlabx.providers.storage.models import AutherType, UserRow
from agentlabx.providers.storage.sqlite_backend import SQLiteBackend


class DefaultAuther:
    name: str = "default"
    USER_ID: str = "local"

    def __init__(self, *, backend: SQLiteBackend) -> None:
        self._backend: SQLiteBackend = backend

    async def ensure_bootstrap(self) -> User:
        existing = await self._backend.get_user(self.USER_ID)
        if existing is not None:
            return User.from_row(existing)
        row = UserRow(
            id=self.USER_ID,
            display_name="Local User",
            auther_type=AutherType.DEFAULT,
            created_at=datetime.now(timezone.utc),
        )
        await self._backend.upsert_user(row)
        return User.from_row(row)
```

- [ ] **Step 4: Run + ruff + commit**

```bash
uv run pytest tests/auth/test_default_auther.py -v
uv run ruff check agentlabx/auth/default_auther.py tests/auth/test_default_auther.py
git add agentlabx/auth/default_auther.py tests/auth/test_default_auther.py
git commit -m "feat(auth): DefaultAuther for single-user local bootstrap (Stage 1 T15)"
```

Expected: 3 passed.

---

### Task 16: `agentlabx/auth/session.py` — current-user persistence

**Files:**
- Create: `agentlabx/auth/session.py`
- Create: `tests/auth/test_session.py`

- [ ] **Step 1: Write failing test**

```python
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from agentlabx.auth.session import AuthSession
from agentlabx.auth.user import User
from agentlabx.providers.storage.models import AutherType, UserRow
from agentlabx.providers.storage.sqlite_backend import SQLiteBackend


async def _with(tmp_path_sqlite: Path) -> tuple[SQLiteBackend, AuthSession]:
    backend = SQLiteBackend(db_path=tmp_path_sqlite)
    await backend.initialize()
    now = datetime.now(timezone.utc)
    for uid in ("local", "github:1"):
        atype = AutherType.DEFAULT if uid == "local" else AutherType.OAUTH
        await backend.upsert_user(UserRow(id=uid, display_name=uid, auther_type=atype, created_at=now))
    return backend, AuthSession(backend=backend)


async def test_get_current_empty_returns_none(tmp_path_sqlite: Path):
    backend, session = await _with(tmp_path_sqlite)
    try:
        assert await session.get_current() is None
    finally:
        await backend.close()


async def test_set_and_get_current_persists(tmp_path_sqlite: Path):
    backend, session = await _with(tmp_path_sqlite)
    try:
        await session.set_current("local")
        u = await session.get_current()
        assert u is not None
        assert u.id == "local"
    finally:
        await backend.close()


async def test_set_current_unknown_user_raises(tmp_path_sqlite: Path):
    backend, session = await _with(tmp_path_sqlite)
    try:
        import pytest
        with pytest.raises(ValueError):
            await session.set_current("does-not-exist")
    finally:
        await backend.close()


async def test_swap_between_users(tmp_path_sqlite: Path):
    backend, session = await _with(tmp_path_sqlite)
    try:
        await session.set_current("local")
        await session.set_current("github:1")
        u = await session.get_current()
        assert u is not None
        assert u.id == "github:1"
    finally:
        await backend.close()


async def test_stale_current_resets_to_none(tmp_path_sqlite: Path):
    backend, session = await _with(tmp_path_sqlite)
    try:
        await session.set_current("local")
        await backend.delete_user("local")
        # After delete, the stored last_active points at a missing user → get_current returns None
        assert await session.get_current() is None
    finally:
        await backend.close()
```

- [ ] **Step 2: Run — expect ImportError.**

- [ ] **Step 3: Implement**

```python
"""AuthSession — persists 'current user' across restarts via app_state."""
from __future__ import annotations

from agentlabx.auth.user import User
from agentlabx.providers.storage.sqlite_backend import SQLiteBackend


LAST_ACTIVE_KEY = "last_active_user_id"


class AuthSession:
    def __init__(self, *, backend: SQLiteBackend) -> None:
        self._backend: SQLiteBackend = backend

    async def get_current(self) -> User | None:
        uid = await self._backend.get_app_state(LAST_ACTIVE_KEY)
        if uid is None:
            return None
        row = await self._backend.get_user(uid)
        if row is None:
            # Stale pointer — clear it so future reads don't repeatedly resolve nothing.
            await self._backend.set_app_state(LAST_ACTIVE_KEY, "")
            return None
        return User.from_row(row)

    async def set_current(self, user_id: str) -> None:
        row = await self._backend.get_user(user_id)
        if row is None:
            raise ValueError(f"cannot set current user — unknown user id {user_id!r}")
        await self._backend.set_app_state(LAST_ACTIVE_KEY, user_id)
```

- [ ] **Step 4: Run + ruff + commit**

```bash
uv run pytest tests/auth/test_session.py -v
uv run ruff check agentlabx/auth/session.py tests/auth/test_session.py
git add agentlabx/auth/session.py tests/auth/test_session.py
git commit -m "feat(auth): AuthSession — persistent current-user pointer (Stage 1 T16)"
```

Expected: 5 passed (adjust the `""` sentinel if needed — make `get_current` treat empty-string value as None).

---

## Part F — Authers continued

### Task 17: `config/providers.yaml` + `agentlabx/auth/providers.py` — provider config loader

**Files:**
- Create: `config/providers.yaml`
- Create: `agentlabx/auth/providers.py`
- Create: `tests/auth/test_providers.py`

- [ ] **Step 1: Write `config/providers.yaml`** (shipped with empty `client_id` fields — user fills in)

```yaml
# OAuth provider configs for Device Authorization Flow.
# To enable a provider, register an OAuth app with it, ensure device-flow is
# supported, and paste the resulting client_id into the matching entry below.
# Providers with an empty client_id are hidden from the frontend UI.

providers:
  - name: github
    display_name: "GitHub"
    client_id: ""
    device_code_url: "https://github.com/login/device/code"
    token_url: "https://github.com/login/oauth/access_token"
    userinfo_url: "https://api.github.com/user"
    scopes: ["read:user", "user:email"]

  - name: google
    display_name: "Google"
    client_id: ""
    device_code_url: "https://oauth2.googleapis.com/device/code"
    token_url: "https://oauth2.googleapis.com/token"
    userinfo_url: "https://openidconnect.googleapis.com/v1/userinfo"
    scopes: ["openid", "email", "profile"]
```

- [ ] **Step 2: Write failing test** `tests/auth/test_providers.py`

```python
from __future__ import annotations

from pathlib import Path

import pytest

from agentlabx.auth.providers import (
    ProviderConfig,
    ProviderNotConfiguredError,
    load_providers,
)


def _write(tmp_path: Path, text: str) -> Path:
    p = tmp_path / "providers.yaml"
    p.write_text(text, encoding="utf-8")
    return p


def test_loads_providers_with_client_id(tmp_path: Path):
    path = _write(tmp_path, """
providers:
  - name: github
    display_name: GitHub
    client_id: "abc123"
    device_code_url: "https://github.com/x"
    token_url: "https://github.com/y"
    userinfo_url: "https://github.com/u"
    scopes: ["read:user"]
""")
    providers = load_providers(path)
    assert len(providers) == 1
    p = providers[0]
    assert isinstance(p, ProviderConfig)
    assert p.name == "github"
    assert p.client_id == "abc123"


def test_skips_providers_with_empty_client_id(tmp_path: Path):
    path = _write(tmp_path, """
providers:
  - name: github
    display_name: GitHub
    client_id: ""
    device_code_url: a
    token_url: b
    userinfo_url: c
    scopes: []
  - name: google
    display_name: Google
    client_id: "set"
    device_code_url: a
    token_url: b
    userinfo_url: c
    scopes: []
""")
    providers = load_providers(path)
    assert [p.name for p in providers] == ["google"]


def test_missing_file_returns_empty_list(tmp_path: Path):
    assert load_providers(tmp_path / "does-not-exist.yaml") == []


def test_get_or_raise(tmp_path: Path):
    path = _write(tmp_path, """
providers:
  - name: github
    display_name: GitHub
    client_id: "abc"
    device_code_url: a
    token_url: b
    userinfo_url: c
    scopes: []
""")
    from agentlabx.auth.providers import get_provider_or_raise
    providers = load_providers(path)
    p = get_provider_or_raise(providers, "github")
    assert p.name == "github"
    with pytest.raises(ProviderNotConfiguredError):
        get_provider_or_raise(providers, "google")
```

- [ ] **Step 3: Run — expect ImportError.**

- [ ] **Step 4: Implement `agentlabx/auth/providers.py`**

```python
"""OAuth provider config loader.

Reads config/providers.yaml and returns a typed list of ProviderConfig.
Providers with empty client_id are filtered out (hidden from UI).
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import yaml


@dataclass(frozen=True)
class ProviderConfig:
    name: str
    display_name: str
    client_id: str
    device_code_url: str
    token_url: str
    userinfo_url: str
    scopes: list[str]


class ProviderNotConfiguredError(Exception):
    """Raised when a requested provider is missing or has no client_id."""


def load_providers(path: Path) -> list[ProviderConfig]:
    if not path.exists():
        return []
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    raw_list = data.get("providers") or []
    out: list[ProviderConfig] = []
    for item in raw_list:
        if not isinstance(item, dict):
            continue
        client_id = str(item.get("client_id") or "")
        if not client_id:
            continue
        out.append(
            ProviderConfig(
                name=str(item["name"]),
                display_name=str(item.get("display_name") or item["name"]),
                client_id=client_id,
                device_code_url=str(item["device_code_url"]),
                token_url=str(item["token_url"]),
                userinfo_url=str(item["userinfo_url"]),
                scopes=[str(s) for s in (item.get("scopes") or [])],
            )
        )
    return out


def get_provider_or_raise(providers: list[ProviderConfig], name: str) -> ProviderConfig:
    for p in providers:
        if p.name == name:
            return p
    raise ProviderNotConfiguredError(f"Provider {name!r} not configured in providers.yaml")
```

- [ ] **Step 5: Run + ruff + commit**

```bash
uv run pytest tests/auth/test_providers.py -v
uv run ruff check agentlabx/auth/providers.py config/providers.yaml tests/auth/test_providers.py
git add agentlabx/auth/providers.py config/providers.yaml tests/auth/test_providers.py
git commit -m "feat(auth): OAuth provider config loader + shipped providers.yaml (Stage 1 T17)"
```

Expected: 4 passed.

---

### Task 18: `agentlabx/auth/token_auther.py` — bearer token auther

**Files:**
- Create: `agentlabx/auth/token_auther.py`
- Create: `tests/auth/test_token_auther.py`

- [ ] **Step 1: Write failing test**

```python
from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from agentlabx.auth.token_auther import TokenAuther, TokenValidationError
from agentlabx.providers.storage.models import AutherType
from agentlabx.providers.storage.sqlite_backend import SQLiteBackend


async def _make(tmp_path_sqlite: Path) -> tuple[SQLiteBackend, TokenAuther]:
    backend = SQLiteBackend(db_path=tmp_path_sqlite)
    await backend.initialize()
    return backend, TokenAuther(backend=backend)


async def test_register_token_creates_user(tmp_path_sqlite: Path):
    backend, auther = await _make(tmp_path_sqlite)
    try:
        user = await auther.register_token(token="secret-token-abc", display_name="Bob")
        assert user.id.startswith("token:")
        assert user.display_name == "Bob"
        assert user.auther_type is AutherType.TOKEN
        persisted = await backend.get_user(user.id)
        assert persisted is not None
    finally:
        await backend.close()


async def test_id_is_hash_of_token(tmp_path_sqlite: Path):
    backend, auther = await _make(tmp_path_sqlite)
    try:
        user = await auther.register_token(token="t-123", display_name="B")
        expected = "token:" + hashlib.sha256(b"t-123").hexdigest()[:16]
        assert user.id == expected
    finally:
        await backend.close()


async def test_empty_token_rejected(tmp_path_sqlite: Path):
    backend, auther = await _make(tmp_path_sqlite)
    try:
        with pytest.raises(TokenValidationError):
            await auther.register_token(token="", display_name="x")
        with pytest.raises(TokenValidationError):
            await auther.register_token(token="abc", display_name="")
    finally:
        await backend.close()


async def test_register_idempotent(tmp_path_sqlite: Path):
    backend, auther = await _make(tmp_path_sqlite)
    try:
        u1 = await auther.register_token(token="same", display_name="D1")
        u2 = await auther.register_token(token="same", display_name="D2")
        assert u1.id == u2.id
        # display_name updates on re-register
        assert u2.display_name == "D2"
    finally:
        await backend.close()
```

- [ ] **Step 2: Run — expect ImportError.**

- [ ] **Step 3: Implement**

```python
"""TokenAuther — accept an opaque bearer token + display name, create/update user row.

The user id is a stable hash of the token bytes so re-registering the same
token returns the same user id; only display_name may be updated.
"""
from __future__ import annotations

import hashlib
from datetime import datetime, timezone

from agentlabx.auth.user import User
from agentlabx.providers.storage.models import AutherType, UserRow
from agentlabx.providers.storage.sqlite_backend import SQLiteBackend


class TokenValidationError(Exception):
    """Raised when a register attempt is malformed."""


class TokenAuther:
    name: str = "token"

    def __init__(self, *, backend: SQLiteBackend) -> None:
        self._backend: SQLiteBackend = backend

    async def register_token(self, *, token: str, display_name: str) -> User:
        if not token:
            raise TokenValidationError("token must not be empty")
        if not display_name:
            raise TokenValidationError("display_name must not be empty")
        user_id = "token:" + hashlib.sha256(token.encode("utf-8")).hexdigest()[:16]
        existing = await self._backend.get_user(user_id)
        created_at = existing.created_at if existing is not None else datetime.now(timezone.utc)
        row = UserRow(
            id=user_id,
            display_name=display_name,
            auther_type=AutherType.TOKEN,
            created_at=created_at,
        )
        await self._backend.upsert_user(row)
        return User.from_row(row)

    async def ensure_bootstrap(self) -> User:
        # TokenAuther is interactive — no implicit bootstrap user.
        raise RuntimeError(
            "TokenAuther has no implicit bootstrap; use register_token() from a route handler."
        )
```

- [ ] **Step 4: Run + ruff + commit**

```bash
uv run pytest tests/auth/test_token_auther.py -v
uv run ruff check agentlabx/auth/token_auther.py tests/auth/test_token_auther.py
git add agentlabx/auth/token_auther.py tests/auth/test_token_auther.py
git commit -m "feat(auth): TokenAuther — hash-id bearer token registration (Stage 1 T18)"
```

Expected: 4 passed.

---

### Task 19: `agentlabx/auth/oauth_auther.py` — Device Authorization Flow (start + poll)

**Files:**
- Create: `agentlabx/auth/oauth_auther.py`
- Create: `tests/auth/test_oauth_auther.py`

- [ ] **Step 1: Write failing test**

```python
from __future__ import annotations

from pathlib import Path

import httpx
import pytest
import respx

from agentlabx.auth.oauth_auther import (
    DeviceFlowPending,
    OAuthAuther,
    OAuthError,
)
from agentlabx.auth.providers import ProviderConfig
from agentlabx.crypto.fernet import FernetCrypto
from agentlabx.providers.storage.sqlite_backend import SQLiteBackend


def _github_cfg() -> ProviderConfig:
    return ProviderConfig(
        name="github",
        display_name="GitHub",
        client_id="cid",
        device_code_url="https://gh.test/device",
        token_url="https://gh.test/token",
        userinfo_url="https://gh.test/user",
        scopes=["read:user"],
    )


async def _make(tmp_path_sqlite: Path) -> tuple[SQLiteBackend, OAuthAuther]:
    backend = SQLiteBackend(db_path=tmp_path_sqlite)
    await backend.initialize()
    crypto = FernetCrypto(master_key=b"\x00" * 32)
    return backend, OAuthAuther(backend=backend, crypto=crypto, providers=[_github_cfg()])


@respx.mock
async def test_start_device_flow_returns_user_code(tmp_path_sqlite: Path):
    backend, auther = await _make(tmp_path_sqlite)
    try:
        respx.post("https://gh.test/device").mock(
            return_value=httpx.Response(
                200,
                json={
                    "device_code": "dc",
                    "user_code": "ABCD-1234",
                    "verification_uri": "https://gh.test/activate",
                    "interval": 5,
                    "expires_in": 900,
                },
            )
        )
        resp = await auther.start_device_flow("github")
        assert resp.user_code == "ABCD-1234"
        assert resp.verification_uri == "https://gh.test/activate"
        assert resp.interval == 5
        assert resp.expires_in == 900
        assert resp.poll_token  # non-empty opaque string
    finally:
        await backend.close()


@respx.mock
async def test_poll_pending_raises_pending(tmp_path_sqlite: Path):
    backend, auther = await _make(tmp_path_sqlite)
    try:
        respx.post("https://gh.test/device").mock(
            return_value=httpx.Response(200, json={
                "device_code": "dc", "user_code": "X", "verification_uri": "u",
                "interval": 1, "expires_in": 60,
            })
        )
        start = await auther.start_device_flow("github")
        respx.post("https://gh.test/token").mock(
            return_value=httpx.Response(200, json={"error": "authorization_pending"})
        )
        with pytest.raises(DeviceFlowPending):
            await auther.poll(start.poll_token)
    finally:
        await backend.close()


@respx.mock
async def test_poll_success_creates_user_and_stores_token(tmp_path_sqlite: Path):
    backend, auther = await _make(tmp_path_sqlite)
    try:
        respx.post("https://gh.test/device").mock(
            return_value=httpx.Response(200, json={
                "device_code": "dc", "user_code": "X", "verification_uri": "u",
                "interval": 1, "expires_in": 60,
            })
        )
        start = await auther.start_device_flow("github")
        respx.post("https://gh.test/token").mock(
            return_value=httpx.Response(200, json={
                "access_token": "at", "refresh_token": "rt", "expires_in": 3600, "token_type": "bearer",
            })
        )
        respx.get("https://gh.test/user").mock(
            return_value=httpx.Response(200, json={"id": 42, "login": "alice", "name": "Alice"})
        )
        user = await auther.poll(start.poll_token)
        assert user.id == "github:42"
        assert user.display_name == "Alice"
        tok = await backend.get_oauth_token("github:42")
        assert tok is not None
        assert tok.access_token_encrypted != b"at"  # encrypted, not plain
    finally:
        await backend.close()


@respx.mock
async def test_poll_access_denied_raises_oauth_error(tmp_path_sqlite: Path):
    backend, auther = await _make(tmp_path_sqlite)
    try:
        respx.post("https://gh.test/device").mock(
            return_value=httpx.Response(200, json={
                "device_code": "dc", "user_code": "X", "verification_uri": "u",
                "interval": 1, "expires_in": 60,
            })
        )
        start = await auther.start_device_flow("github")
        respx.post("https://gh.test/token").mock(
            return_value=httpx.Response(200, json={"error": "access_denied"})
        )
        with pytest.raises(OAuthError):
            await auther.poll(start.poll_token)
    finally:
        await backend.close()


async def test_unconfigured_provider_errors(tmp_path_sqlite: Path):
    backend, auther = await _make(tmp_path_sqlite)
    try:
        with pytest.raises(OAuthError):
            await auther.start_device_flow("unknown-provider")
    finally:
        await backend.close()
```

- [ ] **Step 2: Run — expect ImportError.**

- [ ] **Step 3: Implement**

```python
"""OAuthAuther — Device Authorization Flow (RFC 8628).

start_device_flow(provider) → POSTs device_code_url, stashes (device_code,
provider) keyed by opaque poll_token, returns user-facing user_code +
verification_uri + interval + expires_in.

poll(poll_token) → POSTs token_url. Raises DeviceFlowPending until the user
authorizes in their browser. On success, fetches userinfo, creates/updates
UserRow, encrypts and stores OAuthTokenRow, returns the User.
"""
from __future__ import annotations

import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

import httpx

from agentlabx.auth.providers import (
    ProviderConfig,
    ProviderNotConfiguredError,
    get_provider_or_raise,
)
from agentlabx.auth.user import User
from agentlabx.crypto.fernet import FernetCrypto
from agentlabx.providers.storage.models import (
    AutherType,
    OAuthTokenRow,
    UserRow,
)
from agentlabx.providers.storage.sqlite_backend import SQLiteBackend


class OAuthError(Exception):
    """Raised on terminal OAuth failures (access_denied, expired_token, ...)."""


class DeviceFlowPending(Exception):
    """Raised when the user hasn't completed the device flow yet."""


@dataclass(frozen=True)
class DeviceFlowStart:
    user_code: str
    verification_uri: str
    interval: int
    expires_in: int
    poll_token: str


@dataclass
class _PendingFlow:
    provider: ProviderConfig
    device_code: str
    started_at: datetime


class OAuthAuther:
    name: str = "oauth"

    def __init__(
        self,
        *,
        backend: SQLiteBackend,
        crypto: FernetCrypto,
        providers: list[ProviderConfig],
    ) -> None:
        self._backend: SQLiteBackend = backend
        self._crypto: FernetCrypto = crypto
        self._providers: list[ProviderConfig] = providers
        self._pending: dict[str, _PendingFlow] = {}

    def providers(self) -> list[ProviderConfig]:
        return list(self._providers)

    async def start_device_flow(self, provider_name: str) -> DeviceFlowStart:
        try:
            cfg = get_provider_or_raise(self._providers, provider_name)
        except ProviderNotConfiguredError as exc:
            raise OAuthError(str(exc)) from exc
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.post(
                cfg.device_code_url,
                data={"client_id": cfg.client_id, "scope": " ".join(cfg.scopes)},
                headers={"Accept": "application/json"},
            )
        if resp.status_code != 200:
            raise OAuthError(f"device_code request failed: status={resp.status_code}")
        data = resp.json()
        poll_token = secrets.token_urlsafe(32)
        self._pending[poll_token] = _PendingFlow(
            provider=cfg,
            device_code=str(data["device_code"]),
            started_at=datetime.now(timezone.utc),
        )
        return DeviceFlowStart(
            user_code=str(data["user_code"]),
            verification_uri=str(data.get("verification_uri") or data.get("verification_url") or ""),
            interval=int(data.get("interval") or 5),
            expires_in=int(data.get("expires_in") or 900),
            poll_token=poll_token,
        )

    async def poll(self, poll_token: str) -> User:
        pending = self._pending.get(poll_token)
        if pending is None:
            raise OAuthError("unknown poll_token")
        cfg = pending.provider
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.post(
                cfg.token_url,
                data={
                    "client_id": cfg.client_id,
                    "device_code": pending.device_code,
                    "grant_type": "urn:ietf:params:oauth:grant-type:device_code",
                },
                headers={"Accept": "application/json"},
            )
        data = resp.json() if resp.content else {}
        if "error" in data:
            code = str(data["error"])
            if code == "authorization_pending":
                raise DeviceFlowPending()
            if code == "slow_down":
                raise DeviceFlowPending()
            raise OAuthError(f"oauth error: {code}")
        access_token = str(data.get("access_token") or "")
        if not access_token:
            raise OAuthError("token endpoint returned no access_token")
        refresh_token = data.get("refresh_token")
        expires_in = int(data.get("expires_in") or 0)
        expires_at = (
            datetime.now(timezone.utc) + timedelta(seconds=expires_in) if expires_in > 0 else None
        )
        async with httpx.AsyncClient(timeout=15.0) as client:
            uresp = await client.get(
                cfg.userinfo_url,
                headers={"Authorization": f"Bearer {access_token}", "Accept": "application/json"},
            )
        if uresp.status_code != 200:
            raise OAuthError(f"userinfo request failed: status={uresp.status_code}")
        ui = uresp.json()
        provider_user_id = str(ui.get("id") or ui.get("sub") or "")
        if not provider_user_id:
            raise OAuthError("userinfo did not return a user id")
        display_name = str(ui.get("name") or ui.get("login") or ui.get("email") or provider_user_id)
        user_id = f"{cfg.name}:{provider_user_id}"

        existing = await self._backend.get_user(user_id)
        created_at = existing.created_at if existing is not None else datetime.now(timezone.utc)
        row = UserRow(
            id=user_id,
            display_name=display_name,
            auther_type=AutherType.OAUTH,
            created_at=created_at,
        )
        await self._backend.upsert_user(row)

        tok_row = OAuthTokenRow(
            user_id=user_id,
            provider=cfg.name,
            access_token_encrypted=self._crypto.encrypt(access_token.encode("utf-8")),
            refresh_token_encrypted=self._crypto.encrypt(str(refresh_token).encode("utf-8")) if refresh_token else None,
            expires_at=expires_at,
            updated_at=datetime.now(timezone.utc),
        )
        await self._backend.upsert_oauth_token(tok_row)
        del self._pending[poll_token]
        return User.from_row(row)
```

- [ ] **Step 4: Run + ruff + commit**

```bash
uv run pytest tests/auth/test_oauth_auther.py -v
uv run ruff check agentlabx/auth/oauth_auther.py tests/auth/test_oauth_auther.py
git add agentlabx/auth/oauth_auther.py tests/auth/test_oauth_auther.py
git commit -m "feat(auth): OAuthAuther — device flow + encrypted token storage (Stage 1 T19)"
```

Expected: 5 passed.

---

### Task 20: Full auth integration — first-run bootstrap + swap

**Files:**
- Create: `tests/integration/test_first_run.py`
- Create: `tests/integration/test_account_swap.py`

- [ ] **Step 1: Write `tests/integration/test_first_run.py`**

```python
from __future__ import annotations

from pathlib import Path

from agentlabx.auth.default_auther import DefaultAuther
from agentlabx.auth.session import AuthSession
from agentlabx.crypto.fernet import FernetCrypto
from agentlabx.crypto.keyring import load_or_create_master_key
from agentlabx.providers.storage.sqlite_backend import SQLiteBackend
from agentlabx.user.config import UserConfig
from agentlabx.user.store import UserConfigStore


async def test_first_run_happy_path(tmp_path_sqlite: Path, fake_keyring):
    backend = SQLiteBackend(db_path=tmp_path_sqlite)
    await backend.initialize()
    try:
        default_auther = DefaultAuther(backend=backend)
        user = await default_auther.ensure_bootstrap()
        session = AuthSession(backend=backend)
        await session.set_current(user.id)
        master_key = load_or_create_master_key(service="agentlabx-local", username="master")
        crypto = FernetCrypto(master_key=master_key)
        config_store = UserConfigStore(backend=backend, crypto=crypto)
        # Initial config is absent
        assert await config_store.load(user.id) is None
        # Save a key
        await config_store.save(UserConfig(user_id=user.id, api_keys={"gemini": "AIza..."}, default_model=None, updated_at=None))
        # Load returns decrypted
        loaded = await config_store.load(user.id)
        assert loaded is not None and loaded.api_keys == {"gemini": "AIza..."}
        # Current user persists
        current = await session.get_current()
        assert current is not None and current.id == user.id
    finally:
        await backend.close()
```

- [ ] **Step 2: Write `tests/integration/test_account_swap.py`**

```python
from __future__ import annotations

from pathlib import Path

from agentlabx.auth.default_auther import DefaultAuther
from agentlabx.auth.session import AuthSession
from agentlabx.auth.token_auther import TokenAuther
from agentlabx.crypto.fernet import FernetCrypto
from agentlabx.providers.storage.sqlite_backend import SQLiteBackend
from agentlabx.user.config import UserConfig
from agentlabx.user.store import UserConfigStore


async def test_swap_between_default_and_token_users(tmp_path_sqlite: Path):
    backend = SQLiteBackend(db_path=tmp_path_sqlite)
    await backend.initialize()
    try:
        crypto = FernetCrypto(master_key=b"\x00" * 32)
        store = UserConfigStore(backend=backend, crypto=crypto)
        local = await DefaultAuther(backend=backend).ensure_bootstrap()
        await store.save(UserConfig(user_id=local.id, api_keys={"gemini": "LOCAL_KEY"}, default_model=None, updated_at=None))
        alt = await TokenAuther(backend=backend).register_token(token="some-token", display_name="Alt")
        await store.save(UserConfig(user_id=alt.id, api_keys={"gemini": "ALT_KEY"}, default_model=None, updated_at=None))
        session = AuthSession(backend=backend)
        await session.set_current(local.id)
        cfg_local = await store.load(local.id)
        assert cfg_local is not None and cfg_local.api_keys == {"gemini": "LOCAL_KEY"}
        await session.set_current(alt.id)
        cfg_alt = await store.load(alt.id)
        assert cfg_alt is not None and cfg_alt.api_keys == {"gemini": "ALT_KEY"}
        cfg_local2 = await store.load(local.id)
        assert cfg_local2 is not None and cfg_local2.api_keys == {"gemini": "LOCAL_KEY"}
    finally:
        await backend.close()
```

- [ ] **Step 3: Run + commit**

```bash
uv run pytest tests/integration/ -v
uv run ruff check tests/integration/
git add tests/integration/
git commit -m "test(integration): first-run + account-swap happy paths (Stage 1 T20)"
```

Expected: 2 passed.

---

## Part G — Core utilities

### Task 21: `agentlabx/core/events.py` — generic EventBus

**Files:**
- Create: `agentlabx/core/events.py`
- Create: `tests/core/test_events.py`

- [ ] **Step 1: Write failing test**

```python
from __future__ import annotations

import asyncio

from agentlabx.core.events import Event, EventBus


async def test_publish_to_subscribed_handler():
    bus = EventBus()
    received: list[Event] = []

    async def handler(event: Event) -> None:
        received.append(event)

    bus.subscribe("thing_happened", handler)
    await bus.publish(Event(type="thing_happened", data={"x": 1}))
    assert len(received) == 1
    assert received[0].data == {"x": 1}


async def test_wildcard_handler_gets_all_events():
    bus = EventBus()
    received: list[Event] = []

    async def handler(event: Event) -> None:
        received.append(event)

    bus.subscribe("*", handler)
    await bus.publish(Event(type="a", data={}))
    await bus.publish(Event(type="b", data={}))
    assert [e.type for e in received] == ["a", "b"]


async def test_no_subscribers_publish_is_noop():
    bus = EventBus()
    await bus.publish(Event(type="noop", data={}))


async def test_multiple_subscribers_all_called():
    bus = EventBus()
    counter = 0

    async def h1(_: Event) -> None:
        nonlocal counter
        counter += 1

    async def h2(_: Event) -> None:
        nonlocal counter
        counter += 10

    bus.subscribe("x", h1)
    bus.subscribe("x", h2)
    await bus.publish(Event(type="x", data={}))
    assert counter == 11
```

- [ ] **Step 2: Run — expect ImportError.**

- [ ] **Step 3: Implement**

```python
"""Generic pub/sub event bus. No pipeline knowledge."""
from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from dataclasses import dataclass


EventData = dict[str, object]


@dataclass(frozen=True)
class Event:
    type: str
    data: EventData


EventHandler = Callable[[Event], Awaitable[None]]


class EventBus:
    def __init__(self) -> None:
        self._handlers: dict[str, list[EventHandler]] = {}

    def subscribe(self, event_type: str, handler: EventHandler) -> None:
        self._handlers.setdefault(event_type, []).append(handler)

    async def publish(self, event: Event) -> None:
        handlers = list(self._handlers.get(event.type, []))
        handlers.extend(self._handlers.get("*", []))
        if not handlers:
            return
        await asyncio.gather(*(h(event) for h in handlers))
```

- [ ] **Step 4: Run + ruff + commit**

```bash
uv run pytest tests/core/test_events.py -v
uv run ruff check agentlabx/core/events.py tests/core/test_events.py
git add agentlabx/core/events.py tests/core/test_events.py
git commit -m "feat(core): generic EventBus with wildcard subscribe (Stage 1 T21)"
```

Expected: 4 passed.

---

### Task 22: `agentlabx/core/registry.py` — generic typed plugin registry

**Files:**
- Create: `agentlabx/core/registry.py`
- Create: `tests/core/test_registry.py`

This is a generic `PluginRegistry[T]` — callers instantiate one per plugin kind (`PluginRegistry[BaseLLMProvider]`, `PluginRegistry[BaseTool]`, …) so every registered value and every resolved return is a concrete, typed `T`. No `object`, no `Any`, no heterogeneous union.

- [ ] **Step 1: Write failing test**

```python
from __future__ import annotations

from dataclasses import dataclass

import pytest

from agentlabx.core.registry import PluginNotFoundError, PluginRegistry


@dataclass
class _FakeLLM:
    name: str


def test_register_and_resolve_typed():
    reg: PluginRegistry[_FakeLLM] = PluginRegistry()
    impl = _FakeLLM(name="mock")
    reg.register("mock", impl)
    got = reg.resolve("mock")
    assert got is impl
    assert got.name == "mock"  # static type is _FakeLLM, not object


def test_resolve_missing_raises():
    reg: PluginRegistry[_FakeLLM] = PluginRegistry()
    with pytest.raises(PluginNotFoundError):
        reg.resolve("nope")


def test_register_duplicate_replaces():
    reg: PluginRegistry[_FakeLLM] = PluginRegistry()
    a = _FakeLLM(name="a")
    b = _FakeLLM(name="b")
    reg.register("dup", a)
    reg.register("dup", b)
    assert reg.resolve("dup") is b


def test_list_names_sorted():
    reg: PluginRegistry[_FakeLLM] = PluginRegistry()
    reg.register("z", _FakeLLM(name="z"))
    reg.register("a", _FakeLLM(name="a"))
    assert reg.list_names() == ["a", "z"]


def test_separate_registries_are_independent():
    llm_reg: PluginRegistry[_FakeLLM] = PluginRegistry()
    tool_reg: PluginRegistry[str] = PluginRegistry()
    llm_reg.register("m", _FakeLLM(name="m"))
    tool_reg.register("m", "a-tool")
    assert llm_reg.resolve("m").name == "m"
    assert tool_reg.resolve("m") == "a-tool"
```

- [ ] **Step 2: Run — expect ImportError.**

- [ ] **Step 3: Implement**

```python
"""Generic plugin registry. Callers pick a T per kind — no heterogeneous bag.

Usage:
    llm_registry: PluginRegistry[BaseLLMProvider] = PluginRegistry()
    tool_registry: PluginRegistry[BaseTool] = PluginRegistry()
"""
from __future__ import annotations

from typing import Generic, TypeVar


T = TypeVar("T")


class PluginNotFoundError(Exception):
    """Raised when a plugin name is not registered in this registry."""


class PluginRegistry(Generic[T]):
    def __init__(self) -> None:
        self._entries: dict[str, T] = {}

    def register(self, name: str, value: T) -> None:
        self._entries[name] = value

    def resolve(self, name: str) -> T:
        if name not in self._entries:
            raise PluginNotFoundError(f"plugin {name!r} not registered")
        return self._entries[name]

    def list_names(self) -> list[str]:
        return sorted(self._entries.keys())
```

- [ ] **Step 4: Run + ruff + commit**

```bash
uv run pytest tests/core/test_registry.py -v
uv run ruff check agentlabx/core/registry.py tests/core/test_registry.py
git add agentlabx/core/registry.py tests/core/test_registry.py
git commit -m "feat(core): generic PluginRegistry[T] — typed per-kind instantiation (Stage 1 T22)"
```

Expected: 5 passed.

---

### Task 23: `agentlabx/core/config.py` — Settings (trimmed)

**Files:**
- Create: `agentlabx/core/config.py`
- Create: `tests/core/test_config.py`

- [ ] **Step 1: Write failing test**

```python
from __future__ import annotations

from pathlib import Path

from agentlabx.core.config import Settings


def test_defaults():
    s = Settings()
    assert s.server_host == "127.0.0.1"
    assert s.server_port == 8000
    assert s.db_path == Path("data/agentlabx.db")
    assert s.providers_yaml_path == Path("config/providers.yaml")
    assert s.keyring_service == "agentlabx-local"
    assert s.log_level == "INFO"


def test_env_override(monkeypatch):
    monkeypatch.setenv("AGENTLABX_SERVER_PORT", "9001")
    monkeypatch.setenv("AGENTLABX_LOG_LEVEL", "DEBUG")
    s = Settings()
    assert s.server_port == 9001
    assert s.log_level == "DEBUG"
```

- [ ] **Step 2: Run — expect ImportError.**

- [ ] **Step 3: Implement**

```python
"""App-level settings. No LLM or pipeline fields — those are per-user or per-stage."""
from __future__ import annotations

from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="AGENTLABX_", case_sensitive=False)

    server_host: str = "127.0.0.1"
    server_port: int = 8000
    db_path: Path = Path("data/agentlabx.db")
    providers_yaml_path: Path = Path("config/providers.yaml")
    keyring_service: str = "agentlabx-local"
    keyring_username: str = "master"
    keyring_fallback_path: Path = Path("data/master.key")
    log_level: str = "INFO"
```

- [ ] **Step 4: Run + ruff + commit**

```bash
uv run pytest tests/core/test_config.py -v
uv run ruff check agentlabx/core/config.py tests/core/test_config.py
git add agentlabx/core/config.py tests/core/test_config.py
git commit -m "feat(core): Settings — server/db/providers/keyring fields only (Stage 1 T23)"
```

Expected: 2 passed.

---

## Part H — LLM providers

### Task 24: `agentlabx/providers/llm/base.py` — BaseLLMProvider + LLMResponse

**Files:**
- Create: `agentlabx/providers/llm/base.py`
- Create: `tests/providers/llm/test_base.py`

- [ ] **Step 1: Write failing test**

```python
from __future__ import annotations

from agentlabx.providers.llm.base import BaseLLMProvider, LLMResponse


def test_llm_response_fields():
    r = LLMResponse(
        content="hello",
        model="gemini/x",
        tokens_in=10,
        tokens_out=5,
        cost_usd=0.001,
    )
    assert r.content == "hello"
    assert r.tokens_in == 10


def test_base_is_abstract():
    import inspect
    assert inspect.isabstract(BaseLLMProvider)
```

- [ ] **Step 2: Run — expect ImportError.**

- [ ] **Step 3: Implement**

```python
"""BaseLLMProvider abstract interface. api_key is per-call, NEVER read from env."""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass(frozen=True)
class LLMResponse:
    content: str
    model: str
    tokens_in: int
    tokens_out: int
    cost_usd: float


class BaseLLMProvider(ABC):
    name: str = ""
    is_mock: bool = False

    @abstractmethod
    async def query(
        self,
        *,
        api_key: str,
        model: str,
        prompt: str,
        system_prompt: str = "",
        temperature: float = 0.0,
    ) -> LLMResponse:
        """Query the LLM. Caller supplies api_key — provider never looks it up."""
```

- [ ] **Step 4: Run + ruff + commit**

```bash
uv run pytest tests/providers/llm/test_base.py -v
uv run ruff check agentlabx/providers/llm/base.py tests/providers/llm/test_base.py
git add agentlabx/providers/llm/base.py tests/providers/llm/test_base.py
git commit -m "feat(llm): BaseLLMProvider + LLMResponse — api_key per call (Stage 1 T24)"
```

Expected: 2 passed.

---

### Task 25: `agentlabx/providers/llm/mock_provider.py`

**Files:**
- Create: `agentlabx/providers/llm/mock_provider.py`
- Create: `tests/providers/llm/test_mock_provider.py`

- [ ] **Step 1: Write failing test**

```python
from __future__ import annotations

from agentlabx.providers.llm.mock_provider import MockLLMProvider


async def test_returns_canned_response():
    p = MockLLMProvider()
    r = await p.query(api_key="anything", model="mock", prompt="hi", system_prompt="sys")
    assert r.model == "mock"
    assert r.content.startswith("[MOCK]")
    assert "hi" in r.content
    assert r.tokens_in > 0
    assert r.tokens_out > 0
    assert r.cost_usd == 0.0


async def test_is_mock_flag():
    assert MockLLMProvider.is_mock is True


async def test_api_key_is_not_stored():
    p = MockLLMProvider()
    _ = await p.query(api_key="secret", model="m", prompt="p")
    # no way to verify directly, but sanity check: instance holds no reference
    for attr in dir(p):
        if attr.startswith("_"):
            continue
        val = getattr(p, attr)
        if isinstance(val, str):
            assert "secret" not in val
```

- [ ] **Step 2: Run — expect ImportError.**

- [ ] **Step 3: Implement**

```python
"""Mock LLM provider for tests. Returns a canned echo of the prompt."""
from __future__ import annotations

from agentlabx.providers.llm.base import BaseLLMProvider, LLMResponse


class MockLLMProvider(BaseLLMProvider):
    name: str = "mock"
    is_mock: bool = True

    async def query(
        self,
        *,
        api_key: str,
        model: str,
        prompt: str,
        system_prompt: str = "",
        temperature: float = 0.0,
    ) -> LLMResponse:
        text = f"[MOCK] echo: {prompt}"
        return LLMResponse(
            content=text,
            model=model,
            tokens_in=max(1, len(prompt)),
            tokens_out=max(1, len(text)),
            cost_usd=0.0,
        )
```

- [ ] **Step 4: Run + ruff + commit**

```bash
uv run pytest tests/providers/llm/test_mock_provider.py -v
uv run ruff check agentlabx/providers/llm/mock_provider.py tests/providers/llm/test_mock_provider.py
git add agentlabx/providers/llm/mock_provider.py tests/providers/llm/test_mock_provider.py
git commit -m "feat(llm): MockLLMProvider for tests (Stage 1 T25)"
```

Expected: 3 passed.

---

### Task 26: `agentlabx/providers/llm/litellm_provider.py`

**Files:**
- Create: `agentlabx/providers/llm/litellm_provider.py`
- Create: `tests/providers/llm/test_litellm_provider.py`

- [ ] **Step 1: Write failing test**

```python
from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from agentlabx.providers.llm.litellm_provider import LiteLLMProvider


async def test_none_model_raises():
    p = LiteLLMProvider()
    with pytest.raises(ValueError):
        await p.query(api_key="k", model="", prompt="hi")


async def test_empty_api_key_raises():
    p = LiteLLMProvider()
    with pytest.raises(ValueError):
        await p.query(api_key="", model="gemini/x", prompt="hi")


async def test_query_calls_litellm_acompletion_with_api_key():
    p = LiteLLMProvider()
    fake_resp = {
        "choices": [{"message": {"content": "hello back"}}],
        "model": "gemini/test",
        "usage": {"prompt_tokens": 5, "completion_tokens": 3},
    }

    # Patch the litellm.acompletion symbol used by the provider
    with patch("agentlabx.providers.llm.litellm_provider.acompletion", new=AsyncMock(return_value=_FakeResp(fake_resp))):
        with patch("agentlabx.providers.llm.litellm_provider.completion_cost", return_value=0.0001):
            r = await p.query(api_key="AIza", model="gemini/test", prompt="hi", system_prompt="s")
    assert r.content == "hello back"
    assert r.model == "gemini/test"
    assert r.tokens_in == 5
    assert r.tokens_out == 3
    assert r.cost_usd == 0.0001


class _FakeResp:
    def __init__(self, data):
        self._data = data
        self.choices = [type("C", (), {"message": type("M", (), {"content": data["choices"][0]["message"]["content"]})()})()]
        self.model = data["model"]
        self.usage = type("U", (), data["usage"])()

    def model_dump(self):
        return self._data
```

- [ ] **Step 2: Run — expect ImportError.**

- [ ] **Step 3: Implement**

```python
"""LiteLLM passthrough provider. api_key per-call, zero env reads."""
from __future__ import annotations

from litellm import acompletion, completion_cost

from agentlabx.providers.llm.base import BaseLLMProvider, LLMResponse


class LiteLLMProvider(BaseLLMProvider):
    name: str = "litellm"
    is_mock: bool = False

    async def query(
        self,
        *,
        api_key: str,
        model: str,
        prompt: str,
        system_prompt: str = "",
        temperature: float = 0.0,
    ) -> LLMResponse:
        if not model:
            raise ValueError("model must be a non-empty string")
        if not api_key:
            raise ValueError("api_key must be a non-empty string")
        messages: list[dict[str, str]] = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})
        resp = await acompletion(
            model=model,
            messages=messages,
            api_key=api_key,
            temperature=temperature,
        )
        content = str(resp.choices[0].message.content or "")
        usage = resp.usage
        tokens_in = int(getattr(usage, "prompt_tokens", 0) or 0)
        tokens_out = int(getattr(usage, "completion_tokens", 0) or 0)
        try:
            cost = float(completion_cost(completion_response=resp) or 0.0)
        except Exception:
            cost = 0.0
        return LLMResponse(
            content=content,
            model=str(resp.model or model),
            tokens_in=tokens_in,
            tokens_out=tokens_out,
            cost_usd=cost,
        )
```

- [ ] **Step 4: Run + ruff + commit**

```bash
uv run pytest tests/providers/llm/test_litellm_provider.py -v
uv run ruff check agentlabx/providers/llm/litellm_provider.py tests/providers/llm/test_litellm_provider.py
git add agentlabx/providers/llm/litellm_provider.py tests/providers/llm/test_litellm_provider.py
git commit -m "feat(llm): LiteLLMProvider — api_key per call, no env reads (Stage 1 T26)"
```

Expected: 3 passed.

---

### Task 27: `agentlabx/providers/llm/traced.py` — tracing wrapper

**Files:**
- Create: `agentlabx/providers/llm/traced.py`
- Create: `tests/providers/llm/test_traced.py`

- [ ] **Step 1: Write failing test**

```python
from __future__ import annotations

from agentlabx.core.events import Event, EventBus
from agentlabx.providers.llm.mock_provider import MockLLMProvider
from agentlabx.providers.llm.traced import TracedLLMProvider


async def test_emits_request_and_response_events():
    bus = EventBus()
    received: list[Event] = []

    async def handler(event: Event) -> None:
        received.append(event)

    bus.subscribe("*", handler)
    traced = TracedLLMProvider(inner=MockLLMProvider(), event_bus=bus)
    await traced.query(api_key="k", model="mock", prompt="hi")
    types = [e.type for e in received]
    assert "llm_request" in types
    assert "llm_response" in types


async def test_no_stage_field_in_events():
    bus = EventBus()
    received: list[Event] = []

    async def handler(event: Event) -> None:
        received.append(event)

    bus.subscribe("*", handler)
    traced = TracedLLMProvider(inner=MockLLMProvider(), event_bus=bus)
    await traced.query(api_key="k", model="mock", prompt="hi")
    for e in received:
        assert "stage" not in e.data


async def test_api_key_not_in_events():
    bus = EventBus()
    received: list[Event] = []

    async def handler(event: Event) -> None:
        received.append(event)

    bus.subscribe("*", handler)
    traced = TracedLLMProvider(inner=MockLLMProvider(), event_bus=bus)
    await traced.query(api_key="SECRET_KEY_VALUE", model="mock", prompt="hi")
    for e in received:
        assert "SECRET_KEY_VALUE" not in str(e.data)
```

- [ ] **Step 2: Run — expect ImportError.**

- [ ] **Step 3: Implement**

```python
"""TracedLLMProvider — emits llm_request / llm_response events around an inner provider.

No pipeline/stage concepts. Redacts api_key before emitting.
"""
from __future__ import annotations

from agentlabx.core.events import Event, EventBus
from agentlabx.providers.llm.base import BaseLLMProvider, LLMResponse


class TracedLLMProvider(BaseLLMProvider):
    name: str = "traced"

    def __init__(self, *, inner: BaseLLMProvider, event_bus: EventBus) -> None:
        self._inner: BaseLLMProvider = inner
        self._bus: EventBus = event_bus
        self.is_mock = inner.is_mock

    async def query(
        self,
        *,
        api_key: str,
        model: str,
        prompt: str,
        system_prompt: str = "",
        temperature: float = 0.0,
    ) -> LLMResponse:
        await self._bus.publish(
            Event(
                type="llm_request",
                data={
                    "model": model,
                    "prompt_chars": len(prompt),
                    "system_prompt_chars": len(system_prompt),
                    "temperature": temperature,
                    "is_mock": self._inner.is_mock,
                },
            )
        )
        response = await self._inner.query(
            api_key=api_key,
            model=model,
            prompt=prompt,
            system_prompt=system_prompt,
            temperature=temperature,
        )
        await self._bus.publish(
            Event(
                type="llm_response",
                data={
                    "model": response.model,
                    "tokens_in": response.tokens_in,
                    "tokens_out": response.tokens_out,
                    "cost_usd": response.cost_usd,
                    "response_chars": len(response.content),
                    "is_mock": self._inner.is_mock,
                },
            )
        )
        return response
```

- [ ] **Step 4: Run + ruff + commit**

```bash
uv run pytest tests/providers/llm/test_traced.py -v
uv run ruff check agentlabx/providers/llm/traced.py tests/providers/llm/test_traced.py
git add agentlabx/providers/llm/traced.py tests/providers/llm/test_traced.py
git commit -m "feat(llm): TracedLLMProvider — emits llm_* events, no stage coupling (Stage 1 T27)"
```

Expected: 3 passed.

---

## Part I — FastAPI server

### Task 28: `agentlabx/server/deps.py` — DI container

**Files:**
- Create: `agentlabx/server/deps.py`

- [ ] **Step 1: Write the DI container**

```python
"""Server dependencies (DI).

Single holder of process-scoped singletons (backend, authers, store, auth session).
Route handlers get the holder via a FastAPI dependency and pick what they need.
"""
from __future__ import annotations

from dataclasses import dataclass

from agentlabx.auth.default_auther import DefaultAuther
from agentlabx.auth.oauth_auther import OAuthAuther
from agentlabx.auth.providers import load_providers
from agentlabx.auth.session import AuthSession
from agentlabx.auth.token_auther import TokenAuther
from agentlabx.core.config import Settings
from agentlabx.crypto.fernet import FernetCrypto
from agentlabx.crypto.keyring import load_or_create_master_key
from agentlabx.providers.storage.sqlite_backend import SQLiteBackend
from agentlabx.user.store import UserConfigStore


@dataclass
class ServerDeps:
    settings: Settings
    backend: SQLiteBackend
    crypto: FernetCrypto
    user_store: UserConfigStore
    auth_session: AuthSession
    default_auther: DefaultAuther
    token_auther: TokenAuther
    oauth_auther: OAuthAuther


async def build_deps(settings: Settings) -> ServerDeps:
    backend = SQLiteBackend(db_path=settings.db_path)
    await backend.initialize()
    master_key = load_or_create_master_key(
        service=settings.keyring_service,
        username=settings.keyring_username,
        fallback_path=settings.keyring_fallback_path,
    )
    crypto = FernetCrypto(master_key=master_key)
    user_store = UserConfigStore(backend=backend, crypto=crypto)
    auth_session = AuthSession(backend=backend)
    default_auther = DefaultAuther(backend=backend)
    token_auther = TokenAuther(backend=backend)
    providers = load_providers(settings.providers_yaml_path)
    oauth_auther = OAuthAuther(backend=backend, crypto=crypto, providers=providers)
    # First-run bootstrap: ensure 'local' user exists and is current if nothing set.
    user = await default_auther.ensure_bootstrap()
    if await auth_session.get_current() is None:
        await auth_session.set_current(user.id)
    return ServerDeps(
        settings=settings,
        backend=backend,
        crypto=crypto,
        user_store=user_store,
        auth_session=auth_session,
        default_auther=default_auther,
        token_auther=token_auther,
        oauth_auther=oauth_auther,
    )
```

- [ ] **Step 2: Commit**

```bash
uv run ruff check agentlabx/server/deps.py
git add agentlabx/server/deps.py
git commit -m "feat(server): DI container — build_deps wires auth+crypto+storage (Stage 1 T28)"
```

---

### Task 29: `agentlabx/server/app.py` — FastAPI factory

**Files:**
- Create: `agentlabx/server/app.py`
- Create: `tests/server/test_app.py`

- [ ] **Step 1: Write failing test**

```python
from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from agentlabx.core.config import Settings
from agentlabx.server.app import build_app


def test_app_starts_and_root_returns_ok(tmp_path_sqlite: Path, fake_keyring, monkeypatch):
    monkeypatch.setenv("AGENTLABX_DB_PATH", str(tmp_path_sqlite))
    monkeypatch.setenv("AGENTLABX_PROVIDERS_YAML_PATH", str(tmp_path_sqlite.parent / "providers.yaml"))
    app = build_app(Settings())
    with TestClient(app) as client:
        resp = client.get("/health")
        assert resp.status_code == 200
        assert resp.json() == {"status": "ok"}
```

- [ ] **Step 2: Run — expect ImportError.**

- [ ] **Step 3: Implement**

```python
"""FastAPI factory — builds the app with DI + routes."""
from __future__ import annotations

from contextlib import asynccontextmanager
from collections.abc import AsyncIterator

from fastapi import FastAPI

from agentlabx.core.config import Settings
from agentlabx.server.deps import ServerDeps, build_deps
from agentlabx.server.routes.auth import router as auth_router
from agentlabx.server.routes.user_config import router as config_router


def build_app(settings: Settings) -> FastAPI:
    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        deps = await build_deps(settings)
        app.state.deps = deps  # type: ignore[attr-defined]
        try:
            yield
        finally:
            await deps.backend.close()

    app = FastAPI(title="AgentLabX", version="0.2.0", lifespan=lifespan)

    @app.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    app.include_router(auth_router, prefix="/auth")
    app.include_router(config_router, prefix="/config")
    return app


def get_deps_from_request(request_state: object) -> ServerDeps:
    """Helper used by route handlers: request.app.state.deps."""
    deps = getattr(request_state, "deps", None)
    if deps is None:
        raise RuntimeError("ServerDeps not initialized — lifespan did not run")
    return deps  # type: ignore[no-any-return]
```

- [ ] **Step 4: Run + ruff + commit**

```bash
uv run pytest tests/server/test_app.py -v
uv run ruff check agentlabx/server/app.py tests/server/test_app.py
git add agentlabx/server/app.py tests/server/test_app.py
git commit -m "feat(server): FastAPI factory + lifespan + health endpoint (Stage 1 T29)"
```

Expected: 1 passed.

---

### Task 30: `agentlabx/server/routes/auth.py` — auth routes

**Files:**
- Create: `agentlabx/server/routes/auth.py`
- Create: `tests/server/test_auth_routes.py`

- [ ] **Step 1: Write failing test**

```python
from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from agentlabx.core.config import Settings
from agentlabx.server.app import build_app


def _client(tmp_path_sqlite: Path, monkeypatch) -> TestClient:
    monkeypatch.setenv("AGENTLABX_DB_PATH", str(tmp_path_sqlite))
    monkeypatch.setenv("AGENTLABX_PROVIDERS_YAML_PATH", str(tmp_path_sqlite.parent / "providers.yaml"))
    return TestClient(build_app(Settings()))


def test_me_returns_default_user(tmp_path_sqlite: Path, fake_keyring, monkeypatch):
    with _client(tmp_path_sqlite, monkeypatch) as client:
        r = client.get("/auth/me")
        assert r.status_code == 200
        body = r.json()
        assert body["id"] == "local"
        assert body["auther_type"] == "default"


def test_list_users_shows_local(tmp_path_sqlite: Path, fake_keyring, monkeypatch):
    with _client(tmp_path_sqlite, monkeypatch) as client:
        r = client.get("/auth/users")
        assert r.status_code == 200
        assert any(u["id"] == "local" for u in r.json()["users"])


def test_token_register_creates_and_swaps(tmp_path_sqlite: Path, fake_keyring, monkeypatch):
    with _client(tmp_path_sqlite, monkeypatch) as client:
        r = client.post("/auth/token", json={"token": "tok-1", "display_name": "Tok"})
        assert r.status_code == 200
        body = r.json()
        assert body["id"].startswith("token:")
        assert body["display_name"] == "Tok"
        me = client.get("/auth/me").json()
        assert me["id"] == body["id"]


def test_swap_to_unknown_user_is_404(tmp_path_sqlite: Path, fake_keyring, monkeypatch):
    with _client(tmp_path_sqlite, monkeypatch) as client:
        r = client.post("/auth/swap", json={"user_id": "does-not-exist"})
        assert r.status_code == 404


def test_oauth_start_unconfigured_is_422(tmp_path_sqlite: Path, fake_keyring, monkeypatch):
    with _client(tmp_path_sqlite, monkeypatch) as client:
        r = client.post("/auth/oauth/start", json={"provider": "github"})
        assert r.status_code == 422
```

- [ ] **Step 2: Run — expect ImportError.**

- [ ] **Step 3: Implement**

```python
"""Auth routes — /auth/me, /auth/users, /auth/swap, /auth/token, /auth/oauth/*."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from agentlabx.auth.oauth_auther import DeviceFlowPending, OAuthError
from agentlabx.auth.token_auther import TokenValidationError
from agentlabx.server.app import get_deps_from_request


router = APIRouter()


class UserOut(BaseModel):
    id: str
    display_name: str
    auther_type: str


class UsersOut(BaseModel):
    users: list[UserOut]


class SwapIn(BaseModel):
    user_id: str = Field(..., min_length=1)


class TokenIn(BaseModel):
    token: str = Field(..., min_length=1)
    display_name: str = Field(..., min_length=1)


class OAuthStartIn(BaseModel):
    provider: str = Field(..., min_length=1)


class OAuthStartOut(BaseModel):
    user_code: str
    verification_uri: str
    interval: int
    expires_in: int
    poll_token: str


class OAuthPollIn(BaseModel):
    poll_token: str = Field(..., min_length=1)


@router.get("/me")
async def me(request: Request) -> UserOut:
    deps = get_deps_from_request(request.app.state)
    user = await deps.auth_session.get_current()
    if user is None:
        raise HTTPException(status_code=401, detail="no current user")
    return UserOut(id=user.id, display_name=user.display_name, auther_type=user.auther_type.value)


@router.get("/users")
async def users(request: Request) -> UsersOut:
    deps = get_deps_from_request(request.app.state)
    rows = await deps.backend.list_users()
    return UsersOut(
        users=[
            UserOut(id=r.id, display_name=r.display_name, auther_type=r.auther_type.value)
            for r in rows
        ]
    )


@router.post("/swap")
async def swap(body: SwapIn, request: Request) -> UserOut:
    deps = get_deps_from_request(request.app.state)
    try:
        await deps.auth_session.set_current(body.user_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    current = await deps.auth_session.get_current()
    assert current is not None
    return UserOut(
        id=current.id, display_name=current.display_name, auther_type=current.auther_type.value
    )


@router.post("/token")
async def token(body: TokenIn, request: Request) -> UserOut:
    deps = get_deps_from_request(request.app.state)
    try:
        user = await deps.token_auther.register_token(token=body.token, display_name=body.display_name)
    except TokenValidationError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    await deps.auth_session.set_current(user.id)
    return UserOut(id=user.id, display_name=user.display_name, auther_type=user.auther_type.value)


@router.post("/oauth/start")
async def oauth_start(body: OAuthStartIn, request: Request) -> OAuthStartOut:
    deps = get_deps_from_request(request.app.state)
    try:
        start = await deps.oauth_auther.start_device_flow(body.provider)
    except OAuthError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return OAuthStartOut(
        user_code=start.user_code,
        verification_uri=start.verification_uri,
        interval=start.interval,
        expires_in=start.expires_in,
        poll_token=start.poll_token,
    )


@router.post("/oauth/poll")
async def oauth_poll(body: OAuthPollIn, request: Request) -> UserOut:
    deps = get_deps_from_request(request.app.state)
    try:
        user = await deps.oauth_auther.poll(body.poll_token)
    except DeviceFlowPending as exc:
        raise HTTPException(status_code=202, detail="authorization_pending") from exc
    except OAuthError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    await deps.auth_session.set_current(user.id)
    return UserOut(id=user.id, display_name=user.display_name, auther_type=user.auther_type.value)
```

- [ ] **Step 4: Run + ruff + commit**

```bash
uv run pytest tests/server/test_auth_routes.py -v
uv run ruff check agentlabx/server/routes/auth.py tests/server/test_auth_routes.py
git add agentlabx/server/routes/auth.py tests/server/test_auth_routes.py
git commit -m "feat(server): /auth routes — me, users, swap, token, oauth/start, oauth/poll (Stage 1 T30)"
```

Expected: 5 passed.

---

### Task 31: `agentlabx/server/routes/user_config.py` — config routes

**Files:**
- Create: `agentlabx/server/routes/user_config.py`
- Create: `tests/server/test_config_routes.py`

- [ ] **Step 1: Write failing test**

```python
from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import httpx
import respx
from fastapi.testclient import TestClient

from agentlabx.core.config import Settings
from agentlabx.server.app import build_app
from agentlabx.user.validator import ValidationResult, ValidationStatus


def _client(tmp_path_sqlite: Path, monkeypatch) -> TestClient:
    monkeypatch.setenv("AGENTLABX_DB_PATH", str(tmp_path_sqlite))
    monkeypatch.setenv("AGENTLABX_PROVIDERS_YAML_PATH", str(tmp_path_sqlite.parent / "providers.yaml"))
    return TestClient(build_app(Settings()))


def test_get_config_empty_on_fresh_install(tmp_path_sqlite: Path, fake_keyring, monkeypatch):
    with _client(tmp_path_sqlite, monkeypatch) as client:
        r = client.get("/config")
        assert r.status_code == 200
        body = r.json()
        assert body["api_keys"] == {}
        assert body["default_model"] is None


def test_put_config_valid_key(tmp_path_sqlite: Path, fake_keyring, monkeypatch):
    with _client(tmp_path_sqlite, monkeypatch) as client:
        async def _mock_probe(provider: str, api_key: str) -> ValidationResult:
            return ValidationResult(provider=provider, status=ValidationStatus.VALID, detail=None)

        with patch("agentlabx.server.routes.user_config.probe_provider", new=_mock_probe):
            r = client.put("/config", json={"api_keys": {"gemini": "AIza"}, "default_model": "g/m"})
        assert r.status_code == 200
        body = r.json()
        assert body["api_keys"] == {"gemini": "AIza"}
        assert body["validation"] == {"gemini": "valid"}


def test_put_config_invalid_key(tmp_path_sqlite: Path, fake_keyring, monkeypatch):
    with _client(tmp_path_sqlite, monkeypatch) as client:
        async def _mock_probe(provider: str, api_key: str) -> ValidationResult:
            return ValidationResult(provider=provider, status=ValidationStatus.INVALID, detail="bad")

        with patch("agentlabx.server.routes.user_config.probe_provider", new=_mock_probe):
            r = client.put("/config", json={"api_keys": {"gemini": "AIza"}, "default_model": None})
        assert r.status_code == 422
        body = r.json()
        assert "gemini" in body["detail"]["field_errors"]
```

- [ ] **Step 2: Run — expect ImportError.**

- [ ] **Step 3: Implement**

```python
"""/config routes — GET returns current user's config, PUT saves with validation."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from agentlabx.server.app import get_deps_from_request
from agentlabx.user.config import UserConfig
from agentlabx.user.validator import ValidationStatus, probe_provider


router = APIRouter()


class ConfigOut(BaseModel):
    user_id: str
    api_keys: dict[str, str]
    default_model: str | None
    validation: dict[str, str]


class ConfigPutIn(BaseModel):
    api_keys: dict[str, str] = Field(default_factory=dict)
    default_model: str | None = None


@router.get("")
async def get_config(request: Request) -> ConfigOut:
    deps = get_deps_from_request(request.app.state)
    user = await deps.auth_session.get_current()
    if user is None:
        raise HTTPException(status_code=401, detail="no current user")
    cfg = await deps.user_store.load(user.id)
    if cfg is None:
        return ConfigOut(user_id=user.id, api_keys={}, default_model=None, validation={})
    return ConfigOut(
        user_id=user.id, api_keys=cfg.api_keys, default_model=cfg.default_model, validation={}
    )


@router.put("")
async def put_config(body: ConfigPutIn, request: Request) -> ConfigOut:
    deps = get_deps_from_request(request.app.state)
    user = await deps.auth_session.get_current()
    if user is None:
        raise HTTPException(status_code=401, detail="no current user")

    validation: dict[str, str] = {}
    field_errors: dict[str, str] = {}
    for provider, api_key in body.api_keys.items():
        result = await probe_provider(provider, api_key)
        validation[provider] = result.status.value
        if result.status is ValidationStatus.INVALID:
            field_errors[provider] = result.detail or "invalid"

    if field_errors:
        raise HTTPException(status_code=422, detail={"field_errors": field_errors, "validation": validation})

    saved = await deps.user_store.save(
        UserConfig(
            user_id=user.id,
            api_keys=body.api_keys,
            default_model=body.default_model,
            updated_at=None,
        )
    )
    return ConfigOut(
        user_id=saved.user_id,
        api_keys=saved.api_keys,
        default_model=saved.default_model,
        validation=validation,
    )
```

- [ ] **Step 4: Run + ruff + commit**

```bash
uv run pytest tests/server/test_config_routes.py -v
uv run ruff check agentlabx/server/routes/user_config.py tests/server/test_config_routes.py
git add agentlabx/server/routes/user_config.py tests/server/test_config_routes.py
git commit -m "feat(server): /config routes with save-time validation (Stage 1 T31)"
```

Expected: 3 passed.

---

### Task 32: CLI entry point `agentlabx/cli/main.py`

**Files:**
- Create: `agentlabx/cli/__init__.py` (empty)
- Create: `agentlabx/cli/main.py`
- Create: `tests/cli/__init__.py` (empty)
- Create: `tests/cli/test_cli.py`

- [ ] **Step 1: Write failing test**

```python
from __future__ import annotations

from click.testing import CliRunner


def test_cli_help_lists_serve():
    from agentlabx.cli.main import cli
    runner = CliRunner()
    result = runner.invoke(cli, ["--help"])
    assert result.exit_code == 0
    assert "serve" in result.output


def test_serve_help_mentions_port():
    from agentlabx.cli.main import cli
    runner = CliRunner()
    result = runner.invoke(cli, ["serve", "--help"])
    assert result.exit_code == 0
    assert "--port" in result.output
```

- [ ] **Step 2: Run — expect ImportError.**

- [ ] **Step 3: Implement**

```python
"""CLI entry: `agentlabx serve` starts the FastAPI server via uvicorn."""
from __future__ import annotations

import click
import uvicorn

from agentlabx.core.config import Settings


@click.group()
def cli() -> None:
    """AgentLabX command-line interface."""


@cli.command()
@click.option("--host", default=None, help="Override AGENTLABX_SERVER_HOST")
@click.option("--port", default=None, type=int, help="Override AGENTLABX_SERVER_PORT")
def serve(host: str | None, port: int | None) -> None:
    """Run the AgentLabX HTTP server."""
    settings = Settings()
    uvicorn.run(
        "agentlabx.server.app:build_app",
        factory=False,
        host=host or settings.server_host,
        port=port or settings.server_port,
        reload=False,
    )
```

**Note:** uvicorn's `factory=True` + a zero-arg factory returning an app would be cleaner, but `build_app` takes `Settings`. Provide a zero-arg wrapper at module level in `server/app.py` when implementing:

```python
def build_default_app() -> FastAPI:
    return build_app(Settings())
```

And in the CLI, reference `"agentlabx.server.app:build_default_app"` with `factory=True`. Add this small helper in Task 29 when wiring uvicorn; the CLI test only checks help text so doesn't require a running server.

- [ ] **Step 4: Run + ruff + commit**

```bash
mkdir -p agentlabx/cli tests/cli
# (Touch empty __init__.py files first.)
uv run pytest tests/cli/test_cli.py -v
uv run ruff check agentlabx/cli/ tests/cli/
git add agentlabx/cli/ tests/cli/
git commit -m "feat(cli): agentlabx serve entry point (Stage 1 T32)"
```

Expected: 2 passed.

---

## Part J — Frontend bootstrap

Remaining frontend tasks are concise by design. Exact component markup is left to the implementer following shadcn conventions; this plan pins files, props, behaviours, API contracts, and tests.

### Task 33: Vite + React + TypeScript + Tailwind + shadcn scaffold

**Files created:** `web/package.json`, `web/tsconfig.json`, `web/vite.config.ts`, `web/tailwind.config.ts`, `web/postcss.config.js`, `web/components.json`, `web/index.html`, `web/src/main.tsx`, `web/src/App.tsx`, `web/src/index.css`.

**Acceptance:**
- `web/package.json` declares: `react@19`, `react-dom@19`, `typescript@5`, `vite@5`, `@vitejs/plugin-react`, `tailwindcss@3`, `postcss`, `autoprefixer`, `@tanstack/react-query@5`, `lucide-react` (icon lib shadcn uses).
- Dev deps: `@types/react`, `@types/react-dom`, `vitest@1`, `@testing-library/react@15`, `@testing-library/jest-dom`, `jsdom`, `@playwright/test`, `eslint@9`, `@typescript-eslint/*`, `prettier`.
- `tsconfig.json`: `"strict": true`, `"noImplicitAny": true`, `"noUncheckedIndexedAccess": true`, `"exactOptionalPropertyTypes": true`. **No `any` allowed** — mirrors backend rule for the frontend.
- `tailwind.config.ts` scans `./src/**/*.{ts,tsx}`; `index.css` has the three `@tailwind` directives.
- `components.json` configured for the default shadcn style with `@/components/ui` path alias.
- `vite.config.ts` proxies `/auth` and `/config` to `http://localhost:8000` in dev mode.
- `npm run dev` starts successfully; `npm run build` produces `web/dist/`.

**Steps:**
- [ ] Initialize: `cd web && npm init -y`, install deps listed above.
- [ ] `npx shadcn@latest init` → produces `components.json` + `src/lib/utils.ts` + base config.
- [ ] Write `tsconfig.json` with strict flags above.
- [ ] Write `vite.config.ts` with the proxy rules.
- [ ] Write `src/App.tsx` as a minimal `<div>AgentLabX</div>` placeholder; `src/main.tsx` wires `QueryClientProvider`.
- [ ] Install shadcn primitives we'll need: `npx shadcn@latest add button input dialog dropdown-menu badge select form label alert-dialog`.
- [ ] Verify: `npm run dev` (expect server on 5173 with placeholder page); `npm run build` (expect `dist/` output).
- [ ] Commit:

```bash
cd d:/GitHub/AgentLabX
git add web/package.json web/package-lock.json web/tsconfig.json web/vite.config.ts web/tailwind.config.ts web/postcss.config.js web/components.json web/index.html web/src/ .gitignore
git commit -m "feat(web): Vite + React 19 + TS + Tailwind + shadcn scaffold (Stage 1 T33)"
```

Ensure `.gitignore` covers `web/node_modules/`, `web/dist/`, `web/*.tsbuildinfo`.

---

### Task 34: Shared API client + types (`web/src/lib/api.ts`, `web/src/lib/types.ts`)

**Files:**
- Create: `web/src/lib/api.ts`
- Create: `web/src/lib/types.ts`
- Create: `web/src/lib/queryClient.ts`
- Create: `web/tests/unit/api.test.ts`

**Contract** (mirrors backend exactly):

```typescript
// types.ts
export type AutherType = "default" | "oauth" | "token";
export interface User { id: string; display_name: string; auther_type: AutherType; }
export interface UsersList { users: User[]; }
export interface Config { user_id: string; api_keys: Record<string, string>; default_model: string | null; validation: Record<string, "valid" | "invalid" | "unverified">; }
export interface OAuthStartResponse { user_code: string; verification_uri: string; interval: number; expires_in: number; poll_token: string; }
export type ValidationStatus = "valid" | "invalid" | "unverified";
export interface ApiError { status: number; detail: string | Record<string, unknown>; }
```

**api.ts responsibilities:** typed wrappers for `GET /auth/me`, `GET /auth/users`, `POST /auth/swap`, `POST /auth/token`, `POST /auth/oauth/start`, `POST /auth/oauth/poll`, `GET /config`, `PUT /config`. Each throws `ApiError` on non-2xx. NO `any` — every response is parsed into a typed interface.

**Tests (Vitest):**
- `fetchMe` parses `User` shape.
- `putConfig` on 422 throws `ApiError` with `detail.field_errors`.
- `pollOAuth` on 202 throws a recognizable "pending" signal the UI can loop on.
- Mock `fetch` via `vi.stubGlobal('fetch', ...)` returning typed `Response`-like objects.

**Acceptance:** `npm run test` passes; `tsc --noEmit` passes.

- [ ] Implement + test + commit.

```bash
git add web/src/lib/ web/tests/unit/api.test.ts
git commit -m "feat(web): typed API client + shared types + query client (Stage 1 T34)"
```

---

### Task 35: App shell (`App.tsx`) — routing + layout skeleton

**Files:**
- Modify: `web/src/App.tsx`
- Create: `web/src/features/layout/TopBar.tsx`
- Create: `web/tests/unit/App.test.tsx`

**Behaviour:**
- Top bar: "AgentLabX" title left, `<AccountMenu />` placeholder right (real one lands in T36).
- Main area: switches between `<HomeView />` (empty for Stage 1) and `<SettingsPanel />` based on route (`react-router-dom@6` added here).
- If `GET /config` returns `api_keys == {}` → renders a gated `<OnboardingModal />` forcing the user to Settings. The modal has a single CTA "Go to Settings."
- TanStack Query for `/auth/me` + `/config` with `staleTime: 30_000`.

**Tests:**
- App renders top bar + title.
- When `/config` mock returns empty api_keys → modal appears; clicking CTA navigates to `/settings`.
- When api_keys non-empty → modal does not appear.

**Acceptance:** tests green; `npm run build` still succeeds; no `any` anywhere.

- [ ] Implement + test + commit.

```bash
git add web/src/App.tsx web/src/features/layout/ web/tests/unit/App.test.tsx
git commit -m "feat(web): app shell + gated onboarding modal (Stage 1 T35)"
```

---

## Part K — Frontend components

Each task: implement the component, write a Vitest unit test, commit. Components live under `web/src/features/{auth,settings}/`. All use shadcn primitives. Zero `any`; every prop interface and event handler is typed.

### Task 36: `AccountMenu.tsx`

**Props:** none (reads `/auth/me` + `/auth/users` via TanStack Query).
**Behaviour:**
- Triggered by the avatar button in TopBar.
- Dropdown lists all users from `/auth/users`; clicking one calls `POST /auth/swap` and invalidates `/auth/me` + `/config` caches.
- "Add Account" item → opens `<LoginDialog />` (T37).
- "Sign out" item → swap to `"local"` user (always present).

**Tests:** dropdown opens on click; swap mutation fires; renders current user label.

Commit: `feat(web): AccountMenu (Stage 1 T36)`

---

### Task 37: `LoginDialog.tsx`

**Props:** `open: boolean`, `onOpenChange: (open: boolean) => void`.
**Behaviour:**
- Three cards rendered side-by-side (or stacked on mobile): Default / OAuth / Token.
- OAuth card: provider `<Select>` populated by a future `/auth/oauth/providers` endpoint (Stage 2 adds it; for Stage 1, the list is hardcoded from `providers.yaml` via a static import or a placeholder — implementer's call with a documented TODO).
  - **Implementer note:** to avoid a Stage-2-only endpoint dependency, Stage 1 ships a hardcoded provider list `[{name: "github", display_name: "GitHub"}, {name: "google", display_name: "Google"}]`. The backend `/auth/oauth/start` returns 422 if not configured, which the UI already handles (T38). This matches the "empty client_id hides provider" model — the error surfaces the right message.
- Default card → closes (already logged in as Default path).
- OAuth card "Continue" → `<DeviceFlowScreen />` (T38).
- Token card "Continue" → `<TokenLoginForm />` (T39).

**Tests:** renders three cards; clicking each opens the correct next component.

Commit: `feat(web): LoginDialog chooser (Stage 1 T37)`

---

### Task 38: `DeviceFlowScreen.tsx`

**Props:** `provider: string`, `onSuccess: (user: User) => void`, `onCancel: () => void`.
**Behaviour:**
- On mount: `POST /auth/oauth/start {provider}`. If 422 → show error "Provider not configured — see config/providers.yaml" + cancel button.
- On 200: display `user_code` in a big font with copy button, `<Button>Open {verification_uri}</Button>` (opens in a new tab), "Waiting for authorization…" spinner.
- Polls `POST /auth/oauth/poll {poll_token}` every `interval` seconds. On 202 keep polling. On 200 call `onSuccess(user)` and close. On 422 (other OAuth error) show error + cancel.
- Polling stops after `expires_in` seconds with "Authorization code expired — please retry."

**Tests:** mock `start` + `poll` endpoints with MSW or `vi.spyOn(api, ...)`; assert the polling cadence + success path + expired path.

Commit: `feat(web): DeviceFlowScreen with polling (Stage 1 T38)`

---

### Task 39: `TokenLoginForm.tsx`

**Props:** `onSuccess: (user: User) => void`, `onCancel: () => void`.
**Behaviour:** two inputs (token + display_name), both required; Submit → `POST /auth/token`. On success call `onSuccess`. On 422 show inline errors keyed to fields.

**Tests:** required validation; 422 path shows errors; 200 path calls onSuccess.

Commit: `feat(web): TokenLoginForm (Stage 1 T39)`

---

### Task 40: `SettingsPanel.tsx`

**Route:** `/settings`.
**Behaviour:**
- Loads `/config` via TanStack Query.
- API Keys section: for each of `["gemini", "anthropic", "openai"]` renders an `<ApiKeyField />` (T41) bound to that provider slot.
- Default Model section: `<DefaultModelSelect />` — shadcn `<Select>` (or freeform combobox if shadcn combobox is easy) with suggestions derived from which providers have a valid key; value bound to `config.default_model`.
- "Save" button: `PUT /config` with the whole blob. On 200 show per-provider badges from `validation`. On 422 show per-field error from `detail.field_errors` (red badge next to the offending field) AND save the valid fields (backend already does this via partial save — UI just reflects).

**Tests:** mock GET/PUT endpoints; empty → shows all three fields empty; saving a valid key shows green badge; saving an invalid key shows red badge and preserves other fields.

Commit: `feat(web): SettingsPanel (Stage 1 T40)`

---

### Task 41: `ApiKeyField.tsx`

**Props:** `provider: string`, `value: string`, `status: ValidationStatus | "untouched"`, `onChange: (next: string) => void`.
**Behaviour:** masked `<Input type="password">` with a reveal toggle (eye icon); right-aligned `<Badge>` whose variant depends on `status` (green/valid, red/invalid, gray/unverified, hidden/untouched); on blur trims whitespace.

**Tests:** masks by default; reveal toggle works; badge color matches status; trim-on-blur.

Commit: `feat(web): ApiKeyField (Stage 1 T41)`

---

## Part L — E2E + final checks

### Task 42: Playwright happy-path e2e

**Files:**
- Create: `web/playwright.config.ts`
- Create: `web/tests/e2e/happy-path.spec.ts`

**Scenario:**
1. Start a fresh backend (fixture boots uvicorn against a tmp SQLite + fake keyring backend — can be done via a pytest fixture that starts uvicorn in a subprocess OR via a short Python bootstrap Playwright invokes).
2. Start the Vite dev server (Playwright `webServer` config).
3. Navigate to `http://localhost:5173/`.
4. Assert: top bar shows "Local User"; onboarding modal appears.
5. Click "Go to Settings" → `/settings`.
6. Paste a stub Gemini key (backend validator mocked to return valid via a test-only endpoint or env switch).
7. Click Save → green "Valid" badge appears.
8. Reload the page → key persisted, no onboarding modal, current user still "Local User."

**Acceptance:** `npx playwright test` passes.

- [ ] Implement + commit: `test(e2e): happy-path login → save key → persist across reload (Stage 1 T42)`

---

### Task 43: Final ruff / typecheck / coverage sweep

- [ ] Run the full backend check:

```bash
uv run ruff check .
uv run pytest --cov=agentlabx --cov-report=term-missing
```

Expected:
- `ruff`: `All checks passed!` — zero violations.
- Coverage: 100% for `auth/`, `crypto/`, `user/`, `providers/storage/`; ≥85% elsewhere.

- [ ] Run the full frontend check:

```bash
cd web
npm run lint
npx tsc --noEmit
npm run test
```

Expected: all pass.

- [ ] If anything fails, fix it. No skipping, no weakening contracts.

- [ ] Commit any coverage-gap follow-up tests with message `test: close coverage gaps (Stage 1 T43)`.

---

### Task 44: Tag Stage 1 complete

- [ ] Run the full check one last time (backend + frontend + e2e). All green.

- [ ] Tag:

```bash
git tag -a stage1-complete -m "Stage 1 foundation: auth + encrypted user config + frontend settings panel"
git push origin main
git push origin stage1-complete
```

- [ ] Announce to user: Stage 1 complete with verification command outputs.

---

## Self-review — spec coverage

| Spec section | Tasks |
|---|---|
| §1 Purpose | all tasks collectively |
| §2.1 Goals (1 default bootstrap) | T15, T20, T28 |
| §2.1 Goals (2 account swap + OAuth + token) | T16, T17, T18, T19, T30 |
| §2.1 Goals (3 encrypted api_keys + default_model) | T4, T5, T10, T11 |
| §2.1 Goals (4 save-time validation) | T12, T31 |
| §2.1 Goals (5 frontend panel) | T33-T41 |
| §2.1 Goals (6 ruff ANN strict typing) | T1 + enforced every task |
| §2.2 Non-goals (MCP tool integration) | explicitly excluded |
| §3 Module layout | T2 (scaffold), T4-T32 (implementations) |
| §4.1 First-run flow | T15, T28 (bootstrap), T35, T40 (UI), T42 (e2e) |
| §4.2 Save + validate flow | T12, T31, T40, T41 |
| §4.3 LLM query flow | T24-T27 |
| §4.4 OAuth device flow | T17, T19, T30, T38 |
| §4.5 Account swap | T16, T30, T36 |
| §4.6 Token refresh | (deferred — store refresh_token in T19, actual refresh usage out of Stage 1 scope) |
| §5 Storage schema | T7, T8, T9 |
| §6 Frontend layout + components | T33-T41 |
| §7 Error handling (crypto, auth, validation) | T4 fallback, T5 DecryptionError, T9 SchemaVersionMismatch, T12 probe policy, T19 OAuthError, T30 HTTPException mapping, T31 422 shape |
| §8 Testing (unit/integration/routes/frontend/typing/determinism/coverage) | every task + T42 (e2e) + T43 (sweep) |
| §9 Out of scope | explicitly deferred |
| §10 Deliverables | all 44 tasks |

**Spec requirements with no task:** none identified.

**Placeholder scan:** no "TBD", "TODO" (except explicit notes flagging Stage-2-only gaps), no "similar to Task N" — every step contains concrete code or an explicit acceptance contract.

**Type consistency:** `User`, `UserConfig`, `UserRow`, `UserConfigRow`, `OAuthTokenRow`, `AppStateRow`, `ProviderConfig`, `LLMResponse`, `Event`, `ValidationResult`, `ValidationStatus`, `AutherType`, `PluginRegistry[T]`, `ServerDeps` — all defined once and reused verbatim across later tasks.

---

## Execution handoff

Plan complete and saved to `docs/superpowers/plans/2026-04-15-stage1-auth-userconfig-foundation.md`. Two execution options:

1. **Subagent-Driven (recommended)** — I dispatch a fresh subagent per task, review between tasks, fast iteration. Uses `superpowers:subagent-driven-development`.
2. **Inline Execution** — Execute tasks in this session using `superpowers:executing-plans`, batch execution with checkpoints.

Which approach?

