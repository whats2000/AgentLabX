# Stage A2 — LLM Provider Module Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship the LLM provider module — a LiteLLM-backed router with per-user encrypted key wiring, event-traced cost tracking, budget enforcement, retry/backoff, a test-only mock LLM server, and `providers.yaml` catalog — so that any later stage can call `complete()` and get a response from the user's chosen provider with full observability.

**Architecture:** A `BaseLLMProvider` Protocol defines the call contract (`complete()` → `LLMResponse`). `LiteLLMProvider` implements it by routing through LiteLLM with per-user API keys decrypted from the credential store (A1). `TracedLLMProvider` wraps any provider and emits `LLMCalled` events to the event bus (A1) with token counts, cost, and redacted prompt previews. A standalone **mock LLM server** (test-only, lives in `tests/`) implements the OpenAI-compatible `/v1/chat/completions` API so that all tests — including integration tests — exercise the real `LiteLLMProvider` → LiteLLM → HTTP pipeline rather than bypassing it with a fake class. A `ProviderCatalog` loads `providers.yaml` (admin-editable list of available models/providers). A `BudgetTracker` enforces per-project cost caps. The module integrates into the existing FastAPI server via a new `/api/llm/*` router for model listing.

**Tech Stack:** Python 3.12 · LiteLLM · pydantic · FastAPI (A1) · SQLAlchemy async (A1) · Fernet encryption (A1) · EventBus (A1) · pytest + pytest-asyncio + pytest-dotenv · ruff (`ANN` incl. `ANN401`) · mypy strict.

**Test environment setup:** Real-LLM tests (`pytest -m real_llm`) require at least one provider API key. Copy `.env.example` to `.env` and fill in a key — `pytest-dotenv` auto-loads it before test collection. No manual `export` needed.

**Verification gate (SRS §4.2 Stage A2):**

1. A real LLM call against ≥1 provider succeeds and emits an `LLMCalled` event with token count + cost.
2. Budget cap halts execution when the per-project spend exceeds the cap.
3. Mock LLM server produces deterministic responses; LiteLLMProvider exercises the full HTTP path against it.
4. Per-user encrypted key wiring: user A's key is used for user A's calls; user B's key is isolated.
5. All ruff (`ANN`/`ANN401`) and mypy `--strict` checks pass on both production and test code.

---

## File Structure (locked in before task decomposition)

```
agentlabx/
├── llm/
│   ├── __init__.py                 # re-exports: BaseLLMProvider, LLMRequest, LLMResponse, etc.
│   ├── protocol.py                 # BaseLLMProvider Protocol + LLMRequest/LLMResponse dataclasses
│   ├── litellm_provider.py         # LiteLLMProvider — routes calls through litellm.acompletion
│   ├── traced_provider.py          # TracedLLMProvider — wraps any BaseLLMProvider, emits events
│   ├── budget.py                   # BudgetTracker — per-project cost tracking + cap enforcement
│   ├── catalog.py                  # ProviderCatalog — loads providers.yaml, lists models
│   └── key_resolver.py             # resolve_api_key() — decrypt user's credential for a provider

providers.yaml                      # provider catalog (shipped with the repo, admin-editable)

tests/
├── mock_llm_server.py              # Standalone OpenAI-compatible mock server (test-only)
├── unit/
│   └── llm/
│       ├── __init__.py
│       ├── test_protocol.py        # LLMRequest/LLMResponse construction + validation
│       ├── test_traced_provider.py # TracedLLMProvider event emission + redaction (inline stub)
│       ├── test_budget.py          # BudgetTracker arithmetic + cap enforcement + async concurrency
│       ├── test_catalog.py         # ProviderCatalog loading + validation + malformed YAML
│       ├── test_litellm_helpers.py # _scoped_env + _build_messages unit tests
│       └── test_key_resolver.py    # key decryption from credential store
└── integration/
    ├── test_llm_mock_server.py     # LiteLLMProvider end-to-end against mock server
    ├── test_llm_router.py          # /api/llm/* endpoints via AsyncClient(ASGI)
    └── test_llm_real_provider.py   # Real-LLM verification gate (requires API key)
```

**No mock provider class in the production package.** All mock infrastructure lives in `tests/`.

---

## Task 1: LLM Protocol — `LLMRequest`, `LLMResponse`, `BaseLLMProvider`

**Files:**
- Create: `agentlabx/llm/__init__.py`
- Create: `agentlabx/llm/protocol.py`
- Create: `tests/unit/llm/__init__.py`
- Create: `tests/unit/llm/test_protocol.py`
- Modify: `pyproject.toml` (add `pytest-dotenv` to dev deps + env_file config)
- Modify: `.env.example` (already cleaned up — verify it matches A1/A2 reality)

- [ ] **Step 1: Add `pytest-dotenv` to dev dependencies**

In `pyproject.toml`, add to `[project.optional-dependencies] dev`:
```
    "pytest-dotenv>=0.5",
```

Add to `[tool.pytest.ini_options]`:
```
env_files = [".env"]
```

This makes `pytest` auto-load `.env` (if present) before test collection. Real-LLM tests pick up API keys without manual shell exports. The `.env` file is gitignored.

Run: `uv sync`

- [ ] **Step 2: Write the failing test**

```python
# tests/unit/llm/test_protocol.py
from __future__ import annotations

from agentlabx.llm.protocol import LLMRequest, LLMResponse, MessageRole


def test_llm_request_construction() -> None:
    req = LLMRequest(
        model="test-provider/test-model",
        messages=[
            {"role": MessageRole.SYSTEM, "content": "You are helpful."},
            {"role": MessageRole.USER, "content": "Hello"},
        ],
        temperature=0.7,
        max_tokens=1024,
    )
    assert req.model == "test-provider/test-model"
    assert len(req.messages) == 2
    assert req.temperature == 0.7
    assert req.max_tokens == 1024


def test_llm_request_defaults() -> None:
    req = LLMRequest(
        model="test-provider/default-model",
        messages=[{"role": MessageRole.USER, "content": "Hi"}],
    )
    assert req.temperature is None
    assert req.max_tokens is None
    assert req.system_prompt is None


def test_llm_response_construction() -> None:
    resp = LLMResponse(
        content="Hello there!",
        model="test-provider/test-model",
        prompt_tokens=10,
        completion_tokens=5,
        total_tokens=15,
        cost_usd=0.0003,
    )
    assert resp.content == "Hello there!"
    assert resp.prompt_tokens == 10
    assert resp.completion_tokens == 5
    assert resp.total_tokens == 15
    assert resp.cost_usd == 0.0003


def test_llm_response_zero_cost_allowed() -> None:
    resp = LLMResponse(
        content="ok",
        model="local-model",
        prompt_tokens=0,
        completion_tokens=0,
        total_tokens=0,
        cost_usd=0.0,
    )
    assert resp.cost_usd == 0.0


def test_message_role_values() -> None:
    assert MessageRole.SYSTEM == "system"
    assert MessageRole.USER == "user"
    assert MessageRole.ASSISTANT == "assistant"
```

- [ ] **Step 3: Run test to verify it fails**

Run: `uv run pytest tests/unit/llm/test_protocol.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'agentlabx.llm'`

- [ ] **Step 4: Write minimal implementation**

```python
# agentlabx/llm/__init__.py
from __future__ import annotations
```

```python
# agentlabx/llm/protocol.py
from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from enum import StrEnum
from typing import Protocol, runtime_checkable


class MessageRole(StrEnum):
    SYSTEM = "system"
    USER = "user"
    ASSISTANT = "assistant"


@dataclass(frozen=True)
class Message:
    role: MessageRole
    content: str


@dataclass(frozen=True)
class LLMRequest:
    """Immutable request to an LLM provider."""

    model: str
    messages: Sequence[dict[str, str] | Message]
    temperature: float | None = None
    max_tokens: int | None = None
    system_prompt: str | None = None


@dataclass(frozen=True)
class LLMResponse:
    """Immutable response from an LLM provider."""

    content: str
    model: str
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int
    cost_usd: float


class BudgetExceededError(Exception):
    """Raised when a per-project cost cap is exceeded."""

    def __init__(self, spent: float, cap: float) -> None:
        self.spent = spent
        self.cap = cap
        super().__init__(f"budget exceeded: spent ${spent:.4f} of ${cap:.4f} cap")


@runtime_checkable
class BaseLLMProvider(Protocol):
    """Interface all LLM providers must satisfy."""

    async def complete(self, request: LLMRequest) -> LLMResponse: ...
```

```python
# tests/unit/llm/__init__.py
```

- [ ] **Step 5: Run test to verify it passes**

Run: `uv run pytest tests/unit/llm/test_protocol.py -v`
Expected: All 5 tests PASS

- [ ] **Step 6: Run linters**

Run: `uv run ruff check agentlabx/llm/ tests/unit/llm/ && uv run mypy agentlabx/llm/ tests/unit/llm/`
Expected: No errors

- [ ] **Step 7: Commit**

```bash
git add agentlabx/llm/__init__.py agentlabx/llm/protocol.py tests/unit/llm/__init__.py tests/unit/llm/test_protocol.py pyproject.toml
git commit -m "feat(llm): add LLM protocol — LLMRequest, LLMResponse, BaseLLMProvider"
```

---

## Task 2: Mock LLM Server — test-only OpenAI-compatible HTTP service

**Files:**
- Create: `tests/mock_llm_server.py`
- Modify: `tests/conftest.py` (add `mock_llm_server` fixture)

This is a standalone FastAPI app that implements the OpenAI `/v1/chat/completions` endpoint. LiteLLM can talk to it via the `openai/` model prefix pointed at `http://localhost:<port>`. All integration tests route through `LiteLLMProvider` → LiteLLM → HTTP → this server, exercising the real code path.

- [ ] **Step 1: Create the mock server**

```python
# tests/mock_llm_server.py
"""Standalone OpenAI-compatible mock LLM server for integration tests.

Runs as a real HTTP server. LiteLLM connects to it via
  model="openai/<model_name>", api_base="http://localhost:<port>/v1"

Responses are deterministic: the reply content is always a fixed string
(configurable), token counts are based on simple character-length heuristics,
and cost is always 0.
"""
from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field

from fastapi import FastAPI
from pydantic import BaseModel


# --- Request / response shapes matching OpenAI's chat completions API ---


class ChatMessage(BaseModel):  # type: ignore[explicit-any]
    role: str
    content: str


class ChatCompletionRequest(BaseModel):  # type: ignore[explicit-any]
    model: str
    messages: list[ChatMessage]
    temperature: float | None = None
    max_tokens: int | None = None


class UsageInfo(BaseModel):  # type: ignore[explicit-any]
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int


class ChoiceMessage(BaseModel):  # type: ignore[explicit-any]
    role: str
    content: str


class Choice(BaseModel):  # type: ignore[explicit-any]
    index: int
    message: ChoiceMessage
    finish_reason: str


class ChatCompletionResponse(BaseModel):  # type: ignore[explicit-any]
    id: str
    object: str
    created: int
    model: str
    choices: list[Choice]
    usage: UsageInfo


# --- Server state ---


@dataclass
class MockServerState:
    """Mutable state shared across requests. Configure before starting the server."""

    default_content: str = "This is a mock response."
    response_map: dict[str, str] = field(default_factory=dict)
    history: list[ChatCompletionRequest] = field(default_factory=list)
    fail_next_n: int = 0  # return 429 for the next N requests, then succeed


def create_mock_app(state: MockServerState | None = None) -> FastAPI:
    """Create a FastAPI app implementing OpenAI's /v1/chat/completions."""
    app = FastAPI(title="Mock LLM Server")
    server_state = state or MockServerState()
    app.state.mock = server_state

    @app.post("/v1/chat/completions", response_model=ChatCompletionResponse)
    async def chat_completions(
        req: ChatCompletionRequest,
    ) -> ChatCompletionResponse:
        server_state.history.append(req)

        # Simulate transient failures (429 rate-limit) for retry testing
        if server_state.fail_next_n > 0:
            server_state.fail_next_n -= 1
            from fastapi.responses import JSONResponse
            return JSONResponse(  # type: ignore[return-value]
                status_code=429,
                content={"error": {"message": "Rate limit exceeded", "type": "rate_limit"}},
            )

        # Determine response content
        content = server_state.default_content
        for msg in reversed(req.messages):
            if msg.role == "user" and msg.content in server_state.response_map:
                content = server_state.response_map[msg.content]
                break

        # Simple token count heuristic: ~4 chars per token
        prompt_text = " ".join(m.content for m in req.messages)
        prompt_tokens = max(1, len(prompt_text) // 4)
        completion_tokens = max(1, len(content) // 4)

        return ChatCompletionResponse(
            id=f"chatcmpl-mock-{uuid.uuid4().hex[:8]}",
            object="chat.completion",
            created=int(time.time()),
            model=req.model,
            choices=[
                Choice(
                    index=0,
                    message=ChoiceMessage(role="assistant", content=content),
                    finish_reason="stop",
                )
            ],
            usage=UsageInfo(
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
                total_tokens=prompt_tokens + completion_tokens,
            ),
        )

    @app.get("/v1/models")
    async def list_models() -> dict[str, list[dict[str, str]]]:
        return {
            "data": [
                {"id": "mock-model", "object": "model", "owned_by": "mock"},
            ]
        }

    return app
```

- [ ] **Step 2: Add the `mock_llm_server` fixture to conftest.py**

Add the following to `tests/conftest.py`:

```python
import socket
import threading

import uvicorn

from tests.mock_llm_server import MockServerState, create_mock_app


def _find_free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@dataclass
class MockLLMService:
    """Handle returned by the mock_llm_server fixture."""

    base_url: str
    port: int
    state: MockServerState


@pytest.fixture()
def mock_llm_server() -> Iterator[MockLLMService]:
    """Start a real HTTP mock LLM server on a random port for the test."""
    port = _find_free_port()
    state = MockServerState()
    app = create_mock_app(state)

    config = uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning")
    server = uvicorn.Server(config)
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()

    # Wait for server to be ready
    import time
    for _ in range(50):
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=0.1):
                break
        except OSError:
            time.sleep(0.1)

    yield MockLLMService(
        base_url=f"http://127.0.0.1:{port}/v1",
        port=port,
        state=state,
    )

    server.should_exit = True
    thread.join(timeout=5)
```

You will need to add the appropriate imports at the top of `tests/conftest.py`:

```python
from dataclasses import dataclass
import socket
import threading
import time

import uvicorn
```

And add the `MockServerState` and `create_mock_app` imports:

```python
from tests.mock_llm_server import MockServerState, create_mock_app
```

- [ ] **Step 3: Run linters on the mock server**

Run: `uv run ruff check tests/mock_llm_server.py && uv run mypy tests/mock_llm_server.py`
Expected: No errors

- [ ] **Step 4: Commit**

```bash
git add tests/mock_llm_server.py tests/conftest.py
git commit -m "test(llm): add standalone mock LLM server — OpenAI-compatible HTTP service"
```

---

## Task 3: BudgetTracker — per-project cost tracking + cap enforcement

**Files:**
- Create: `agentlabx/llm/budget.py`
- Create: `tests/unit/llm/test_budget.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/llm/test_budget.py
from __future__ import annotations

import asyncio

import pytest

from agentlabx.llm.budget import BudgetTracker
from agentlabx.llm.protocol import BudgetExceededError


def test_initial_spend_is_zero() -> None:
    tracker = BudgetTracker(cap_usd=10.0)
    assert tracker.spent_usd == 0.0
    assert tracker.remaining_usd == 10.0


def test_record_increments_spend() -> None:
    tracker = BudgetTracker(cap_usd=10.0)
    tracker.record(cost_usd=2.5)
    assert tracker.spent_usd == 2.5
    assert tracker.remaining_usd == 7.5


def test_record_multiple_increments() -> None:
    tracker = BudgetTracker(cap_usd=10.0)
    tracker.record(cost_usd=1.0)
    tracker.record(cost_usd=2.0)
    tracker.record(cost_usd=3.0)
    assert tracker.spent_usd == 6.0
    assert tracker.remaining_usd == 4.0


def test_check_raises_when_cap_exceeded() -> None:
    tracker = BudgetTracker(cap_usd=5.0)
    tracker.record(cost_usd=4.0)
    tracker.check()  # should not raise — still under cap
    tracker.record(cost_usd=2.0)  # now at 6.0 > 5.0
    with pytest.raises(BudgetExceededError) as exc_info:
        tracker.check()
    assert exc_info.value.spent == 6.0
    assert exc_info.value.cap == 5.0


def test_check_raises_at_exact_cap() -> None:
    tracker = BudgetTracker(cap_usd=5.0)
    tracker.record(cost_usd=5.0)
    # At exact cap — should NOT raise (only raises when strictly exceeded)
    tracker.check()


def test_no_cap_never_raises() -> None:
    tracker = BudgetTracker(cap_usd=None)
    tracker.record(cost_usd=99999.0)
    tracker.check()  # no cap → never raises
    assert tracker.spent_usd == 99999.0
    assert tracker.remaining_usd is None


def test_zero_cost_record() -> None:
    tracker = BudgetTracker(cap_usd=10.0)
    tracker.record(cost_usd=0.0)
    assert tracker.spent_usd == 0.0


def test_call_count() -> None:
    tracker = BudgetTracker(cap_usd=10.0)
    assert tracker.call_count == 0
    tracker.record(cost_usd=1.0)
    tracker.record(cost_usd=0.0)
    assert tracker.call_count == 2


def test_summary() -> None:
    tracker = BudgetTracker(cap_usd=10.0)
    tracker.record(cost_usd=3.5)
    tracker.record(cost_usd=1.5)
    summary = tracker.summary()
    assert summary["spent_usd"] == 5.0
    assert summary["cap_usd"] == 10.0
    assert summary["remaining_usd"] == 5.0
    assert summary["call_count"] == 2


@pytest.mark.asyncio
async def test_record_async_is_concurrency_safe() -> None:
    """Multiple concurrent record_async calls produce correct totals."""
    tracker = BudgetTracker(cap_usd=None)

    async def record_many(n: int, cost: float) -> None:
        for _ in range(n):
            await tracker.record_async(cost_usd=cost)

    await asyncio.gather(
        record_many(100, 0.01),
        record_many(100, 0.01),
    )
    assert tracker.call_count == 200
    assert abs(tracker.spent_usd - 2.0) < 1e-9


@pytest.mark.asyncio
async def test_check_async_raises_when_exceeded() -> None:
    tracker = BudgetTracker(cap_usd=1.0)
    await tracker.record_async(cost_usd=2.0)
    with pytest.raises(BudgetExceededError):
        await tracker.check_async()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/llm/test_budget.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'agentlabx.llm.budget'`

- [ ] **Step 3: Write minimal implementation**

```python
# agentlabx/llm/budget.py
from __future__ import annotations

import asyncio

from agentlabx.llm.protocol import BudgetExceededError


class BudgetTracker:
    """Per-project LLM cost tracker with optional cap enforcement.

    Thread-safe under asyncio: record() and check() acquire an internal
    lock so concurrent calls cannot interleave spend updates.
    """

    def __init__(self, *, cap_usd: float | None) -> None:
        self._cap_usd = cap_usd
        self._spent_usd: float = 0.0
        self._call_count: int = 0
        self._lock: asyncio.Lock = asyncio.Lock()

    @property
    def spent_usd(self) -> float:
        return self._spent_usd

    @property
    def remaining_usd(self) -> float | None:
        if self._cap_usd is None:
            return None
        return self._cap_usd - self._spent_usd

    @property
    def call_count(self) -> int:
        return self._call_count

    def record(self, *, cost_usd: float) -> None:
        """Record the cost of an LLM call (sync — callers use record_async for lock)."""
        self._spent_usd += cost_usd
        self._call_count += 1

    async def record_async(self, *, cost_usd: float) -> None:
        """Record cost under the internal lock (concurrency-safe)."""
        async with self._lock:
            self._spent_usd += cost_usd
            self._call_count += 1

    def check(self) -> None:
        """Raise BudgetExceededError if spending has strictly exceeded the cap."""
        if self._cap_usd is not None and self._spent_usd > self._cap_usd:
            raise BudgetExceededError(spent=self._spent_usd, cap=self._cap_usd)

    async def check_async(self) -> None:
        """Check budget under the internal lock (concurrency-safe)."""
        async with self._lock:
            self.check()

    def summary(self) -> dict[str, float | int | None]:
        """Return a summary dict suitable for event payloads."""
        return {
            "spent_usd": self._spent_usd,
            "cap_usd": self._cap_usd,
            "remaining_usd": self.remaining_usd,
            "call_count": self._call_count,
        }
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/unit/llm/test_budget.py -v`
Expected: All 11 tests PASS

- [ ] **Step 5: Run linters**

Run: `uv run ruff check agentlabx/llm/budget.py tests/unit/llm/test_budget.py && uv run mypy agentlabx/llm/budget.py tests/unit/llm/test_budget.py`
Expected: No errors

- [ ] **Step 6: Commit**

```bash
git add agentlabx/llm/budget.py tests/unit/llm/test_budget.py
git commit -m "feat(llm): add BudgetTracker — per-project cost tracking + cap enforcement"
```

---

## Task 4: ProviderCatalog — load `providers.yaml`, list models

**Files:**
- Create: `providers.yaml`
- Create: `agentlabx/llm/catalog.py`
- Create: `tests/unit/llm/test_catalog.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/llm/test_catalog.py
from __future__ import annotations

from pathlib import Path

from agentlabx.llm.catalog import ModelEntry, ProviderCatalog, ProviderEntry


def test_load_from_yaml_string() -> None:
    yaml_content = """\
providers:
  - name: provider-a
    display_name: Provider A
    env_var: PROVIDER_A_KEY
    credential_slot: provider-a
    models:
      - id: provider-a/model-1
        display_name: Model 1
      - id: provider-a/model-2
        display_name: Model 2
  - name: provider-b
    display_name: Provider B
    env_var: PROVIDER_B_KEY
    credential_slot: provider-b
    models:
      - id: provider-b/model-1
        display_name: Model 1
"""
    catalog = ProviderCatalog.from_yaml(yaml_content)
    assert len(catalog.providers) == 2
    assert catalog.providers[0].name == "provider-a"
    assert len(catalog.providers[0].models) == 2
    assert catalog.providers[1].name == "provider-b"


def test_list_all_models() -> None:
    yaml_content = """\
providers:
  - name: provider-a
    display_name: Provider A
    env_var: PROVIDER_A_KEY
    credential_slot: provider-a
    models:
      - id: provider-a/model-1
        display_name: Model 1
  - name: provider-b
    display_name: Provider B
    env_var: PROVIDER_B_KEY
    credential_slot: provider-b
    models:
      - id: provider-b/model-1
        display_name: Model 1
"""
    catalog = ProviderCatalog.from_yaml(yaml_content)
    models = catalog.list_models()
    assert len(models) == 2
    ids = [m.id for m in models]
    assert "provider-a/model-1" in ids
    assert "provider-b/model-1" in ids


def test_get_provider_by_name() -> None:
    yaml_content = """\
providers:
  - name: provider-a
    display_name: Provider A
    env_var: PROVIDER_A_KEY
    credential_slot: provider-a
    models:
      - id: provider-a/model-1
        display_name: Model 1
"""
    catalog = ProviderCatalog.from_yaml(yaml_content)
    provider = catalog.get_provider("provider-a")
    assert provider is not None
    assert provider.display_name == "Provider A"


def test_get_provider_missing_returns_none() -> None:
    yaml_content = """\
providers: []
"""
    catalog = ProviderCatalog.from_yaml(yaml_content)
    assert catalog.get_provider("nonexistent") is None


def test_resolve_provider_for_model() -> None:
    yaml_content = """\
providers:
  - name: provider-a
    display_name: Provider A
    env_var: PROVIDER_A_KEY
    credential_slot: provider-a
    models:
      - id: provider-a/model-1
        display_name: Model 1
  - name: provider-b
    display_name: Provider B
    env_var: PROVIDER_B_KEY
    credential_slot: provider-b
    models:
      - id: provider-b/model-1
        display_name: Model 1
"""
    catalog = ProviderCatalog.from_yaml(yaml_content)
    provider = catalog.resolve_provider_for_model("provider-a/model-1")
    assert provider is not None
    assert provider.name == "provider-a"
    provider2 = catalog.resolve_provider_for_model("provider-b/model-1")
    assert provider2 is not None
    assert provider2.name == "provider-b"


def test_resolve_provider_for_unknown_model_returns_none() -> None:
    yaml_content = """\
providers:
  - name: provider-a
    display_name: Provider A
    env_var: PROVIDER_A_KEY
    credential_slot: provider-a
    models:
      - id: provider-a/model-1
        display_name: Model 1
"""
    catalog = ProviderCatalog.from_yaml(yaml_content)
    assert catalog.resolve_provider_for_model("nonexistent-model") is None


def test_load_from_file(tmp_path: Path) -> None:
    yaml_file = tmp_path / "providers.yaml"
    yaml_file.write_text("""\
providers:
  - name: local-provider
    display_name: Local Provider
    env_var: ""
    credential_slot: ""
    models:
      - id: local-provider/model-1
        display_name: Local Model 1
""")
    catalog = ProviderCatalog.from_file(yaml_file)
    assert len(catalog.providers) == 1
    assert catalog.providers[0].name == "local-provider"


def test_provider_entry_fields() -> None:
    entry = ProviderEntry(
        name="test",
        display_name="Test Provider",
        env_var="TEST_API_KEY",
        credential_slot="test",
        models=[ModelEntry(id="test/model-1", display_name="Test Model")],
    )
    assert entry.name == "test"
    assert entry.env_var == "TEST_API_KEY"
    assert entry.credential_slot == "test"


def test_malformed_yaml_missing_providers_key() -> None:
    """YAML with no 'providers' key yields an empty catalog."""
    catalog = ProviderCatalog.from_yaml("something_else: true\n")
    assert len(catalog.providers) == 0


def test_malformed_yaml_missing_model_fields() -> None:
    """Provider entry with missing model fields is skipped gracefully."""
    yaml_content = """\
providers:
  - name: broken
    display_name: Broken Provider
    env_var: X
    credential_slot: x
    models:
      - not_a_valid_model: true
"""
    catalog = ProviderCatalog.from_yaml(yaml_content)
    assert len(catalog.providers) == 1
    # The malformed model entry should be skipped (no 'id' key)
    assert len(catalog.providers[0].models) == 0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/llm/test_catalog.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'agentlabx.llm.catalog'`

- [ ] **Step 3: Add PyYAML dependency**

In `pyproject.toml`, add to `dependencies`:
```
    "pyyaml>=6.0,<7.0",
```

Add to `[project.optional-dependencies] dev`:
```
    "types-PyYAML>=6.0",
```

Run: `uv sync`

- [ ] **Step 4: Write minimal implementation**

```python
# agentlabx/llm/catalog.py
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Self

import yaml


@dataclass(frozen=True)
class ModelEntry:
    """A single model available from a provider."""

    id: str
    display_name: str


@dataclass(frozen=True)
class ProviderEntry:
    """A provider with its models and credential mapping."""

    name: str
    display_name: str
    env_var: str
    credential_slot: str
    models: list[ModelEntry] = field(default_factory=list)


class ProviderCatalog:
    """Loads providers.yaml and provides model/provider lookups."""

    def __init__(self, providers: list[ProviderEntry]) -> None:
        self._providers = providers
        self._model_to_provider: dict[str, ProviderEntry] = {}
        for p in providers:
            for m in p.models:
                self._model_to_provider[m.id] = p

    @property
    def providers(self) -> list[ProviderEntry]:
        return list(self._providers)

    @classmethod
    def from_yaml(cls, content: str) -> Self:
        data: dict[str, list[dict[str, str | list[dict[str, str]]]]] = yaml.safe_load(
            content
        )
        providers: list[ProviderEntry] = []
        for p in data.get("providers", []):
            models_raw = p.get("models", [])
            models: list[ModelEntry] = []
            if isinstance(models_raw, list):
                for m in models_raw:
                    if isinstance(m, dict) and "id" in m and "display_name" in m:
                        models.append(
                            ModelEntry(
                                id=str(m["id"]),
                                display_name=str(m["display_name"]),
                            )
                        )
            providers.append(
                ProviderEntry(
                    name=str(p["name"]),
                    display_name=str(p["display_name"]),
                    env_var=str(p.get("env_var", "")),
                    credential_slot=str(p.get("credential_slot", "")),
                    models=models,
                )
            )
        return cls(providers)

    @classmethod
    def from_file(cls, path: Path) -> Self:
        return cls.from_yaml(path.read_text(encoding="utf-8"))

    def list_models(self) -> list[ModelEntry]:
        """Return all models across all providers."""
        result: list[ModelEntry] = []
        for p in self._providers:
            result.extend(p.models)
        return result

    def get_provider(self, name: str) -> ProviderEntry | None:
        """Look up a provider by name."""
        for p in self._providers:
            if p.name == name:
                return p
        return None

    def resolve_provider_for_model(self, model_id: str) -> ProviderEntry | None:
        """Return the provider that owns this model, or None."""
        return self._model_to_provider.get(model_id)
```

- [ ] **Step 5: Run test to verify it passes**

Run: `uv run pytest tests/unit/llm/test_catalog.py -v`
Expected: All 10 tests PASS

- [ ] **Step 6: Run linters**

Run: `uv run ruff check agentlabx/llm/catalog.py tests/unit/llm/test_catalog.py && uv run mypy agentlabx/llm/catalog.py tests/unit/llm/test_catalog.py`
Expected: No errors

- [ ] **Step 7: Create the `providers.yaml` file**

```yaml
# providers.yaml — AgentLabX provider catalog
# Admin-editable. Defines which LLM providers and models are available.
# LiteLLM model ID format: https://docs.litellm.ai/docs/providers

providers:
  - name: anthropic
    display_name: Anthropic
    env_var: ANTHROPIC_API_KEY
    credential_slot: anthropic
    models:
      - id: claude-opus-4-6
        display_name: Claude Opus 4.6
      - id: claude-sonnet-4-6
        display_name: Claude Sonnet 4.6
      - id: claude-haiku-4-5-20251001
        display_name: Claude Haiku 4.5

  - name: openai
    display_name: OpenAI
    env_var: OPENAI_API_KEY
    credential_slot: openai
    models:
      - id: openai/gpt-4o
        display_name: GPT-4o
      - id: openai/gpt-4o-mini
        display_name: GPT-4o Mini
      - id: openai/o3
        display_name: o3
      - id: openai/o3-mini
        display_name: o3-mini

  - name: gemini
    display_name: Google Gemini
    env_var: GEMINI_API_KEY
    credential_slot: gemini
    models:
      - id: gemini/gemini-3.1-pro-preview
        display_name: Gemini 3.1 Pro Preview
      - id: gemini/gemini-3.1-flash-lite-preview
        display_name: Gemini 3.1 Flash Lite Preview

  - name: azure
    display_name: Azure OpenAI
    env_var: AZURE_API_KEY
    credential_slot: azure
    models:
      - id: azure/gpt-4o
        display_name: Azure GPT-4o

  - name: deepseek
    display_name: DeepSeek
    env_var: DEEPSEEK_API_KEY
    credential_slot: deepseek
    models:
      - id: deepseek/deepseek-chat
        display_name: DeepSeek Chat
      - id: deepseek/deepseek-reasoner
        display_name: DeepSeek Reasoner

  - name: ollama
    display_name: Ollama (Local)
    env_var: ""
    credential_slot: ""
    models:
      - id: ollama/llama3
        display_name: Llama 3 (Ollama)
      - id: ollama/mistral
        display_name: Mistral (Ollama)

  - name: openrouter
    display_name: OpenRouter
    env_var: OPENROUTER_API_KEY
    credential_slot: openrouter
    models:
      - id: openrouter/auto
        display_name: OpenRouter Auto
```

- [ ] **Step 8: Commit**

```bash
git add agentlabx/llm/catalog.py tests/unit/llm/test_catalog.py providers.yaml pyproject.toml
git commit -m "feat(llm): add ProviderCatalog — providers.yaml loading + model/provider lookup"
```

---

## Task 5: KeyResolver — decrypt per-user API key from credential store

**Files:**
- Create: `agentlabx/llm/key_resolver.py`
- Create: `tests/unit/llm/test_key_resolver.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/llm/test_key_resolver.py
from __future__ import annotations

from pathlib import Path

import pytest

from agentlabx.db.schema import Base, UserConfig
from agentlabx.db.session import DatabaseHandle
from agentlabx.llm.catalog import ModelEntry, ProviderCatalog, ProviderEntry
from agentlabx.llm.key_resolver import KeyResolver, NoCredentialError
from agentlabx.security.fernet_store import FernetStore

# Re-use A1 ephemeral_keyring fixture from conftest.py


@pytest.fixture()
async def db(tmp_path: Path) -> DatabaseHandle:
    handle = DatabaseHandle(tmp_path / "test.db")
    await handle.connect()
    async with handle.engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    return handle


@pytest.fixture()
def crypto(ephemeral_keyring: dict[tuple[str, str], str]) -> FernetStore:
    return FernetStore.from_keyring()


@pytest.fixture()
def catalog() -> ProviderCatalog:
    return ProviderCatalog(
        providers=[
            ProviderEntry(
                name="provider-a",
                display_name="Provider A",
                env_var="PROVIDER_A_KEY",
                credential_slot="provider-a",
                models=[ModelEntry(id="provider-a/model-1", display_name="Model 1")],
            ),
            ProviderEntry(
                name="local-provider",
                display_name="Local Provider",
                env_var="",
                credential_slot="",
                models=[ModelEntry(id="local-provider/model-1", display_name="Local Model")],
            ),
        ]
    )


async def _store_credential(
    db: DatabaseHandle, crypto: FernetStore, user_id: str, slot: str, value: str
) -> None:
    ciphertext = crypto.encrypt(value.encode("utf-8"))
    async with db.session() as session:
        session.add(UserConfig(user_id=user_id, slot=f"user:key:{slot}", ciphertext=ciphertext))
        await session.commit()


@pytest.mark.asyncio
async def test_resolve_returns_decrypted_key(
    db: DatabaseHandle, crypto: FernetStore, catalog: ProviderCatalog
) -> None:
    await _store_credential(db, crypto, "user-1", "provider-a", "sk-test-secret")
    resolver = KeyResolver(db=db, crypto=crypto, catalog=catalog)
    key = await resolver.resolve(user_id="user-1", model="provider-a/model-1")
    assert key == "sk-test-secret"


@pytest.mark.asyncio
async def test_resolve_raises_when_no_credential(
    db: DatabaseHandle, crypto: FernetStore, catalog: ProviderCatalog
) -> None:
    resolver = KeyResolver(db=db, crypto=crypto, catalog=catalog)
    with pytest.raises(NoCredentialError, match="provider-a"):
        await resolver.resolve(user_id="user-1", model="provider-a/model-1")


@pytest.mark.asyncio
async def test_resolve_returns_none_for_no_credential_slot(
    db: DatabaseHandle, crypto: FernetStore, catalog: ProviderCatalog
) -> None:
    """Providers with empty credential_slot (e.g. local) need no key."""
    resolver = KeyResolver(db=db, crypto=crypto, catalog=catalog)
    key = await resolver.resolve(user_id="user-1", model="local-provider/model-1")
    assert key is None


@pytest.mark.asyncio
async def test_resolve_isolates_users(
    db: DatabaseHandle, crypto: FernetStore, catalog: ProviderCatalog
) -> None:
    await _store_credential(db, crypto, "user-A", "provider-a", "key-A")
    await _store_credential(db, crypto, "user-B", "provider-a", "key-B")
    resolver = KeyResolver(db=db, crypto=crypto, catalog=catalog)
    assert await resolver.resolve(user_id="user-A", model="provider-a/model-1") == "key-A"
    assert await resolver.resolve(user_id="user-B", model="provider-a/model-1") == "key-B"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/llm/test_key_resolver.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'agentlabx.llm.key_resolver'`

- [ ] **Step 3: Write minimal implementation**

```python
# agentlabx/llm/key_resolver.py
from __future__ import annotations

from sqlalchemy import select

from agentlabx.db.schema import UserConfig
from agentlabx.db.session import DatabaseHandle
from agentlabx.llm.catalog import ProviderCatalog
from agentlabx.security.fernet_store import FernetStore


class NoCredentialError(Exception):
    """Raised when a user has no stored credential for the required provider."""

    def __init__(self, provider_name: str, user_id: str) -> None:
        self.provider_name = provider_name
        self.user_id = user_id
        super().__init__(
            f"no credential stored for provider '{provider_name}' (user {user_id})"
        )


class KeyResolver:
    """Resolves a per-user API key from the encrypted credential store."""

    def __init__(
        self,
        *,
        db: DatabaseHandle,
        crypto: FernetStore,
        catalog: ProviderCatalog,
    ) -> None:
        self._db = db
        self._crypto = crypto
        self._catalog = catalog

    async def resolve(self, *, user_id: str, model: str) -> str | None:
        """Return the decrypted API key for the provider owning `model`.

        Returns None if the provider requires no credential (empty credential_slot).
        Raises NoCredentialError if the provider requires a credential but the user
        has none stored.
        """
        provider = self._catalog.resolve_provider_for_model(model)
        if provider is None:
            # Unknown model — let LiteLLM try with env vars / no key
            return None

        if not provider.credential_slot:
            # Provider needs no key (e.g. local inference server)
            return None

        slot = f"user:key:{provider.credential_slot}"
        async with self._db.session() as session:
            row = (
                await session.execute(
                    select(UserConfig).where(
                        UserConfig.user_id == user_id,
                        UserConfig.slot == slot,
                    )
                )
            ).scalar_one_or_none()

        if row is None:
            raise NoCredentialError(provider_name=provider.name, user_id=user_id)

        return self._crypto.decrypt(row.ciphertext).decode("utf-8")
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/unit/llm/test_key_resolver.py -v`
Expected: All 4 tests PASS

- [ ] **Step 5: Run linters**

Run: `uv run ruff check agentlabx/llm/key_resolver.py tests/unit/llm/test_key_resolver.py && uv run mypy agentlabx/llm/key_resolver.py tests/unit/llm/test_key_resolver.py`
Expected: No errors

- [ ] **Step 6: Commit**

```bash
git add agentlabx/llm/key_resolver.py tests/unit/llm/test_key_resolver.py
git commit -m "feat(llm): add KeyResolver — decrypt per-user API key from credential store"
```

---

## Task 6: TracedLLMProvider — event emission + prompt redaction + budget integration

**Files:**
- Create: `agentlabx/llm/traced_provider.py`
- Create: `tests/unit/llm/test_traced_provider.py`

TracedLLMProvider wraps any `BaseLLMProvider`. Unit tests use a minimal inline stub (defined in the test file) — not a shipped mock class. The stub is a few lines that satisfy the Protocol; this tests the tracing/budget wrapper logic in isolation.

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/llm/test_traced_provider.py
from __future__ import annotations

import pytest

from agentlabx.events.bus import Event, EventBus
from agentlabx.llm.budget import BudgetTracker
from agentlabx.llm.protocol import BudgetExceededError, LLMRequest, LLMResponse, MessageRole
from agentlabx.llm.traced_provider import TracedLLMProvider


# --- Inline test stub (not shipped in production) ---


class _StubProvider:
    """Minimal in-test stub satisfying BaseLLMProvider for TracedLLMProvider tests."""

    def __init__(
        self,
        *,
        content: str = "stub response",
        prompt_tokens: int = 0,
        completion_tokens: int = 0,
    ) -> None:
        self._content = content
        self._prompt_tokens = prompt_tokens
        self._completion_tokens = completion_tokens
        self.call_count: int = 0

    async def complete(self, request: LLMRequest) -> LLMResponse:
        self.call_count += 1
        return LLMResponse(
            content=self._content,
            model=request.model,
            prompt_tokens=self._prompt_tokens,
            completion_tokens=self._completion_tokens,
            total_tokens=self._prompt_tokens + self._completion_tokens,
            cost_usd=0.0,
        )


# --- Helpers ---


async def _collect_events(bus: EventBus, kind: str) -> list[Event]:
    collected: list[Event] = []

    async def handler(event: Event) -> None:
        collected.append(event)

    bus.subscribe(kind, handler)
    return collected


# --- Tests ---


@pytest.mark.asyncio
async def test_traced_emits_llm_called_event() -> None:
    bus = EventBus()
    events = await _collect_events(bus, "llm.called")
    inner = _StubProvider(content="traced response", prompt_tokens=100, completion_tokens=50)
    traced = TracedLLMProvider(inner=inner, bus=bus)
    req = LLMRequest(
        model="test-provider/test-model",
        messages=[{"role": MessageRole.USER, "content": "Hello world"}],
    )
    resp = await traced.complete(req)

    assert resp.content == "traced response"
    assert len(events) == 1
    evt = events[0]
    assert evt.kind == "llm.called"
    assert evt.payload["model"] == "test-provider/test-model"
    assert evt.payload["prompt_tokens"] == 100
    assert evt.payload["completion_tokens"] == 50
    assert evt.payload["total_tokens"] == 150
    assert evt.payload["cost_usd"] == 0.0


@pytest.mark.asyncio
async def test_traced_redacts_prompt_preview() -> None:
    bus = EventBus()
    events = await _collect_events(bus, "llm.called")
    inner = _StubProvider()
    traced = TracedLLMProvider(inner=inner, bus=bus, prompt_preview_length=10)
    long_message = "A" * 100
    req = LLMRequest(
        model="m",
        messages=[{"role": MessageRole.USER, "content": long_message}],
    )
    await traced.complete(req)

    assert len(events) == 1
    preview = events[0].payload["prompt_preview"]
    assert isinstance(preview, str)
    assert len(preview) <= 13  # 10 chars + "..."
    assert preview.endswith("...")


@pytest.mark.asyncio
async def test_traced_short_prompt_not_truncated() -> None:
    bus = EventBus()
    events = await _collect_events(bus, "llm.called")
    inner = _StubProvider()
    traced = TracedLLMProvider(inner=inner, bus=bus, prompt_preview_length=100)
    req = LLMRequest(
        model="m",
        messages=[{"role": MessageRole.USER, "content": "short"}],
    )
    await traced.complete(req)

    assert events[0].payload["prompt_preview"] == "short"


@pytest.mark.asyncio
async def test_traced_with_budget_records_cost() -> None:
    bus = EventBus()
    budget = BudgetTracker(cap_usd=10.0)
    inner = _StubProvider(prompt_tokens=10, completion_tokens=5)
    traced = TracedLLMProvider(inner=inner, bus=bus, budget=budget)
    req = LLMRequest(
        model="m",
        messages=[{"role": MessageRole.USER, "content": "hi"}],
    )
    await traced.complete(req)
    assert budget.call_count == 1


@pytest.mark.asyncio
async def test_traced_with_budget_raises_before_call() -> None:
    bus = EventBus()
    budget = BudgetTracker(cap_usd=1.0)
    budget.record(cost_usd=2.0)  # already over budget
    inner = _StubProvider()
    traced = TracedLLMProvider(inner=inner, bus=bus, budget=budget)
    req = LLMRequest(
        model="m",
        messages=[{"role": MessageRole.USER, "content": "hi"}],
    )
    with pytest.raises(BudgetExceededError):
        await traced.complete(req)
    assert inner.call_count == 0  # inner was never called


@pytest.mark.asyncio
async def test_traced_emits_error_event_on_failure() -> None:
    bus = EventBus()
    events = await _collect_events(bus, "llm.error")

    class _FailingProvider:
        async def complete(self, request: LLMRequest) -> LLMResponse:
            raise RuntimeError("LLM exploded")

    traced = TracedLLMProvider(inner=_FailingProvider(), bus=bus)  # type: ignore[arg-type]
    req = LLMRequest(
        model="m",
        messages=[{"role": MessageRole.USER, "content": "hi"}],
    )
    with pytest.raises(RuntimeError, match="LLM exploded"):
        await traced.complete(req)

    assert len(events) == 1
    assert events[0].payload["error"] == "LLM exploded"
    assert events[0].payload["model"] == "m"


@pytest.mark.asyncio
async def test_traced_passes_through_response_unchanged() -> None:
    bus = EventBus()
    inner = _StubProvider(content="exact content", prompt_tokens=42, completion_tokens=17)
    traced = TracedLLMProvider(inner=inner, bus=bus)
    req = LLMRequest(
        model="test-model",
        messages=[{"role": MessageRole.USER, "content": "hi"}],
    )
    resp = await traced.complete(req)
    assert resp.content == "exact content"
    assert resp.prompt_tokens == 42
    assert resp.completion_tokens == 17
    assert resp.total_tokens == 59
    assert resp.model == "test-model"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/llm/test_traced_provider.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'agentlabx.llm.traced_provider'`

- [ ] **Step 3: Write minimal implementation**

```python
# agentlabx/llm/traced_provider.py
from __future__ import annotations

from agentlabx.events.bus import Event, EventBus
from agentlabx.llm.budget import BudgetTracker
from agentlabx.llm.protocol import BaseLLMProvider, LLMRequest, LLMResponse, MessageRole


class TracedLLMProvider:
    """Wraps any BaseLLMProvider with event emission, prompt redaction, and budget tracking."""

    def __init__(
        self,
        *,
        inner: BaseLLMProvider,
        bus: EventBus,
        budget: BudgetTracker | None = None,
        prompt_preview_length: int = 80,
    ) -> None:
        self._inner = inner
        self._bus = bus
        self._budget = budget
        self._preview_len = prompt_preview_length

    def _extract_prompt_preview(self, request: LLMRequest) -> str:
        """Extract the last user message content, truncated for the event payload."""
        text = ""
        for msg in reversed(request.messages):
            role = msg["role"] if isinstance(msg, dict) else msg.role
            content = msg["content"] if isinstance(msg, dict) else msg.content
            if role == MessageRole.USER:
                text = content
                break

        if len(text) > self._preview_len:
            return text[: self._preview_len] + "..."
        return text

    async def complete(self, request: LLMRequest) -> LLMResponse:
        # Pre-call budget check (concurrency-safe)
        if self._budget is not None:
            await self._budget.check_async()

        try:
            response = await self._inner.complete(request)
        except Exception as exc:
            await self._bus.emit(
                Event(
                    kind="llm.error",
                    payload={
                        "model": request.model,
                        "error": str(exc),
                        "prompt_preview": self._extract_prompt_preview(request),
                    },
                )
            )
            raise

        # Record cost in budget tracker (concurrency-safe)
        if self._budget is not None:
            await self._budget.record_async(cost_usd=response.cost_usd)

        # Emit success event
        await self._bus.emit(
            Event(
                kind="llm.called",
                payload={
                    "model": response.model,
                    "prompt_tokens": response.prompt_tokens,
                    "completion_tokens": response.completion_tokens,
                    "total_tokens": response.total_tokens,
                    "cost_usd": response.cost_usd,
                    "prompt_preview": self._extract_prompt_preview(request),
                },
            )
        )

        return response
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/unit/llm/test_traced_provider.py -v`
Expected: All 7 tests PASS

- [ ] **Step 5: Run linters**

Run: `uv run ruff check agentlabx/llm/traced_provider.py tests/unit/llm/test_traced_provider.py && uv run mypy agentlabx/llm/traced_provider.py tests/unit/llm/test_traced_provider.py`
Expected: No errors

- [ ] **Step 6: Commit**

```bash
git add agentlabx/llm/traced_provider.py tests/unit/llm/test_traced_provider.py
git commit -m "feat(llm): add TracedLLMProvider — event emission + prompt redaction + budget"
```

---

## Task 7: LiteLLMProvider — real LLM calls via LiteLLM + mock server integration tests

**Files:**
- Create: `agentlabx/llm/litellm_provider.py`
- Create: `tests/unit/llm/test_litellm_helpers.py`
- Modify: `pyproject.toml` (add `litellm` dependency + mypy override)
- Create: `tests/integration/test_llm_mock_server.py`

- [ ] **Step 1: Add LiteLLM dependency**

In `pyproject.toml`, add to `dependencies`:
```
    "litellm>=1.60,<2.0",
```

Add a new mypy override block:
```toml
[[tool.mypy.overrides]]
module = ["litellm.*"]
ignore_missing_imports = true
```

Run: `uv sync`

- [ ] **Step 2: Write the LiteLLMProvider implementation**

```python
# agentlabx/llm/litellm_provider.py
from __future__ import annotations

import asyncio
import os
from collections.abc import Iterator
from contextlib import contextmanager

import litellm

from agentlabx.llm.protocol import LLMRequest, LLMResponse

# Lock for providers that require env-var-based key injection.
# LiteLLM's api_key param covers most providers, but some read from
# env vars directly.  The lock serialises env mutations so concurrent
# async calls cannot leak one user's key to another.
_env_lock = asyncio.Lock()


def _build_messages(
    request: LLMRequest,
) -> list[dict[str, str]]:
    """Convert LLMRequest messages to the list-of-dicts format LiteLLM expects."""
    msgs: list[dict[str, str]] = []
    if request.system_prompt is not None:
        msgs.append({"role": "system", "content": request.system_prompt})
    for m in request.messages:
        if isinstance(m, dict):
            msgs.append({"role": m["role"], "content": m["content"]})
        else:
            msgs.append({"role": m.role, "content": m.content})
    return msgs


@contextmanager
def _scoped_env(api_key: str | None, env_var: str | None) -> Iterator[None]:
    """Temporarily set an environment variable for the duration of the call.

    Only used for providers that read keys from env vars rather than the
    api_key parameter.  Callers must hold _env_lock before entering.
    """
    if api_key is None or env_var is None or env_var == "":
        yield
        return

    previous = os.environ.get(env_var)
    os.environ[env_var] = api_key
    try:
        yield
    finally:
        if previous is None:
            os.environ.pop(env_var, None)
        else:
            os.environ[env_var] = previous


class LiteLLMProvider:
    """Routes LLM calls through LiteLLM's acompletion."""

    def __init__(
        self,
        *,
        api_key: str | None = None,
        api_base: str | None = None,
        env_var: str | None = None,
        retry_count: int = 2,
        timeout_seconds: float = 120.0,
    ) -> None:
        self._api_key = api_key
        self._api_base = api_base
        self._env_var = env_var
        self._retry_count = retry_count
        self._timeout = timeout_seconds

    async def complete(self, request: LLMRequest) -> LLMResponse:
        messages = _build_messages(request)

        kwargs: dict[str, str | int | float | list[dict[str, str]] | None] = {
            "model": request.model,
            "messages": messages,  # type: ignore[dict-item]
            "num_retries": self._retry_count,
            "timeout": self._timeout,
        }
        if request.temperature is not None:
            kwargs["temperature"] = request.temperature
        if request.max_tokens is not None:
            kwargs["max_tokens"] = request.max_tokens
        if self._api_key is not None:
            kwargs["api_key"] = self._api_key
        if self._api_base is not None:
            kwargs["api_base"] = self._api_base

        # Primary path: api_key param (concurrency-safe, no env mutation).
        # Fallback path: env-var injection under lock (for providers that
        # ignore the api_key param and read from env vars directly).
        needs_env = self._env_var is not None and self._env_var != ""
        if needs_env:
            async with _env_lock:
                with _scoped_env(self._api_key, self._env_var):
                    response = await litellm.acompletion(**kwargs)  # type: ignore[arg-type]
        else:
            response = await litellm.acompletion(**kwargs)  # type: ignore[arg-type]

        # Extract usage
        usage = response.usage  # type: ignore[union-attr]
        prompt_tokens: int = getattr(usage, "prompt_tokens", 0) or 0
        completion_tokens: int = getattr(usage, "completion_tokens", 0) or 0
        total_tokens: int = getattr(usage, "total_tokens", 0) or 0

        # Extract content
        content: str = response.choices[0].message.content or ""  # type: ignore[union-attr, index]

        # Extract cost via LiteLLM's cost calculation
        cost_usd: float = 0.0
        try:
            cost_usd = float(
                litellm.completion_cost(completion_response=response)  # type: ignore[arg-type]
            )
        except Exception:
            pass  # cost calculation may fail for custom/local models — default to 0

        model_returned: str = getattr(response, "model", request.model) or request.model  # type: ignore[union-attr]

        return LLMResponse(
            content=content,
            model=model_returned,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_tokens=total_tokens,
            cost_usd=cost_usd,
        )
```

- [ ] **Step 2b: Write unit tests for `_scoped_env` and `_build_messages`**

```python
# tests/unit/llm/test_litellm_helpers.py
from __future__ import annotations

import os

from agentlabx.llm.litellm_provider import _build_messages, _scoped_env
from agentlabx.llm.protocol import LLMRequest, Message, MessageRole


def test_scoped_env_sets_and_restores() -> None:
    """_scoped_env restores the previous value after the block."""
    os.environ["TEST_SCOPED_KEY"] = "original"
    with _scoped_env("new-value", "TEST_SCOPED_KEY"):
        assert os.environ["TEST_SCOPED_KEY"] == "new-value"
    assert os.environ["TEST_SCOPED_KEY"] == "original"
    del os.environ["TEST_SCOPED_KEY"]


def test_scoped_env_pops_when_no_previous() -> None:
    """_scoped_env removes the var if it did not exist before."""
    os.environ.pop("TEST_SCOPED_NEW", None)
    with _scoped_env("temp-value", "TEST_SCOPED_NEW"):
        assert os.environ["TEST_SCOPED_NEW"] == "temp-value"
    assert "TEST_SCOPED_NEW" not in os.environ


def test_scoped_env_noop_when_none() -> None:
    """_scoped_env is a no-op when api_key or env_var is None."""
    with _scoped_env(None, "ANY_VAR"):
        pass  # should not raise
    with _scoped_env("key", None):
        pass
    with _scoped_env("key", ""):
        pass


def test_build_messages_with_system_prompt() -> None:
    req = LLMRequest(
        model="m",
        messages=[{"role": MessageRole.USER, "content": "hi"}],
        system_prompt="Be helpful.",
    )
    msgs = _build_messages(req)
    assert msgs[0] == {"role": "system", "content": "Be helpful."}
    assert msgs[1] == {"role": "user", "content": "hi"}


def test_build_messages_with_message_dataclass() -> None:
    req = LLMRequest(
        model="m",
        messages=[Message(role=MessageRole.USER, content="typed msg")],
    )
    msgs = _build_messages(req)
    assert msgs[0] == {"role": "user", "content": "typed msg"}
```

- [ ] **Step 3: Write integration tests against the mock server**

```python
# tests/integration/test_llm_mock_server.py
"""Integration tests: LiteLLMProvider → LiteLLM → HTTP → mock LLM server.

Exercises the full pipeline without any real LLM provider API key.
Uses the mock_llm_server fixture (conftest.py).
"""
from __future__ import annotations

import pytest

from agentlabx.events.bus import Event, EventBus
from agentlabx.llm.budget import BudgetTracker
from agentlabx.llm.litellm_provider import LiteLLMProvider
from agentlabx.llm.protocol import LLMRequest, LLMResponse, MessageRole
from agentlabx.llm.traced_provider import TracedLLMProvider
from tests.conftest import MockLLMService

pytestmark = pytest.mark.integration


@pytest.mark.asyncio
async def test_litellm_provider_against_mock_server(
    mock_llm_server: MockLLMService,
) -> None:
    """LiteLLMProvider calls the mock server and returns a valid LLMResponse."""
    provider = LiteLLMProvider(
        api_key="mock-key",
        api_base=mock_llm_server.base_url,
    )
    req = LLMRequest(
        model="openai/mock-model",
        messages=[{"role": MessageRole.USER, "content": "Hello mock"}],
    )
    resp = await provider.complete(req)

    assert isinstance(resp, LLMResponse)
    assert resp.content == "This is a mock response."
    assert resp.prompt_tokens > 0
    assert resp.completion_tokens > 0
    assert resp.total_tokens == resp.prompt_tokens + resp.completion_tokens


@pytest.mark.asyncio
async def test_mock_server_deterministic(
    mock_llm_server: MockLLMService,
) -> None:
    """Same input → same output across calls."""
    provider = LiteLLMProvider(
        api_key="mock-key",
        api_base=mock_llm_server.base_url,
    )
    req = LLMRequest(
        model="openai/mock-model",
        messages=[{"role": MessageRole.USER, "content": "determinism check"}],
    )
    r1 = await provider.complete(req)
    r2 = await provider.complete(req)

    assert r1.content == r2.content
    assert r1.prompt_tokens == r2.prompt_tokens
    assert r1.completion_tokens == r2.completion_tokens


@pytest.mark.asyncio
async def test_mock_server_custom_response(
    mock_llm_server: MockLLMService,
) -> None:
    """response_map in the mock server produces per-input responses."""
    mock_llm_server.state.response_map["special input"] = "special output"
    provider = LiteLLMProvider(
        api_key="mock-key",
        api_base=mock_llm_server.base_url,
    )
    req = LLMRequest(
        model="openai/mock-model",
        messages=[{"role": MessageRole.USER, "content": "special input"}],
    )
    resp = await provider.complete(req)
    assert resp.content == "special output"


@pytest.mark.asyncio
async def test_traced_provider_with_mock_server(
    mock_llm_server: MockLLMService,
) -> None:
    """Full pipeline: TracedLLMProvider → LiteLLMProvider → mock server → events."""
    bus = EventBus()
    events: list[Event] = []

    async def collect(event: Event) -> None:
        events.append(event)

    bus.subscribe("llm.called", collect)

    inner = LiteLLMProvider(
        api_key="mock-key",
        api_base=mock_llm_server.base_url,
    )
    traced = TracedLLMProvider(inner=inner, bus=bus)
    req = LLMRequest(
        model="openai/mock-model",
        messages=[{"role": MessageRole.USER, "content": "traced mock call"}],
    )
    resp = await traced.complete(req)

    assert resp.content == "This is a mock response."
    assert len(events) == 1
    evt = events[0]
    assert evt.payload["prompt_tokens"] > 0
    assert evt.payload["completion_tokens"] > 0
    assert evt.payload["prompt_preview"] == "traced mock call"


@pytest.mark.asyncio
async def test_mock_server_records_history(
    mock_llm_server: MockLLMService,
) -> None:
    """The mock server records all requests for test assertions."""
    provider = LiteLLMProvider(
        api_key="mock-key",
        api_base=mock_llm_server.base_url,
    )
    req = LLMRequest(
        model="openai/mock-model",
        messages=[{"role": MessageRole.USER, "content": "track this"}],
    )
    await provider.complete(req)
    await provider.complete(req)

    assert len(mock_llm_server.state.history) == 2
    assert mock_llm_server.state.history[0].messages[-1].content == "track this"


@pytest.mark.asyncio
async def test_litellm_retries_on_429(
    mock_llm_server: MockLLMService,
) -> None:
    """LiteLLM retries on 429 and eventually succeeds."""
    mock_llm_server.state.fail_next_n = 1  # fail first request, succeed on retry
    provider = LiteLLMProvider(
        api_key="mock-key",
        api_base=mock_llm_server.base_url,
        retry_count=2,
    )
    req = LLMRequest(
        model="openai/mock-model",
        messages=[{"role": MessageRole.USER, "content": "retry me"}],
    )
    resp = await provider.complete(req)
    assert resp.content == "This is a mock response."


@pytest.mark.asyncio
async def test_litellm_provider_with_system_prompt(
    mock_llm_server: MockLLMService,
) -> None:
    """system_prompt is prepended as a system message in _build_messages."""
    provider = LiteLLMProvider(
        api_key="mock-key",
        api_base=mock_llm_server.base_url,
    )
    req = LLMRequest(
        model="openai/mock-model",
        messages=[{"role": MessageRole.USER, "content": "hello"}],
        system_prompt="You are a test assistant.",
    )
    resp = await provider.complete(req)
    assert isinstance(resp, LLMResponse)
    # Verify the mock server received the system message
    last_req = mock_llm_server.state.history[-1]
    assert last_req.messages[0].role == "system"
    assert last_req.messages[0].content == "You are a test assistant."


@pytest.mark.asyncio
async def test_litellm_provider_with_message_dataclass(
    mock_llm_server: MockLLMService,
) -> None:
    """Message dataclass objects are correctly converted by _build_messages."""
    from agentlabx.llm.protocol import Message

    provider = LiteLLMProvider(
        api_key="mock-key",
        api_base=mock_llm_server.base_url,
    )
    req = LLMRequest(
        model="openai/mock-model",
        messages=[Message(role=MessageRole.USER, content="dataclass msg")],
    )
    resp = await provider.complete(req)
    assert resp.content == "This is a mock response."
    last_req = mock_llm_server.state.history[-1]
    assert last_req.messages[-1].content == "dataclass msg"
```

- [ ] **Step 4: Run the integration tests**

Run: `uv run pytest tests/integration/test_llm_mock_server.py -v`
Expected: All 9 tests PASS

- [ ] **Step 5: Run linters**

Run: `uv run ruff check agentlabx/llm/litellm_provider.py tests/unit/llm/test_litellm_helpers.py tests/integration/test_llm_mock_server.py && uv run mypy agentlabx/llm/litellm_provider.py tests/unit/llm/test_litellm_helpers.py tests/integration/test_llm_mock_server.py`
Expected: No errors

- [ ] **Step 6: Commit**

```bash
git add agentlabx/llm/litellm_provider.py tests/unit/llm/test_litellm_helpers.py tests/integration/test_llm_mock_server.py pyproject.toml
git commit -m "feat(llm): add LiteLLMProvider + mock server integration tests"
```

---

## Task 8: Wire LLM module into FastAPI — `/api/llm/*` router + app factory

> **Note:** No `/api/llm/complete` endpoint — completion is invoked server-side by stages via the Python API, not by the frontend. A REST completion endpoint may be added in a later stage if needed.

**Files:**
- Create: `agentlabx/server/routers/llm.py`
- Modify: `agentlabx/server/app.py` (register LLM router + catalog + inject into request.state)
- Modify: `agentlabx/models/api.py` (add LLM-related response models)
- Modify: `agentlabx/llm/__init__.py` (re-exports)
- Create: `tests/integration/test_llm_router.py`

- [ ] **Step 1: Add LLM response models to `api.py`**

Add the following classes to `agentlabx/models/api.py`:

```python
class ModelResponse(BaseModel):  # type: ignore[explicit-any]
    id: str
    display_name: str
    provider: str


class ProviderResponse(BaseModel):  # type: ignore[explicit-any]
    name: str
    display_name: str
    credential_slot: str
    models: list[ModelResponse]
```

- [ ] **Step 2: Write the failing integration test**

```python
# tests/integration/test_llm_router.py
from __future__ import annotations

from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient

from agentlabx.config.settings import AppSettings
from agentlabx.server.app import create_app


async def _bootstrap_and_login(
    client: AsyncClient,
) -> dict[str, str]:
    """Register admin + login, return cookies dict."""
    await client.post(
        "/api/auth/register",
        json={
            "display_name": "Admin",
            "email": "admin@test.com",
            "passphrase": "testpass123",
        },
    )
    r = await client.post(
        "/api/auth/login",
        json={"email": "admin@test.com", "passphrase": "testpass123"},
    )
    assert r.status_code == 200
    return dict(client.cookies)


@pytest.mark.asyncio
@pytest.mark.integration
async def test_list_providers(
    tmp_workspace: Path,
    ephemeral_keyring: dict[tuple[str, str], str],
) -> None:
    settings = AppSettings(workspace=tmp_workspace)
    app = await create_app(settings)
    try:
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as c:
            await _bootstrap_and_login(c)
            r = await c.get("/api/llm/providers")
            assert r.status_code == 200
            data = r.json()
            assert isinstance(data, list)
            assert len(data) > 0
            first = data[0]
            assert "name" in first
            assert "display_name" in first
            assert "models" in first
    finally:
        await app.state.db.close()


@pytest.mark.asyncio
@pytest.mark.integration
async def test_list_models(
    tmp_workspace: Path,
    ephemeral_keyring: dict[tuple[str, str], str],
) -> None:
    settings = AppSettings(workspace=tmp_workspace)
    app = await create_app(settings)
    try:
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as c:
            await _bootstrap_and_login(c)
            r = await c.get("/api/llm/models")
            assert r.status_code == 200
            data = r.json()
            assert isinstance(data, list)
            assert len(data) > 0
            first = data[0]
            assert "id" in first
            assert "display_name" in first
            assert "provider" in first
    finally:
        await app.state.db.close()


@pytest.mark.asyncio
@pytest.mark.integration
async def test_list_providers_unauthenticated(
    tmp_workspace: Path,
    ephemeral_keyring: dict[tuple[str, str], str],
) -> None:
    settings = AppSettings(workspace=tmp_workspace)
    app = await create_app(settings)
    try:
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as c:
            r = await c.get("/api/llm/providers")
            assert r.status_code == 401
    finally:
        await app.state.db.close()
```

- [ ] **Step 3: Run test to verify it fails**

Run: `uv run pytest tests/integration/test_llm_router.py -v`
Expected: FAIL — 404 (router not registered)

- [ ] **Step 4: Create the LLM router**

```python
# agentlabx/server/routers/llm.py
from __future__ import annotations

from fastapi import APIRouter, Depends, Request

from agentlabx.auth.protocol import Identity
from agentlabx.llm.catalog import ProviderCatalog
from agentlabx.models.api import ModelResponse, ProviderResponse
from agentlabx.server.dependencies import current_identity

router = APIRouter(prefix="/api/llm", tags=["llm"])


@router.get("/providers", response_model=list[ProviderResponse])
async def list_providers(
    request: Request,
    identity: Identity = Depends(current_identity),
) -> list[ProviderResponse]:
    catalog: ProviderCatalog = request.app.state.catalog
    return [
        ProviderResponse(
            name=p.name,
            display_name=p.display_name,
            credential_slot=p.credential_slot,
            models=[
                ModelResponse(id=m.id, display_name=m.display_name, provider=p.name)
                for m in p.models
            ],
        )
        for p in catalog.providers
    ]


@router.get("/models", response_model=list[ModelResponse])
async def list_models(
    request: Request,
    identity: Identity = Depends(current_identity),
) -> list[ModelResponse]:
    catalog: ProviderCatalog = request.app.state.catalog
    result: list[ModelResponse] = []
    for p in catalog.providers:
        for m in p.models:
            result.append(
                ModelResponse(id=m.id, display_name=m.display_name, provider=p.name)
            )
    return result
```

- [ ] **Step 5: Wire into app factory**

In `agentlabx/config/settings.py`, add to `AppSettings`:
```python
    catalog_path: Path | None = None  # None → resolve from package data
```

In `agentlabx/server/app.py`, add imports:
```python
import importlib.resources
import logging

from agentlabx.llm.catalog import ProviderCatalog
from agentlabx.server.routers import llm as llm_router

_log = logging.getLogger(__name__)
```

After the event bus setup and before `app.include_router(health_router.router)`, add:
```python
    # Provider catalog — resolve from settings, fall back to package data
    catalog_path = settings.catalog_path
    if catalog_path is not None and catalog_path.exists():
        catalog = ProviderCatalog.from_file(catalog_path)
    else:
        # Try shipped package data via importlib.resources
        try:
            ref = importlib.resources.files("agentlabx") / ".." / "providers.yaml"
            with importlib.resources.as_file(ref) as p:  # type: ignore[arg-type]
                if p.exists():
                    catalog = ProviderCatalog.from_file(p)
                else:
                    _log.warning("providers.yaml not found — catalog is empty")
                    catalog = ProviderCatalog(providers=[])
        except (FileNotFoundError, TypeError):
            _log.warning("providers.yaml not found — catalog is empty")
            catalog = ProviderCatalog(providers=[])
    app.state.catalog = catalog
```

Add the router registration:
```python
    app.include_router(llm_router.router)
```

- [ ] **Step 6: Update `agentlabx/llm/__init__.py` with re-exports**

```python
# agentlabx/llm/__init__.py
from __future__ import annotations

from agentlabx.llm.budget import BudgetTracker
from agentlabx.llm.catalog import ModelEntry, ProviderCatalog, ProviderEntry
from agentlabx.llm.key_resolver import KeyResolver, NoCredentialError
from agentlabx.llm.litellm_provider import LiteLLMProvider
from agentlabx.llm.protocol import (
    BaseLLMProvider,
    BudgetExceededError,
    LLMRequest,
    LLMResponse,
    Message,
    MessageRole,
)
from agentlabx.llm.traced_provider import TracedLLMProvider

__all__ = [
    "BaseLLMProvider",
    "BudgetExceededError",
    "BudgetTracker",
    "KeyResolver",
    "LLMRequest",
    "LLMResponse",
    "LiteLLMProvider",
    "Message",
    "MessageRole",
    "ModelEntry",
    "NoCredentialError",
    "ProviderCatalog",
    "ProviderEntry",
    "TracedLLMProvider",
]
```

- [ ] **Step 7: Run test to verify it passes**

Run: `uv run pytest tests/integration/test_llm_router.py -v`
Expected: All 3 tests PASS

- [ ] **Step 8: Run linters on all changed files**

Run: `uv run ruff check agentlabx/llm/ agentlabx/server/ agentlabx/models/ tests/integration/test_llm_router.py && uv run mypy agentlabx/llm/ agentlabx/server/ agentlabx/models/ tests/integration/test_llm_router.py`
Expected: No errors

- [ ] **Step 9: Commit**

```bash
git add agentlabx/server/routers/llm.py agentlabx/server/app.py agentlabx/models/api.py agentlabx/llm/__init__.py tests/integration/test_llm_router.py
git commit -m "feat(llm): wire LLM router into FastAPI — /api/llm/providers + /api/llm/models"
```

---

## Task 9: Integration test — real LLM call with event + cost verification

**Files:**
- Create: `tests/integration/test_llm_real_provider.py`

This test verifies the A2 exit criterion: "Real call against ≥1 provider succeeds and emits `LLMCalled` event with token + cost."

- [ ] **Step 1: Write the integration test**

```python
# tests/integration/test_llm_real_provider.py
"""Real-LLM integration test for Stage A2 verification gate.

Requires TEST_LLM_MODEL + a matching provider API key in the environment.
See .env.example for setup instructions. pytest-dotenv auto-loads .env.

Skip with: pytest -m "not real_llm"
Run only: pytest -m real_llm
"""
from __future__ import annotations

import os

import pytest

from agentlabx.events.bus import Event, EventBus
from agentlabx.llm.budget import BudgetTracker
from agentlabx.llm.litellm_provider import LiteLLMProvider
from agentlabx.llm.protocol import BudgetExceededError, LLMRequest, LLMResponse, MessageRole
from agentlabx.llm.traced_provider import TracedLLMProvider

# Read from env — pytest-dotenv loads .env automatically.
_MODEL = os.environ.get("TEST_LLM_MODEL", "")

_skip = pytest.mark.skipif(
    not _MODEL,
    reason="TEST_LLM_MODEL not set — see .env.example",
)

pytestmark = [pytest.mark.real_llm, pytest.mark.integration]


@_skip
@pytest.mark.asyncio
async def test_real_llm_call_succeeds() -> None:
    """A2 verification: real call succeeds and returns valid LLMResponse."""
    provider = LiteLLMProvider()
    req = LLMRequest(
        model=_MODEL,
        messages=[{"role": MessageRole.USER, "content": "Reply with exactly: hello"}],
        max_tokens=50,
        temperature=0.0,
    )
    resp = await provider.complete(req)
    assert isinstance(resp, LLMResponse)
    assert len(resp.content) > 0
    assert resp.prompt_tokens > 0
    assert resp.completion_tokens > 0
    assert resp.total_tokens > 0


@_skip
@pytest.mark.asyncio
async def test_real_llm_emits_event_with_cost() -> None:
    """A2 verification: TracedLLMProvider emits LLMCalled with tokens + cost."""
    bus = EventBus()
    events: list[Event] = []

    async def collect(event: Event) -> None:
        events.append(event)

    bus.subscribe("llm.called", collect)

    inner = LiteLLMProvider()
    traced = TracedLLMProvider(inner=inner, bus=bus)
    req = LLMRequest(
        model=_MODEL,
        messages=[{"role": MessageRole.USER, "content": "Say hi"}],
        max_tokens=20,
        temperature=0.0,
    )
    await traced.complete(req)

    assert len(events) == 1
    evt = events[0]
    assert evt.kind == "llm.called"
    assert evt.payload["prompt_tokens"] > 0
    assert evt.payload["completion_tokens"] > 0
    assert evt.payload["total_tokens"] > 0
    # Cost should be a non-negative number (may be 0 for some providers)
    assert isinstance(evt.payload["cost_usd"], float)
    assert evt.payload["cost_usd"] >= 0.0


@_skip
@pytest.mark.asyncio
async def test_real_llm_budget_cap_halts() -> None:
    """A2 verification: budget cap prevents call when exceeded."""
    bus = EventBus()
    budget = BudgetTracker(cap_usd=0.0001)

    inner = LiteLLMProvider()
    traced = TracedLLMProvider(inner=inner, bus=bus, budget=budget)

    # First call should succeed (budget starts at 0)
    req = LLMRequest(
        model=_MODEL,
        messages=[{"role": MessageRole.USER, "content": "Hi"}],
        max_tokens=5,
        temperature=0.0,
    )
    resp1 = await traced.complete(req)
    assert resp1.content

    # Budget should now be exceeded (cap is $0.0001)
    if budget.spent_usd > 0.0001:
        with pytest.raises(BudgetExceededError):
            await traced.complete(req)
```

> **How it works:** The tester sets `TEST_LLM_MODEL=claude-haiku-4-5-20251001` and `ANTHROPIC_API_KEY=sk-...` in `.env`. LiteLLM reads the provider key from the environment automatically (matching by model prefix). No hardcoded model names — when models change, the tester updates `.env`, not the test code.

- [ ] **Step 2: Add the `real_llm` marker to pytest config**

In `pyproject.toml`, add to `markers`:
```
    "real_llm: marks tests that require a real LLM provider API key",
```

- [ ] **Step 3: Run the test (if an API key is available)**

Run: `uv run pytest tests/integration/test_llm_real_provider.py -v -m real_llm`
Expected: Tests PASS if an API key is set, SKIP otherwise.

- [ ] **Step 4: Run linters**

Run: `uv run ruff check tests/integration/test_llm_real_provider.py && uv run mypy tests/integration/test_llm_real_provider.py`
Expected: No errors

- [ ] **Step 5: Commit**

```bash
git add tests/integration/test_llm_real_provider.py pyproject.toml
git commit -m "test(llm): add real-LLM integration test — A2 verification gate"
```

---

## Task 10: Full suite verification + plugin entry point registration

**Files:**
- Modify: `pyproject.toml` (add `agentlabx.llm_providers` entry point group)

- [ ] **Step 1: Add entry point for LLM provider plugin registration**

In `pyproject.toml`, add the entry points section:

```toml
[project.entry-points."agentlabx.llm_providers"]
litellm = "agentlabx.llm.litellm_provider:LiteLLMProvider"
```

- [ ] **Step 2: Run full test suite (excluding real_llm)**

Run: `uv run pytest tests/ -v -m "not real_llm"`
Expected: All tests PASS (existing A1 tests + new A2 tests)

- [ ] **Step 3: Run full linter suite**

Run: `uv run ruff check agentlabx/ tests/ && uv run mypy agentlabx/ tests/`
Expected: No errors

- [ ] **Step 4: Verify entry points are discoverable**

Run: `uv run python -c "from importlib.metadata import entry_points; eps = entry_points(group='agentlabx.llm_providers'); print([(e.name, e.value) for e in eps])"`
Expected: Output includes `[('litellm', 'agentlabx.llm.litellm_provider:LiteLLMProvider')]`

- [ ] **Step 5: Commit**

```bash
git add pyproject.toml
git commit -m "feat(llm): register LiteLLMProvider as entry point for plugin discovery"
```

- [ ] **Step 6: Run the real-LLM test if key available**

Run: `uv run pytest tests/integration/test_llm_real_provider.py -v -m real_llm`
Expected: PASS (or SKIP if no key)

---

## Verification Summary

After all tasks complete, the following A2 exit criteria are met:

| Criterion | Verified by |
|-----------|-------------|
| Real call against ≥1 provider succeeds + emits `LLMCalled` event with token + cost | Task 9: `test_real_llm_emits_event_with_cost` |
| Budget cap halts execution | Task 3: `test_check_raises_when_cap_exceeded` + Task 9: `test_real_llm_budget_cap_halts` |
| Mock LLM server deterministic; full pipeline exercised | Task 7: `test_mock_server_deterministic` + `test_traced_provider_with_mock_server` |
| Per-user encrypted key wiring | Task 5: `test_resolve_isolates_users` |
| ruff + mypy pass | Task 10: full suite verification |
| FR-3 (key handling via credential store) | Task 5: KeyResolver + Task 8: wiring |
| NFR-8 (cost-awareness) | Task 3: BudgetTracker + Task 6: TracedLLMProvider cost recording |

### Design decisions

**No mock provider in production code.** All mock infrastructure is test-only:
- `tests/mock_llm_server.py` — standalone OpenAI-compatible HTTP server
- `tests/conftest.py` — `mock_llm_server` fixture starts/stops the server per test
- `tests/unit/llm/test_traced_provider.py` — `_StubProvider` inline class (6 lines, test-local)

This ensures every integration test exercises the real code path: `LiteLLMProvider` → LiteLLM → HTTP → server. The mock server simulates a real provider at the network boundary, not at the Python class boundary.
