# Stage A5 — Literature RAG Component Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development` (recommended) or `superpowers:executing-plans` to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship the literature-grounding retrieval surface per SRS §3.3.4 and FR-10 — a self-contained Python module that ingests text into one of three Chroma-backed indices (per-project paper corpus, per-lab reference library, per-project artifact index), retrieves top-k chunks as A4-shaped `ChunkRef`s, and verifies LLM-generated citations against the indexed corpus. Pure module — no stage calls it yet; B1 (literature_review), B6 (interpretation), and B7 (report_writing) are the future consumers. The citation verifier is the load-bearing piece: SRS §1.8 Acceptance 8 demands "zero ungrounded citations" in shipped reports, and the only way to enforce that downstream is to reject ungrounded claims at the framework level here.

**Architecture (one-paragraph mental model).** A `RAGService` is the single public surface. On `ingest(IngestRequest)` it (1) if `request.replace=True` (default) calls `ChromaStore.delete_paper(paper_id)` to clear any prior chunking of the same paper — review I-2 prevents stale spans from co-existing with new ones when chunk-size settings change — (2) splits text via a deterministic chunker, (3) embeds each chunk through the configured `BaseEmbedder` (default `LiteLLMEmbedder`, opt-in `SentenceTransformersEmbedder` via the `rag-local` extra; both implementations return L2-normalized vectors so the cosine-similarity threshold is calibrated consistently across backends), and (4) writes vectors + flat-scalar metadata into a Chroma collection named `<index_type>__<scope_id>`. On `query(text, index_type, scope_id, top_k, filters, query_kind)` it embeds the query, delegates retrieval to an injected `BaseRetriever` (Q-E seam — `ChromaStore` implicitly satisfies it; a future BM25/hybrid backend slots in here without touching ingest), persists a row to `rag_query_log` tagged with `query_kind ∈ {"user","verifier"}` (Q-D fetch-on-demand + review M-4 distinguishes interactive vs. verifier-internal traffic), and returns `list[ChunkRef]` — already A4 contract. Both ingest and query enforce embedder-model match against the collection's recorded model and raise `EmbedderMismatchError` on mismatch (review I-1 — the query-time guard prevents the verifier from accepting/rejecting on garbage cosine scores). `CitationVerifier` is a thin policy on top: given a claim text + `cited_paper_id` + `(index_type, scope_id)`, the strict default requires (a) ≥1 chunk from that `paper_id` to exist in the index AND (b) at least one of that paper's chunks to score above `rag_verifier_threshold` for the claim text; lenient mode skips (b). `CitationVerifier` returns a `VerificationResult` carrying the matching chunks (or the failure reason) so callers can attach grounding spans to the claims they keep. Event emissions and query-log writes are wrapped in `contextlib.suppress(Exception)` so transport-side failures never roll back successful retrieval results (review M-6, matching A3's pattern). **No async Chroma calls** — Chroma's Python client is sync, so the store wraps every call in `anyio.to_thread.run_sync`, keeping the public service API async-consistent with A2/A3.

**Tech stack:** Python 3.12 · `chromadb` (new runtime dep, PersistentClient on `<workspace>/rag/chroma/`) · `sentence-transformers` shipped as an opt-in extra under `agentlabx[rag-local]` (~700 MB with torch — not in the base install) · LiteLLM embeddings via A2 (`litellm.aembedding`, default) · Pydantic v2 frozen models · SQLAlchemy async for the query log · `anyio.to_thread.run_sync` for sync→async wrapping · pytest + pytest-asyncio · ruff (`ANN`, `ANN401`) · mypy `--strict`. **No new REST surface.** One new DB table + migration.

**Verification gate (SRS §4.2 Stage A5):**

1. **Ingest of a real markdown paper text produces queryable chunks** with source attribution metadata (`paper_id`, `source`, `span_start`, `span_end`, `ingested_at`). Chunks survive a Chroma round-trip — flat-scalar metadata only (matches A4's `ChunkRef` I-4 fix).
2. **`query(...)` returns `list[ChunkRef]`** ordered by similarity descending, with `score` populated; `model_validate(model_dump(chunk)) == chunk` for every returned chunk.
3. **Citation verifier accepts a grounded claim** — claim about an indexed paper where ≥1 chunk scores above threshold returns `VerificationResult(grounded=True, matching_chunks=[...])`.
4. **Citation verifier rejects an ungrounded claim** in three distinguishable modes:
   - **Mode A — paper-not-in-index**: `cited_paper_id` absent → `VerificationResult(grounded=False, reason="paper_not_indexed")`.
   - **Mode B — paper-present-but-no-supporting-chunk**: `cited_paper_id` present in index but no chunk scores above threshold → `VerificationResult(grounded=False, reason="no_supporting_chunk")`.
   - **Mode C — caller-supplied chunk ids no longer in index (review BL-2)**: `cited_chunk_ids=[...]` supplied but ≥1 of them is missing from the collection (typically because of between-stage re-ingest) → `VerificationResult(grounded=False, reason="cited_chunks_missing")`. Makes A4 `Finding.cited_chunk_ids` load-bearing rather than advisory.
5. **Per-index isolation enforced.** Ingest paper P into `paper_corpus__projA`; query `paper_corpus__projB`, `reference_library__labX`, and `artifact_index__projA` — all three return empty. Cross-scope or cross-index bleed is a test failure.
6. **Query log persists** — after every `query(...)` call a row appears in `rag_query_log` with `query_id`, request params, returned `chunk_ids`, scores, and `ts`; fetching by `query_id` yields the same chunk set.
7. **Event stream lite** — `rag.ingested` and `rag.queried` events carry `{index, scope_id, query_id, hit_count, top_k}` only (no chunk bodies); `rag.verify.passed` / `rag.verify.failed` carry `{claim_hash, cited_paper_id, reason}`.
8. **mypy `--strict` + ruff `ANN`/`ANN401` clean** on production + test code; no `Any`, no `object`-as-placeholder.

**Non-goals (deferred, do not creep):**

- ❌ **BM25 / hybrid retrieval.** Pure vector retrieval is the A5 gate. Q-E decision: revisit after B1 surfaces concrete retrieval-quality complaints; A5 ships the seam (`BaseRetriever` is single-method, replaceable) without a second implementation.
- ❌ **PDF → text extraction.** arxiv MCP already returns markdown; semantic_scholar surfaces abstract text; filesystem MCP returns raw bytes a caller decodes. A5's ingest API takes pre-extracted strings and treats PDF parsing as the caller's problem.
- ❌ **Stage wiring.** B1/B6/B7 will use `RAGService` later. A5 ships only deterministic in-process tests and a Python API.
- ❌ **Memory MCP server vectorisation.** FR-12's curator-governed shared memory layer is Stage C4. A5's Chroma store is the **literature** layer only — it does not touch `memory_entries`.
- ❌ **Cross-lab RAG synchronisation.** A5 stores per-scope locally. Federation is Layer C.
- ❌ **REST endpoints.** A5 is an internal Python contract surface only — exercised through pytest, not HTTP. The REST wrapper (for the Layer C UI) builds on top of `rag_query_log` once the UI is in scope.
- ❌ **A frontend.** Layer C.
- ❌ **Re-ranking, query rewriting, multi-hop retrieval.** None are mandated by SRS §3.3.4. Add after B1/B6 prove they're needed.
- ❌ **Embedding cache.** Useful, deferable. If determinism + repeatability force the issue during B-stage harnesses, add it then.

---

## SRS amendment (Q-A) — to be applied in Task 10

SRS §3.3.4 currently reads:

> Tech: Chroma (local, embedded) for the vector store; **sentence-transformers (or provider embeddings)**; per-project SQLite for chunk metadata.

This plan flips the default. The amended paragraph (apply verbatim in Task 10):

> Tech: Chroma (local, embedded) for the vector store; **provider embeddings via LiteLLM by default** (any LiteLLM-supported embedding model, user-keyed through A2's `KeyResolver`), with **`sentence-transformers` available as an opt-in via the `agentlabx[rag-local]` install extra** for fully-offline operation (~700 MB with torch — not in the base install); per-project SQLite for chunk metadata and per-query result log (`rag_query_log`).

Rationale: the base install stays light; users who want fully-offline RAG (NFR-7) install the extra and flip a setting. Solo installs running against an Anthropic or OpenAI key already have an embedding provider available through their existing LiteLLM credential — no separate setup. Spec-alignment memory: this divergence has been approved (Q-A) and the SRS is updated as part of A5's shipping deliverable, never silently left to drift.

---

## File structure (locked in before task decomposition)

```
agentlabx/
├── rag/
│   ├── __init__.py             # re-exports: RAGService, BaseRetriever, BaseEmbedder,
│   │                           #            SentenceTransformersEmbedder, LiteLLMEmbedder,
│   │                           #            CitationVerifier, VerificationResult,
│   │                           #            IndexType, IngestRequest, IngestResponse,
│   │                           #            QueryFilters, QueryResult,
│   │                           #            RAGStorageError, EmbedderUnavailableError,
│   │                           #            EmbedderMismatchError, VerificationFailureReason
│   ├── protocol.py             # IndexType Literal, IngestRequest, QueryFilters, VerificationResult,
│   │                           # VerificationFailureReason Literal, exceptions
│   ├── chunker.py              # deterministic section-aware char-window splitter; pure function
│   ├── embedders.py            # BaseEmbedder Protocol + LiteLLMEmbedder (default) +
│   │                           # SentenceTransformersEmbedder (opt-in via rag-local extra,
│   │                           # ImportError surfaces as EmbedderUnavailableError)
│   ├── store.py                # ChromaStore — collection-per-(index_type, scope_id),
│   │                           # deterministic naming, metadata schema enforcement,
│   │                           # sync→async wrap via anyio.to_thread.run_sync
│   ├── query_log.py            # RAGQueryLog — async SQLAlchemy CRUD over rag_query_log table
│   ├── service.py              # RAGService — public async ingest/query API, event emission,
│   │                           # query-log persistence
│   └── verifier.py             # CitationVerifier — two-condition policy (paper-in-index +
│   │                           # supporting-chunk-above-threshold); strict + lenient modes
│
agentlabx/db/
├── schema.py                   # ADD: rag_query_log table (id PK, query_id UUID unique, index_type,
│                               #      scope_id, query_text, embedder_model, top_k, hit_chunk_ids JSON,
│                               #      scores JSON, created_at)
└── migrations.py               # ADD: v7→v8 migration add_rag_query_log. Confirmed by reading
│                               # CURRENT_SCHEMA_VERSION (currently 7) — A3's later patch rounds
│                               # shipped v5→v6 (add_slot_env_overrides) and v6→v7
│                               # (add_last_startup_error). A5 lands v7→v8. Verify at branch creation
│                               # in case an intervening stage bumps further (review IM-1).

agentlabx/config/settings.py    # ADD: rag_storage_dir, rag_embedder, rag_embedder_model,
                                #      rag_default_top_k, rag_chunk_size, rag_chunk_overlap,
                                #      rag_verifier_threshold, rag_verifier_strict

agentlabx/events/types.py       # ADD: rag.ingested, rag.queried, rag.verify.passed, rag.verify.failed

tests/
├── fixtures/rag/
│   ├── arxiv_paper_mae.md      # ~3 KB markdown excerpt — masked autoencoder pretraining intro,
│   │                           # 3 distinct sections with paragraph structure (real arxiv text,
│   │                           # not invented)
│   └── arxiv_paper_seg.md      # ~3 KB markdown excerpt — medical segmentation paper;
│   │                           # used for cross-paper grounding test
├── unit/rag/
│   ├── __init__.py
│   ├── test_chunker.py             # determinism; section-boundary respect; overlap correctness
│   ├── test_embedders_litellm.py   # LiteLLMEmbedder against tests/fakes/openai_mock_server
│   │                               # (existing A2 fake, embeddings endpoint stub)
│   ├── test_embedders_st.py        # SentenceTransformersEmbedder, marked `rag_local`;
│   │                               # skipped if the extra is not installed
│   ├── test_store_isolation.py     # 3 indices × 2 scopes — no cross-contamination
│   ├── test_query_log.py           # rag_query_log CRUD round-trip
│   ├── test_service_ingest.py      # ingest emits event, chunks landed in store, log untouched
│   ├── test_service_query.py       # query returns ChunkRefs in score order; log row written
│   └── test_verifier.py            # accept grounded; reject mode A (no paper); reject mode B
│                                   # (paper present, no scoring chunk); lenient-mode override
└── integration/rag/
    ├── __init__.py
    └── test_e2e_pipeline.py        # ingest both fixtures → cross-paper grounded query →
                                    # verify grounded + ungrounded claim across the two papers;
                                    # full event stream asserted; isolation re-asserted
```

**Determinism note.** The `LiteLLMEmbedder` integration tests run against the existing `tests/fakes/openai_mock_server` (A2 infrastructure) with a deterministic embeddings endpoint that returns vectors derived from the input string hash. This is enough to assert ordering, scoring, and round-tripping without depending on a real provider. The `rag_local` marker exists so a developer with the extra installed can exercise the real ST path locally; CI does not require it.

---

## Cross-cutting prerequisites (do these first; not a numbered task)

- [ ] **Add Chroma to base deps.** `chromadb>=0.5,<1.0` enters `pyproject.toml` `[project.dependencies]`. Chroma's PersistentClient writes to `<workspace>/rag/chroma/` and brings in `onnxruntime` + `tokenizers` indirectly (~150 MB) — light enough for base.
- [ ] **Add `rag-local` optional dependency group.** New `[project.optional-dependencies]` entry:
  ```toml
  rag-local = [
      "sentence-transformers>=3.0,<4.0",
  ]
  ```
  Document in README install notes: "For fully-offline RAG, install `pip install -e .[rag-local]`. This pulls in `torch` (~700 MB CPU) and downloads the embedding model on first use."
- [ ] **Add `rag_local` pytest marker** to `pyproject.toml`:
  ```toml
  "rag_local: marks tests that require the rag-local extra (sentence-transformers)"
  ```
- [ ] **Extend `AppSettings`** in `agentlabx/config/settings.py` (env prefix `AGENTLABX_`):
  - `rag_storage_dir: Path | None = None` — defaults to `workspace / "rag" / "chroma"` via property if unset.
  - `rag_embedder: Literal["litellm", "sentence_transformers"] = "litellm"` (Q-A: default flipped).
  - `rag_embedder_model: str = "text-embedding-3-small"` (LiteLLM default; ST default applies when `rag_embedder == "sentence_transformers"` → `"all-MiniLM-L6-v2"`).
  - `rag_default_top_k: int = 8`.
  - `rag_chunk_size: int = 800` (Q-C: configurable).
  - `rag_chunk_overlap: int = 100` (Q-C: configurable).
  - `rag_verifier_threshold: float = 0.55` (cosine similarity).
  - `rag_verifier_strict: bool = True` (Q-B: strict by default).
- [ ] **Register event types** in `agentlabx/events/types.py`:
  - `rag.ingested` — payload `{index_type, scope_id, paper_id, chunk_count, embedder_model}`
  - `rag.queried` — payload `{index_type, scope_id, query_id, top_k, hit_count, embedder_model, query_kind: "user" | "verifier"}` (review M-4: tag distinguishes stage-initiated queries from verifier-internal queries that fire one per citation; lets log readers and Layer C UI filter the noisy verifier traffic from interactive retrievals)
  - `rag.verify.passed` — payload `{claim_hash, cited_paper_id, index_type, scope_id, matching_chunk_count, best_score}`
  - `rag.verify.failed` — payload `{claim_hash, cited_paper_id, index_type, scope_id, reason}` where `reason ∈ {"paper_not_indexed", "no_supporting_chunk"}`
- [ ] **Scope-id convention.** A5 does not own the lab schema (none exists; SRS §FR-9 says lab deployment is a config switch). Pass `scope_id: str` through opaque to the store. For `reference_library`, solo installs use the constant string `"_solo"`. Wiring to a real `lab_id` is Layer C.
- [ ] **Chunk metadata schema** (Chroma constraint — flat scalars only):
  ```
  paper_id     : str
  source       : Literal["arxiv", "semantic_scholar", "file", "artifact"]
  span_start   : int
  span_end     : int
  ingested_at  : str   # ISO-8601
  title        : str | None
  section      : str | None
  ```
  Matches A4's `ChunkRef` flat-fields decision (I-4 fix).
- [ ] **Collection naming.** Deterministic: `f"{index_type}__{scope_id}"`. Chroma collection names must match `^[A-Za-z0-9_-]{3,63}$` — `scope_id` is validated against this regex at `RAGService` boundary; reject otherwise.
- [ ] **Reuse A2's `KeyResolver` for the LiteLLM embedder.** `litellm.aembedding` uses the same provider key registry as `litellm.acompletion`; A2's resolver covers it as-is.
- [ ] **Confirm next free migration version (review IM-1).** Current `CURRENT_SCHEMA_VERSION = 7` (A3 patches added `v5→v6 add_slot_env_overrides` and `v6→v7 add_last_startup_error` after the original A3 merge). The A5 migration is `v7→v8 add_rag_query_log`. Re-check `agentlabx/db/migrations.py` at branch-creation time in case any A-stage between A3 and A5 bumps further — but the v7→v8 expectation is the right anchor today.
- [ ] Create the feature branch `stageA5-rag-component` from `main` (currently at `d311b03`).

---

## Resolved decisions (carry forward; do not relitigate)

| Tag | Decision | Source |
|-----|----------|--------|
| **Q-A** | Default embedder = LiteLLM (any LiteLLM embedding model, user-keyed via A2's `KeyResolver`). sentence-transformers ships as `agentlabx[rag-local]` optional extra. **SRS §3.3.4 amended** as part of Task 10. | User confirmation 2026-05-16 |
| **Q-B** | Citation verifier is **strict by default** — paper-in-index AND chunk-above-threshold. Lenient mode opt-in via `rag_verifier_strict=False`. | User confirmation 2026-05-16 |
| **Q-C** | Chunk size 800 char / overlap 100 char as configurable defaults. | User confirmation 2026-05-16 |
| **Q-D** | Event payloads are **lite** (counts + ids, no chunk bodies). Full retrieval results persist to `rag_query_log` so callers (and the Layer C UI later) can fetch on demand. | User confirmation 2026-05-16 |
| **Q-E** | Pure vector retrieval only in A5; defer BM25/hybrid until B1 surfaces a concrete need. Ship the seam: `BaseRetriever` Protocol is declared in `protocol.py`, `ChromaStore` implicitly satisfies it, `RAGService` depends on the protocol (not the concrete store) for retrieval — a future BM25/hybrid backend implements `BaseRetriever` only. **Implemented concretely (review I-3), not aspirationally.** | User confirmation 2026-05-16 |
| **I-A** | `index_type` is a `Literal["paper_corpus", "reference_library", "artifact_index"]` matching SRS §3.3.4 three-index design — closed set, no runtime extensibility in A5. | This plan |
| **I-B** | `RAGService` is **single-process, single Chroma `PersistentClient`** for the entire backend; collections separate the indices. Multiple-host Chroma is Layer C. | This plan |
| **I-C** | The `rag_query_log` table is **append-only** in A5 — no soft delete, no retention sweep. A future task can add retention once query volume justifies it. | This plan |
| **I-D** | Embedder model id is **recorded per ingest and per query** in `rag.ingested` / `rag.queried` events and in `rag_query_log.embedder_model`. Mixing embedder models within one collection is rejected at ingest time — the collection records the embedder model in its metadata on first ingest; subsequent ingests with a different model raise `EmbedderMismatchError`. | This plan |
| **I-E** | `CitationVerifier` operates **per (index_type, scope_id) pair** the caller supplies. The verifier never silently fans out across all indices — callers (stages) decide which index a citation is supposed to land in. | This plan |

---

## Task 1 — Cross-cutting wiring (deps, settings, event types, migration scaffold)

**Files:**
- Modify: `pyproject.toml` (deps + optional + marker)
- Modify: `agentlabx/config/settings.py`
- Modify: `agentlabx/events/types.py`
- Create: `agentlabx/rag/__init__.py` (empty re-export placeholder; filled in later tasks)

**Steps:**
- [ ] Add `chromadb>=0.5,<1.0` to `[project.dependencies]`.
- [ ] Add `[project.optional-dependencies].rag-local = ["sentence-transformers>=3.0,<4.0"]`.
- [ ] Add `rag_local` marker to `[tool.pytest.ini_options].markers`.
- [ ] Extend `AppSettings` with the eight RAG fields listed in prerequisites; computed `rag_storage_path` property defaults to `workspace / "rag" / "chroma"` when `rag_storage_dir is None`.
- [ ] Add the four `rag.*` event types with full payload schemas.
- [ ] Run `uv pip install -e .` and `uv run pytest -q tests/unit/config` to confirm settings load cleanly; run `uv run mypy --strict agentlabx` to confirm types pass before any A5 code is written.

**Done when:** `uv run mypy --strict agentlabx` and `uv run ruff check agentlabx` pass; importing `from agentlabx.config import AppSettings; AppSettings()` succeeds with the new defaults; `from agentlabx.events.types import RAG_INGESTED` resolves.

---

## Task 2 — `rag/protocol.py` — public types + exceptions

**Files:**
- Create: `agentlabx/rag/protocol.py`
- Create: `tests/unit/rag/__init__.py`
- Create: `tests/unit/rag/test_protocol.py`

**Steps:**
- [ ] Define the closed `IndexType` literal: `IndexType = Literal["paper_corpus", "reference_library", "artifact_index"]`.
- [ ] Define frozen Pydantic models (mirror A4 style, `ConfigDict(frozen=True, extra="forbid")`):
  - `IngestRequest` — fields: `text: str`, `paper_id: str`, `source: Literal["arxiv", "semantic_scholar", "file", "artifact"]`, `title: str | None = None`, `index_type: IndexType`, `scope_id: str`, `replace: bool = True` (review I-2: when `True`, `RAGService.ingest` calls `ChromaStore.delete_paper(...)` for this `paper_id` before inserting new chunks — guarantees stale spans from a prior chunking config don't co-exist with new ones; set `False` only for incremental append flows where the caller can prove span ids will collide and upsert cleanly). Validator: `scope_id` must match `^[A-Za-z0-9_-]{3,63}$` (Chroma collection-name constraint propagated).
  - `QueryFilters` — fields: `paper_ids: list[str] | None = None`, `source: Literal["arxiv", "semantic_scholar", "file", "artifact"] | None = None`, `min_ingested_at: datetime | None = None`. Translated to Chroma `where` clauses by `ChromaStore.query`.
  - `IngestResponse` — frozen Pydantic model. Fields: `chunk_count: int`, `corpus_id: str`, `replaced: bool` (mirrors `IngestRequest.replace` outcome so callers can detect a no-op replace). **`corpus_id` semantics (review BL-1):** for A5, `corpus_id == request.scope_id` — `scope_id` already disambiguates corpora (per-project paper corpus, per-lab reference library, per-project artifact index), B1's literature-review pass produces one corpus per project, and reusing the existing field avoids a second source of truth. The field is exposed as a typed return value (not just "you knew the scope_id") so [`literature_review.py:44`](agentlabx/stages/contracts/literature_review.py#L44)'s `LiteratureReviewOutput.corpus_id` has a load-bearing supplier — A4's contract is satisfied without B1 having to mint an id itself.
  - `VerificationFailureReason = Literal["paper_not_indexed", "no_supporting_chunk", "cited_chunks_missing"]`.
  - `VerificationResult` — fields: `grounded: bool`, `reason: VerificationFailureReason | None = None`, `matching_chunks: list[ChunkRef] = []`, `best_score: float | None = None`, `claim_hash: str`. `model_validator(mode="after")`: if `grounded` is `True` then `reason is None` and `matching_chunks` is non-empty; if `False` then `reason is not None` and `matching_chunks == []`.
  - **`BaseRetriever` Protocol (review I-3 — Q-E seam)** — runtime-checkable, single method so a future BM25/hybrid backend slots in without touching `RAGService`:
    ```python
    @runtime_checkable
    class BaseRetriever(Protocol):
        async def retrieve(
            self,
            *,
            index_type: IndexType,
            scope_id: str,
            embedder_model: str,
            query_embedding: list[float],
            top_k: int,
            filters: QueryFilters | None,
        ) -> list[ChunkRef]: ...
    ```
    `ChromaStore` implicitly satisfies this (its `query` method matches the signature). `RAGService` depends on `BaseRetriever`, not on `ChromaStore` directly — making the swap point concrete instead of aspirational.
- [ ] Define exceptions:
  - `RAGStorageError(Exception)` — base.
  - `EmbedderUnavailableError(RAGStorageError)` — raised when `rag_embedder="sentence_transformers"` but the extra is not installed.
  - `EmbedderMismatchError(RAGStorageError)` — raised on ingest when the collection's recorded embedder model differs from the configured one (I-D).
  - `ScopeIdValidationError(RAGStorageError)` — raised when `scope_id` fails the regex.
  - `UnknownIndexError(RAGStorageError)` — raised when querying a `(index_type, scope_id)` pair with no collection yet (vs. an empty collection — distinguishable for diagnostics).
- [ ] Unit tests:
  - `model_validate(model_dump(req)) == req` for each model.
  - Scope-id regex acceptance/rejection cases (empty, too short, too long, illegal chars).
  - `VerificationResult` validator: rejects `(grounded=True, matching_chunks=[])`; rejects `(grounded=False, matching_chunks=[chunk])`.

**Done when:** unit tests pass; mypy clean; `rag/__init__.py` re-exports the types.

---

## Task 3 — `rag/chunker.py` — deterministic section-aware splitter

**Files:**
- Create: `agentlabx/rag/chunker.py`
- Create: `tests/unit/rag/test_chunker.py`

**Steps:**
- [ ] Implement a pure function:
  ```python
  def chunk_text(
      text: str,
      *,
      chunk_size: int,
      overlap: int,
  ) -> list[ChunkSpan]: ...
  ```
  where `ChunkSpan` is a frozen Pydantic model carrying `text: str`, `span_start: int`, `span_end: int`, `section: str | None`. **No tokenizer dependency** — character-based windowing.
- [ ] Section detection: detect markdown headings (`^#{1,6}\s+`) and emit `section` = nearest preceding heading text (without the `#`s). Non-markdown text gets `section=None`.
- [ ] Chunking algorithm:
  1. Split into paragraphs on blank lines.
  2. Greedily accumulate paragraphs into chunks until adding the next paragraph would exceed `chunk_size` chars.
  3. If a single paragraph exceeds `chunk_size`, fall back to a sliding char-window with `overlap` (still preserving `span_start`/`span_end` offsets into the original `text`).
  4. Emit chunks with offset-into-original-text spans (so callers can re-fetch the exact range).
  5. Apply overlap by carrying the last `overlap` chars of chunk N into chunk N+1.
- [ ] Determinism: same input + params → bit-identical output. Asserted by hashing the chunk-list JSON in a test.
- [ ] Unit tests:
  - Empty string → empty list.
  - Single paragraph shorter than `chunk_size` → one chunk spanning the full text.
  - Three paragraphs each ~chunk_size/3 → packed into one chunk if they fit, otherwise split.
  - Single mega-paragraph 5× `chunk_size` → ~5 chunks with overlap, spans tile the original.
  - Markdown headings: each chunk's `section` resolves to the nearest preceding heading.
  - Determinism: call twice, assert equal.

**Done when:** unit tests pass; chunker is a pure function with no side effects; mypy clean.

---

## Task 4 — `rag/embedders.py` — pluggable embedders

**Files:**
- Create: `agentlabx/rag/embedders.py`
- Create: `tests/unit/rag/test_embedders_litellm.py`
- Create: `tests/unit/rag/test_embedders_st.py` (marked `rag_local`)

**Steps:**
- [ ] Define the `BaseEmbedder` Protocol (runtime-checkable):
  ```python
  @runtime_checkable
  class BaseEmbedder(Protocol):
      model_id: str         # e.g. "text-embedding-3-small" or "all-MiniLM-L6-v2"
      dim: int | None       # populated after the first successful embed() call;
                            # None before then (review M-3 — avoids requiring a
                            # network probe in __init__)

      async def embed(self, texts: list[str]) -> list[list[float]]: ...
  ```
  **Output vector contract:** all implementations MUST return **L2-normalized** (unit-norm) vectors. Cosine similarity in `ChromaStore` (configured with `hnsw:space=cosine`) is computed against the stored vectors, and the `rag_verifier_threshold=0.55` default is calibrated assuming unit norms. OpenAI and Anthropic embedding APIs already return unit-norm vectors; `sentence-transformers` does NOT by default — implementations must explicitly normalize (review M-2). A unit-tested invariant per implementation: `all(abs(sum(v**2 for v in vec) - 1.0) < 1e-5 for vec in result)`.
- [ ] Implement `LiteLLMEmbedder` (default):
  - Constructor takes `model_id: str`, `key_resolver: KeyResolver` (A2), `identity_id: str | None`, optional `api_base: str | None`.
  - `embed(texts)` calls `litellm.aembedding(model=self.model_id, input=texts, api_key=resolved_key, api_base=self.api_base)` and returns `[item["embedding"] for item in response.data]`. OpenAI/Anthropic embedding APIs return unit-norm vectors already — no extra normalization step. If a future provider returns non-unit vectors, defensively normalize at this boundary (cheap; preserves the M-2 invariant downstream).
  - On first successful call, set `self.dim = len(result[0])` (review M-3: `dim` stays `None` until the API confirms its actual vector size; no construct-time probe).
  - Per-user key isolation works through A2's existing `KeyResolver`.
  - **`identity_id=None` semantics (review M-5).** When `identity_id is None`, A5 is making a system-scope embedding call (verifier-internal queries, post-stage background jobs). `KeyResolver.resolve_for_model(model_id, identity_id=None)` returns: (a) `None` if `model_id` resolves to a local provider in `AppSettings.local_providers` — fine, LiteLLM handles it; (b) an admin-scope key from `admin_configs` (introduced in A3's `SlotResolver`, slot `admin:embedding:{provider}`) when present; (c) raises `NoCredentialError` otherwise. Stages that invoke the verifier always pass `identity_id` of the run owner; only orchestrator-initiated system calls go through the system-scope path. Document in the verifier's docstring that callers without an admin embedding key configured must either use a local LiteLLM provider or pass `identity_id` explicitly.
- [ ] Implement `SentenceTransformersEmbedder` (opt-in):
  - Constructor lazy-imports `sentence_transformers.SentenceTransformer`. `ImportError` → raise `EmbedderUnavailableError("install agentlabx[rag-local] to enable sentence-transformers")`.
  - Loads the model lazily on first `embed()` call.
  - Wraps the sync `.encode(texts, convert_to_numpy=True, normalize_embeddings=True)` in `anyio.to_thread.run_sync` (review M-2: `normalize_embeddings=True` is non-negotiable — without it, the `rag_verifier_threshold=0.55` default is calibrated against the wrong scale and the verifier rejects valid grounded claims at random).
  - `dim` populated from `model.get_sentence_embedding_dimension()` after first load (review M-3 — defer to first `embed()` rather than `__init__` so the model fetch doesn't block construction).
- [ ] Factory: `def build_embedder(settings: AppSettings, key_resolver: KeyResolver, identity_id: str | None) -> BaseEmbedder` selects on `settings.rag_embedder`.
- [ ] Unit tests:
  - `test_embedders_litellm.py`: Stand up the A2 `tests/fakes/openai_mock_server`'s embeddings endpoint. **Fake-embedder contract (review IM-4):** the handler must accept any `model` value the client passes (not hard-coded to one model id) and derive its output vector from the pair `(model, input)` so that **two different model ids over the same input produce different vectors** — this is what makes the query-time embedder-mismatch guard testable end-to-end (Task 9 step 15). The vector is deterministic per `(model, input)` pair and **pre-normalized to unit norm** (per the M-2 invariant). Implementation: `vector = unit_normalize(hash_to_floats(f"{model}:{input}", dim=8))` or equivalent — the exact algorithm doesn't matter, only the contract. `LiteLLMEmbedder` returns a list of equal-length vectors; same `(model, input)` pair → same vector (determinism); same `input` across two model ids → two different vectors; `dim` is `None` before the first call and a positive int after.
  - **L2-norm invariant (review M-2)**: assert `all(abs(sum(v*v for v in vec) - 1.0) < 1e-5 for vec in result)` for both `LiteLLMEmbedder` (against the fake) and `SentenceTransformersEmbedder` (when the extra is installed).
  - `test_embedders_st.py` (marked `rag_local`): real `SentenceTransformersEmbedder` on `all-MiniLM-L6-v2`; same input twice → bit-identical vectors; cosine(self, self) ≈ 1.0 (already L2-normalized, so cosine = dot product); cosine(unrelated, unrelated) < 0.5. Skipped at the marker level if the extra isn't installed.
  - Negative path: `SentenceTransformersEmbedder` constructed without the extra installed → `EmbedderUnavailableError` raised on first call. This can be exercised by monkeypatching `sentence_transformers` to `ImportError`.
  - **`identity_id=None` path (review M-5)**: `LiteLLMEmbedder` with a local-provider `model_id` (e.g., `"ollama/nomic-embed-text"`) and `identity_id=None` succeeds without hitting the credential store; with a remote-provider `model_id` and no admin-scope key configured, raises `NoCredentialError`.

**Done when:** both embedder paths tested; LiteLLM path exercises the full A2 mock-server pipeline (not bypassed by a fake class); the rag-local path is gated by the marker so CI without the extra still passes.

---

## Task 5 — `rag/store.py` — Chroma wrapper with collection-per-(index,scope)

**Files:**
- Create: `agentlabx/rag/store.py`
- Create: `tests/unit/rag/test_store_isolation.py`

**Steps:**
- [ ] `ChromaStore` constructor takes `storage_path: Path` and initialises a single `chromadb.PersistentClient(path=str(storage_path))`. One client per process. `ChromaStore` implicitly satisfies the `BaseRetriever` protocol via its `query` method — `isinstance(store, BaseRetriever)` returns `True` at runtime (review I-3 makes the Q-E seam concrete rather than aspirational).
- [ ] Collection naming: `_collection_name(index_type, scope_id) -> str` returns `f"{index_type}__{scope_id}"`. Validate against Chroma's `^[A-Za-z0-9_-]{3,63}$` regex before passing through.
- [ ] On first ingest into a collection, record the embedder `model_id` and `dim` in the collection's metadata (`{"embedder_model": ..., "embedder_dim": ...}`). On subsequent ingests, verify match and raise `EmbedderMismatchError` otherwise (I-D enforcement).
- [ ] **Query-time embedder-mismatch guard (review I-1).** Every call to `ChromaStore.query` reads the target collection's recorded `embedder_model` *before* running the search and raises `EmbedderMismatchError` if the caller-provided embedder's `model_id` differs. Cosine scores across two different embedding spaces are mathematically meaningless — failing loud at the query boundary prevents the verifier from accepting/rejecting on noise. This is the silent failure mode review I-1 flagged as worse than the ingest case (there is no exception path otherwise). Fail-loud matches A4's pattern.
- [ ] Public methods (all `async`, wrap sync Chroma calls in `anyio.to_thread.run_sync`):
  - `async def add(self, *, index_type: IndexType, scope_id: str, embedder_model: str, chunk_ids: list[str], texts: list[str], embeddings: list[list[float]], metadatas: list[ChunkMetadata]) -> None` — checks ingest-time embedder match.
  - `async def query(self, *, index_type: IndexType, scope_id: str, embedder_model: str, embedding: list[float], top_k: int, filters: QueryFilters | None) -> list[ChunkRef]` — checks **query-time** embedder match before search (review I-1).
  - `async def delete_paper(self, *, index_type: IndexType, scope_id: str, paper_id: str) -> int` — review I-2: deletes every chunk whose metadata `paper_id` matches; returns count deleted; idempotent (returns `0` if paper absent).
  - `async def count_by_paper(self, *, index_type: IndexType, scope_id: str, paper_id: str) -> int`
  - `async def get_chunks_by_ids(self, *, index_type: IndexType, scope_id: str, chunk_ids: list[str]) -> dict[str, ChunkRecord]` — review BL-2: returns a dict keyed by `chunk_id` only for ids actually present in the collection (missing ids absent from the dict, NOT raised — caller compares `set(chunk_ids) - set(returned)` to detect missing). `ChunkRecord` is a frozen Pydantic model carrying `chunk_id`, `paper_id`, `text`, `embedding: list[float]`, and the flat metadata fields. Backed by Chroma's `collection.get(ids=..., include=["embeddings","documents","metadatas"])`.
  - `async def score_chunks(self, *, index_type: IndexType, scope_id: str, chunk_ids: list[str], query_embedding: list[float], embedder_model: str) -> dict[str, float]` — review BL-2: returns `{chunk_id: cosine_score}` computed against the stored embeddings (NOT a fresh retrieval — this is the verifier-supplied-chunks scoring path). Enforces query-time embedder-model match (review I-1). Missing chunk_ids absent from the result; caller already has them flagged from `get_chunks_by_ids`.
  - `async def list_collections(self) -> list[str]` — diagnostic
  - `async def delete_collection(self, *, index_type: IndexType, scope_id: str) -> bool` — review IM-2: drops the entire `<index_type>__<scope_id>` collection from the Chroma client (including its `{embedder_model, embedder_dim}` metadata). Returns `True` if the collection existed and was deleted, `False` if it was already absent. **This is the operator migration path** for `rag_embedder_model` changes — without it, switching the embedder leaves a stranded collection whose recorded model can never be matched by future ingests, and the only fix is to manually nuke `<workspace>/rag/chroma/`. `delete_paper` clears chunks but does not reset the collection's recorded embedder, so it alone is insufficient. Idempotent.
- [ ] `chunk_id` generation: `f"{paper_id}::{span_start}:{span_end}"` — deterministic, dedupable (re-ingesting the same span overwrites the same id rather than producing a duplicate). Chroma's `upsert` semantics make this safe.
- [ ] Map `QueryFilters` to Chroma `where` dicts: `paper_ids` → `{"paper_id": {"$in": ids}}`; `source` → `{"source": source}`; `min_ingested_at` → `{"ingested_at": {"$gte": iso_str}}`. Combine via `$and` when multiple set.
- [ ] Convert Chroma's `query()` response into `ChunkRef`s using A4's contract (`chunk_id`, `paper_id`, `span_start`, `span_end`, `score`). Chroma returns distances; convert distance → cosine similarity score (`score = 1 - distance` for `hnsw:space=cosine`).
- [ ] Configure each collection with `metadata={"hnsw:space": "cosine"}` at creation time for deterministic score interpretation.
- [ ] Unit tests (`test_store_isolation.py`):
  - **Three-index × two-scope matrix**: ingest the same paper text into `paper_corpus__projA`. Query `paper_corpus__projB`, `reference_library__projA`, `reference_library__projB`, `artifact_index__projA`, `artifact_index__projB` — all five return empty. The original `paper_corpus__projA` returns it.
  - **Embedder mismatch on ingest**: ingest into a collection with model `m1`; second ingest with model `m2` raises `EmbedderMismatchError`.
  - **Embedder mismatch on query (review I-1)**: ingest with `m1`; query with `embedder_model="m2"` raises `EmbedderMismatchError` **before** any cosine-similarity computation runs.
  - **`delete_paper` round-trip (review I-2)**: ingest paper P into a fresh collection (N chunks); `delete_paper(P)` returns N; `count_by_paper(P) == 0`; second `delete_paper(P)` returns 0 (idempotent).
  - **Filter precision**: ingest two papers; query with `paper_ids=[p1]` returns only p1 chunks.
  - **Upsert idempotency**: ingest the same chunk twice; collection size grows by 1, not 2.
  - **Replace semantics (review I-2)**: ingest paper P with chunk_size=800; re-ingest the same P with chunk_size=400 and `replace=True` → only the 400-byte chunks remain (`count_by_paper(P)` reflects new chunking, not new+old).
  - **Scope-id regex enforcement**: store rejects scope_ids violating the regex with `ScopeIdValidationError`.
  - **`delete_collection` migration path (review IM-2)**: ingest paper P with embedder `m1`; `delete_collection(...)` returns `True`; re-ingest the same P with embedder `m2` succeeds (no `EmbedderMismatchError`) because the collection's recorded model is gone with the collection. Second `delete_collection(...)` returns `False` (idempotent).
  - **`get_chunks_by_ids` + `score_chunks` round-trip (review BL-2)**: ingest paper P (N chunks); `get_chunks_by_ids(chunk_ids=[<N existing>, "missing_id"])` returns a dict of size N (missing id absent, not raised); `score_chunks(chunk_ids=[c1, c2], query_embedding=embed(c1.text))` returns scores with `result[c1] > result[c2]`.

**Done when:** isolation test green; all queries through `ChromaStore` are async; mypy clean.

---

## Task 6 — `rag_query_log` table + migration + `RAGQueryLog` async accessor

**Files:**
- Modify: `agentlabx/db/schema.py`
- Modify: `agentlabx/db/migrations.py`
- Create: `agentlabx/rag/query_log.py`
- Create: `tests/unit/rag/test_query_log.py`

**Steps:**
- [ ] **Confirm schema version is v7 (review IM-1).** Read the current `MIGRATIONS` list; expected current max is `7` (after A3's `v5→v6 add_slot_env_overrides` and `v6→v7 add_last_startup_error` patch rounds). Implement `add_rag_query_log` as `v7→v8`. If `CURRENT_SCHEMA_VERSION` is something other than `7` at branch time, an intervening stage bumped — adjust to `current_max → current_max + 1` and update this task's literal numbers.
- [ ] Schema (`schema.py`):
  ```python
  class RAGQueryLog(Base):
      __tablename__ = "rag_query_log"
      id: Mapped[int] = mapped_column(primary_key=True)
      query_id: Mapped[str] = mapped_column(String(36), unique=True, index=True)
      index_type: Mapped[str] = mapped_column(String(32))
      scope_id: Mapped[str] = mapped_column(String(64))
      query_text: Mapped[str] = mapped_column(Text)
      embedder_model: Mapped[str] = mapped_column(String(128))
      top_k: Mapped[int] = mapped_column()
      filters_json: Mapped[str] = mapped_column(Text)         # JSON-encoded QueryFilters (review IM-3)
      verifier_threshold: Mapped[float | None] = mapped_column(nullable=True)  # review IM-3
      hit_chunk_ids: Mapped[str] = mapped_column(Text)  # JSON-encoded list[str]
      scores: Mapped[str] = mapped_column(Text)         # JSON-encoded list[float]
      identity_id: Mapped[str | None] = mapped_column(String(36), index=True, nullable=True)
      query_kind: Mapped[str] = mapped_column(String(16), index=True)  # "user" | "verifier"
      created_at: Mapped[datetime] = mapped_column(default=lambda: datetime.now(timezone.utc))
  ```
  **Replay-state columns (review IM-3).** `filters_json` stores the `QueryFilters` payload as JSON (`null` when no filter supplied) so C2's `agentlabx reproduce` CLI can replay the exact retrieval call. `verifier_threshold` carries the `rag_verifier_threshold` that was in effect for a verifier-kind row (`NULL` for `query_kind="user"`) so the *accept/reject decision*, not just the retrieval, is reproducible — required by SRS Acceptance 3 ("numerical results within tolerance" includes verifier verdicts). Index on `query_kind` is composite-friendly with `(index_type, scope_id)` so the Layer C UI can cheaply list "interactive retrievals only" without scanning verifier rows (review M-4).
- [ ] Migration `add_rag_query_log`: `CREATE TABLE rag_query_log (...)` + indexes on `query_id` (UNIQUE) and `(index_type, scope_id)` for replay queries.
- [ ] `RAGQueryLog` accessor (`query_log.py`):
  - `async def record(*, query_id, index_type, scope_id, query_text, embedder_model, top_k, filters: QueryFilters | None, verifier_threshold: float | None, hit_chunk_ids, scores, identity_id, query_kind: Literal["user","verifier"]) -> None` (review IM-3)
  - `async def fetch(query_id) -> QueryLogEntry | None` (frozen Pydantic, carrying `query_kind`, `filters`, `verifier_threshold`) — Q-D "fetch on demand" path
  - `async def list_recent(*, limit: int = 50, index_type: IndexType | None = None, scope_id: str | None = None, query_kind: Literal["user","verifier"] | None = None) -> list[QueryLogEntry]` (for future UI listing; `query_kind=None` returns both)
- [ ] Unit tests: round-trip `record(...)` → `fetch(query_id)` → exact equality including `filters` and `verifier_threshold` (review IM-3 — proves C2's reproduce CLI has enough state to replay both retrieval *and* verifier decision); `list_recent` filters by `index_type` + `scope_id` + `query_kind`; non-existent `query_id` returns `None`; JSON columns survive non-trivial chunk_id strings; a `query_kind="user"` row has `verifier_threshold IS NULL`; a `query_kind="verifier"` row has a populated threshold.

**Done when:** migration runs forward cleanly on a fresh DB and on an existing v5 DB; round-trip tests pass; mypy clean.

---

## Task 7 — `rag/service.py` — public `RAGService` API

**Files:**
- Create: `agentlabx/rag/service.py`
- Create: `tests/unit/rag/test_service_ingest.py`
- Create: `tests/unit/rag/test_service_query.py`

**Steps:**
- [ ] `RAGService` constructor: `(store: ChromaStore, retriever: BaseRetriever, embedder: BaseEmbedder, query_log: RAGQueryLog, chunker_config: ChunkerConfig, event_bus: EventBus)`. All deps injected — no global state. The `retriever` parameter is the I-3 seam (Q-E): in A5 the caller passes the same `ChromaStore` instance for both `store` and `retriever` (the store satisfies `BaseRetriever`); a future BM25/hybrid backend implements `BaseRetriever` only and is injected here without changes to ingest paths. `store` is kept as a separate dep because ingest, `delete_paper`, and `count_by_paper` are mutating/structural operations not part of `BaseRetriever`.
- [ ] `async def ingest(self, request: IngestRequest, *, identity_id: str | None = None) -> IngestResponse`:
  1. If `request.replace`, call `replaced_count = await store.delete_paper(index_type=request.index_type, scope_id=request.scope_id, paper_id=request.paper_id)` first (review I-2: prevents stale chunks from a prior chunking config co-existing with new ones; idempotent when the paper is not yet indexed). `replaced = replaced_count > 0`.
  2. Call `chunk_text(request.text, chunk_size=..., overlap=...)` → list of `ChunkSpan`.
  3. Build chunk ids via `_chunk_id(paper_id, span_start, span_end)`.
  4. Call `embedder.embed([span.text for span in spans])` → list of vectors.
  5. Build `ChunkMetadata` per chunk: `paper_id`, `source`, `span_start`, `span_end`, `ingested_at=now()`, `title=request.title`, `section=span.section`.
  6. Call `store.add(embedder_model=embedder.model_id, ...)` once.
  7. Emit `rag.ingested` event with `{index_type, scope_id, paper_id, chunk_count, embedder_model, replaced: bool}` — wrap in `contextlib.suppress(Exception)` so an event-bus failure does not roll back a successful ingest (review M-6).
  8. Return `IngestResponse(chunk_count=len(spans), corpus_id=request.scope_id, replaced=replaced)` (review BL-1: typed return is what `LiteratureReviewOutput.corpus_id` consumes — B1 wires `output.corpus_id = response.corpus_id` without minting any id itself).
- [ ] `async def query(self, *, text: str, index_type: IndexType, scope_id: str, top_k: int | None = None, filters: QueryFilters | None = None, verifier_threshold: float | None = None, identity_id: str | None = None, query_kind: Literal["user","verifier"] = "user") -> QueryResult`:
  - `QueryResult` is a frozen Pydantic model: `query_id: str`, `chunks: list[ChunkRef]`, `embedder_model: str`.
  - Steps:
    1. Resolve `top_k or settings.rag_default_top_k`.
    2. `embedder.embed([text])` → one vector.
    3. `retriever.retrieve(...)` (the injected `BaseRetriever`, satisfied by `ChromaStore`) → `list[ChunkRef]`. Pass `embedder_model=self.embedder.model_id` so the retriever can enforce the query-time mismatch guard (review I-1).
    4. Generate `query_id = str(uuid.uuid4())`.
    5. Persist via `query_log.record(..., filters=filters, verifier_threshold=verifier_threshold, query_kind=query_kind)` — review IM-3: `filters_json` stores the QueryFilters payload for replay, `verifier_threshold` stores the threshold in effect for verifier-kind queries (NULL otherwise). Wrap in `contextlib.suppress(Exception)` so a DB write failure doesn't lose the live result the caller already has (review M-6).
    6. Emit `rag.queried` event with `{index_type, scope_id, query_id, top_k, hit_count, embedder_model, query_kind}` — **no chunk bodies** — wrap in `contextlib.suppress(Exception)` (review M-6).
    7. Return `QueryResult(query_id=..., chunks=..., embedder_model=...)`.
- [ ] `async def fetch_query_result(self, query_id: str) -> QueryLogEntry | None` — thin pass-through to `query_log.fetch`. The Q-D path.
- [ ] Unit tests (`test_service_ingest.py`):
  - Mock embedder + mock store + mock event bus; assert correct args flow through; returned `IngestResponse.chunk_count` matches; `IngestResponse.corpus_id == request.scope_id` (review BL-1); event payload light.
  - Empty text → `IngestResponse(chunk_count=0, corpus_id=scope_id, replaced=False)`; event still emitted with `chunk_count=0` (no special-case).
  - **Replace path (review I-2)**: with `replace=True` and a previously-ingested `paper_id`, `store.delete_paper` is called before `store.add` and `IngestResponse.replaced == True`; with `replace=False`, only `store.add` runs and `replaced == False`; with `replace=True` against an unseen `paper_id`, `delete_paper` is called and returns 0 → `replaced == False`.
  - **Best-effort emit on ingest (review M-6)**: event bus raises → `ingest(...)` still returns a valid `IngestResponse`; store has the new chunks.
- [ ] Unit tests (`test_service_query.py`):
  - Mocked retriever returns 3 chunks; service returns 3 `ChunkRef`s in order; `query_id` generated; query log row written; event emitted.
  - Embedder model recorded in both event and query log.
  - `fetch_query_result(query_id)` returns the record after `query()`; before `query()` it returns `None`.
  - **Default `query_kind="user"` (review M-4)**: a direct `query(...)` call without specifying `query_kind` records and emits with `query_kind="user"`.
  - **Best-effort log write (review M-6)**: query_log.record raises → `query(...)` still returns the result; subsequent `fetch_query_result(query_id)` returns `None` (the log write was lost, but the caller has the result in hand).
  - **Best-effort event emit (review M-6)**: event bus raises → `query(...)` still returns the result and the log row is still written.
  - **BaseRetriever injection (review I-3)**: pass a fake `BaseRetriever` (not a `ChromaStore`) — `query(...)` works the same. Confirms the protocol is the load-bearing seam, not the concrete store.

**Done when:** ingest + query + fetch-result paths pass unit tests with mocks; events captured lite; mypy clean.

---

## Task 8 — `rag/verifier.py` — `CitationVerifier` two-condition policy

**Files:**
- Create: `agentlabx/rag/verifier.py`
- Create: `tests/unit/rag/test_verifier.py`

**Steps:**
- [ ] `CitationVerifier` constructor: `(rag_service: RAGService, store: ChromaStore, event_bus: EventBus, threshold: float, strict: bool)`. Threshold + strict come from `AppSettings`.
- [ ] `async def verify(self, *, claim_text: str, cited_paper_id: str, index_type: IndexType, scope_id: str, cited_chunk_ids: list[str] | None = None, identity_id: str | None = None) -> VerificationResult`:
  1. Compute `claim_hash = sha256(claim_text.encode()).hexdigest()[:16]` for event payload (no raw claim in events).
  2. **Condition (a) — paper-in-index**: `await store.count_by_paper(index_type, scope_id, paper_id=cited_paper_id)`. If `0`, return `VerificationResult(grounded=False, reason="paper_not_indexed", claim_hash=claim_hash)` and emit `rag.verify.failed` (best-effort, review M-6).
  3. **Condition (b) — supporting chunk** (only checked when `strict=True`). **Two sub-modes depending on `cited_chunk_ids` (review BL-2 — makes `Finding.cited_chunk_ids` from A4 `_shared.py` load-bearing):**
     - **(b.i) — caller supplied `cited_chunk_ids`** (the B7 path: re-verifying B6's already-grounded findings against the live index). Look up each id via `await store.get_chunks_by_ids(index_type, scope_id, chunk_ids=cited_chunk_ids)` (new method, see Task 5 below). If any id is missing from the index (re-ingest between B6 and B7 invalidated it, or the id was fabricated), return `VerificationResult(grounded=False, reason="cited_chunks_missing", claim_hash=claim_hash)`; emit `rag.verify.failed`. Then score each resolved chunk's text against `claim_text` (embed claim once, cosine against each chunk's stored vector — `ChromaStore.score_chunks(chunk_ids, query_embedding)` helper). If no resolved chunk scores at or above `self.threshold`, return `VerificationResult(grounded=False, reason="no_supporting_chunk", claim_hash=claim_hash)`. Otherwise: return `grounded=True` with the resolved chunks as `matching_chunks`. **This sub-mode does not re-query the collection** — it verifies the exact chunks the upstream stage claimed it grounded against, making verifier verdicts immune to between-stage re-ingest drift.
     - **(b.ii) — caller did not supply `cited_chunk_ids`** (the B1 / first-pass path): call `RAGService.query(text=claim_text, index_type, scope_id, top_k=settings.rag_default_top_k, filters=QueryFilters(paper_ids=[cited_paper_id]), verifier_threshold=self.threshold, identity_id=identity_id, query_kind="verifier")` — note **`query_kind="verifier"`** (review M-4) so the resulting log/event rows are distinguishable from interactive retrievals, and **`verifier_threshold=self.threshold`** (review IM-3) so the accept/reject decision is reproducible from the persisted log row alone. Filter results to chunks with `score >= self.threshold`. If empty: return `VerificationResult(grounded=False, reason="no_supporting_chunk", claim_hash=claim_hash)`; emit `rag.verify.failed` (best-effort).
  4. Otherwise: return `VerificationResult(grounded=True, matching_chunks=[...], best_score=..., claim_hash=claim_hash)`; emit `rag.verify.passed` (best-effort, wrapped in `contextlib.suppress(Exception)` — review M-6: an event-bus failure must never roll back a successful verification result the caller has already received).
- [ ] Lenient mode (`strict=False`): skip condition (b); paper-in-index is sufficient. Useful for early B-stage prototyping; SRS-aligned default stays strict.
- [ ] Unit tests:
  - **Grounded**: ingest paper text into a paper_corpus; verify a claim whose key phrase appears in the text; assert `grounded=True`, ≥1 matching chunk, `best_score >= threshold`, `rag.verify.passed` emitted.
  - **Mode A reject** (paper-not-indexed): verify a claim citing `paper_id="nonexistent"`; assert `reason="paper_not_indexed"`, `matching_chunks=[]`, `rag.verify.failed` emitted with that reason.
  - **Mode B reject** (paper present, no scoring chunk): ingest paper P; verify a claim whose semantic content has nothing to do with P (e.g., P is about MAE pretraining; claim is about quantum chromodynamics); assert `reason="no_supporting_chunk"`. **Reliability note:** if the LiteLLM fake's hash-derived embedder produces incidental cosine matches, raise the test threshold (or assert against a separately-injectable embedder fixture that returns orthogonal vectors for clearly unrelated inputs) — the goal is to exercise the *code path*, not measure embedding quality.
  - **Lenient bypass**: same setup as Mode B reject, but verifier constructed with `strict=False` → returns `grounded=True` (paper-in-index suffices).
  - **No raw claim leakage**: assert event payload has `claim_hash` but no field carrying the verbatim claim text.
  - **`query_kind="verifier"` tagging (review M-4)**: after a `verify(...)` call that triggers a Condition (b) query, fetch the corresponding `rag_query_log` row and assert `query_kind == "verifier"` and the matching `rag.queried` event emitted by `RAGService.query` carries `query_kind == "verifier"`. A separate `RAGService.query(...)` call (without going through the verifier) records `query_kind == "user"`.
  - **Best-effort emit (review M-6)**: inject an event bus that raises on emit; assert that `verify(...)` still returns the correct `VerificationResult` (no exception propagates) and the log row is still written.
  - **Caller-supplied `cited_chunk_ids` happy path (review BL-2)**: ingest paper P (chunks `c1, c2, c3`); call `verify(claim_text=<text supported by c2>, cited_paper_id=P, cited_chunk_ids=["c2"])` → `grounded=True`, `matching_chunks` contains exactly `c2`. Verify that **`RAGService.query` was NOT invoked** (verifier scored against the stored embedding directly via `store.score_chunks`, no new `rag_query_log` row appeared).
  - **`cited_chunks_missing` rejection (review BL-2)**: ingest paper P; call `verify(..., cited_chunk_ids=["nonexistent_chunk_id"])` → `VerificationResult(grounded=False, reason="cited_chunks_missing")`. Distinguishes from `no_supporting_chunk` — different code path, different event payload.
  - **Re-ingest invalidates BL-2 chunks**: ingest paper P (chunks `c1..c3`); record one chunk id `c2`; re-ingest P with different `rag_chunk_size` (so spans/ids change); call `verify(..., cited_chunk_ids=["c2"])` → `reason="cited_chunks_missing"` (proves the verifier catches between-stage re-ingest drift, the failure mode `Finding.cited_chunk_ids` was added to prevent).
  - **`cited_chunk_ids=None` falls through to original Mode (b.ii)**: same algorithm as before, exercised by the existing Mode B tests.

**Done when:** all three verifier paths green; lenient override exercised; event redaction confirmed.

---

## Task 9 — Integration test: ingest → query → verify end-to-end

**Files:**
- Create: `tests/fixtures/rag/arxiv_paper_mae.md`
- Create: `tests/fixtures/rag/arxiv_paper_seg.md`
- Create: `tests/integration/rag/__init__.py`
- Create: `tests/integration/rag/test_e2e_pipeline.py`

**Steps:**
- [ ] Source two ~3 KB markdown fixtures from arxiv abstracts/intros (real text, paraphrase-free; cite the originals in a `_source.md` adjacent file). Both have clear sectional structure (Introduction / Method / Results headings) so the chunker exercises section attribution.
- [ ] Test pipeline (one integration test marked `integration`, **not** `real_llm`):
  1. Stand up a tmp_path `AppSettings(workspace=...)`.
  2. Run the rag-log migration on a fresh SQLite.
  3. Construct a deterministic embedder (use the LiteLLM fake-server path, A2 infrastructure) — this keeps the test offline + deterministic.
  4. Construct `ChromaStore` against `tmp_path / "rag" / "chroma"`.
  5. Construct `RAGService` + `CitationVerifier`.
  6. Ingest both fixtures into `paper_corpus__projA`. Assert each returned `IngestResponse.corpus_id == "projA"` and `chunk_count > 0` (review N-3 — one end-to-end check that BL-1 flows through the full pipeline; unit tests already cover the shape in isolation).
  7. Query for a phrase appearing in fixture 1 — assert ≥1 returned chunk belongs to fixture 1's `paper_id`.
  8. Query for a phrase appearing in fixture 2 — assert top result belongs to fixture 2's `paper_id`.
  9. Verify a grounded claim citing fixture 1 — `grounded=True`.
  10. Verify a claim citing a `paper_id` not in the index — `reason="paper_not_indexed"`.
  11. Verify a fixture-2 claim against fixture 1's `paper_id` — `reason="no_supporting_chunk"` (assuming the fake embedder + threshold produce orthogonal-enough scores; if not, dial threshold up in test settings to make the contrast unambiguous).
  12. **Isolation re-assert**: ingest the same fixture 1 into `paper_corpus__projA` and **query** `paper_corpus__projB`, `reference_library__projA`, `artifact_index__projA` — all three empty.
  13. Fetch the latest `query_id` from `RAGService.fetch_query_result(query_id)` — round-trip equals the live result's `chunks`.
  14. Subscribe to the event bus before the run; after the run assert the expected sequence of `rag.ingested` + `rag.queried` (with `query_kind="user"`) + `rag.queried` (with `query_kind="verifier"`, fired only by Mode (b.ii) — caller-supplied `cited_chunk_ids` runs `store.score_chunks` instead and emits no `rag.queried`) + `rag.verify.{passed,failed}` events with **lite payloads only** (no chunk bodies in any event); `rag.verify.failed` payload distinguishes all three reasons: `"paper_not_indexed"`, `"no_supporting_chunk"`, and `"cited_chunks_missing"` (review BL-2).
  15. **Caller-supplied chunk-ids round-trip (review BL-2)**: query the index for chunks belonging to fixture 1 → collect their `chunk_id`s → call `CitationVerifier.verify(..., cited_chunk_ids=[<one_of_them>])` → assert `grounded=True` AND no new `rag_query_log` row was written (`query_kind="verifier"`-tagged) for that verification (proves the BL-2 path bypassed `RAGService.query`).
  16. **Query-time mismatch guard (review I-1)**: after a successful ingest with embedder model `m1`, construct a second `LiteLLMEmbedder` with model `m2` and call `RAGService.query(...)` using a service wired with that second embedder against the same scope_id; expect `EmbedderMismatchError` raised before any retrieval result is computed.

**Done when:** the integration test runs to green offline (fake embedder + fixture text only); the gate items 1–7 from §Verification gate are all exercised in this one test or its unit-test siblings.

---

## Task 10 — SRS amendment (§3.3.4 + §4.2 A5 row reverse-engineering) + README + CLAUDE.md

**Files:**
- Modify: `docs/superpowers/specs/2026-04-15-agentlabx-srs.md`
- Modify: `README.md`
- Modify: `CLAUDE.md`

**Steps:**
- [ ] **SRS §3.3.4** — apply the embedder-default flip verbatim (the "amended paragraph" block in the SRS amendment section above).
- [ ] **SRS §4.2 A5 row** — reverse-engineer to reflect what shipped: the three-index design, default LiteLLM embedder, opt-in ST extra, strict verifier default + threshold setting, `rag_query_log` table for fetch-on-demand, lite event payloads, BM25/hybrid explicitly deferred.
- [ ] **README "What's shipped"** — add an A5 entry mirroring the A4 entry's tone: one paragraph naming the public surface (`RAGService`, `CitationVerifier`), the embedder choice, the optional `rag-local` extra install command, the persistence path. **Plus an operator-facing note for the `admin:embedding:{provider}` slot (review N-1):** verifier-internal queries (and any other system-initiated retrievals where `identity_id=None`) resolve the embedding API key via A3's `SlotResolver` — operators wanting system-scope embedding for remote providers must set the slot through `PUT /api/settings/admin/credentials/admin:embedding:{provider}` (e.g., `admin:embedding:openai`). Solo installs whose `rag_embedder_model` resolves to a local LiteLLM provider (Ollama, vLLM) need no admin slot; the verifier path runs key-free. Document this in the README's "Settings" subsection, not buried in a footnote — operators reading top-down should hit it before they first see `NoCredentialError` from a verifier-internal call.
- [ ] **CLAUDE.md "What's shipped"** — append A5 to the per-stage list.
- [ ] Confirm SRS §1.5 FR-10 still holds verbatim against what shipped (it does — A5 implements it).
- [ ] Confirm SRS §1.8 Acceptance 8 wording still matches (zero-ungrounded-citation report-time enforcement is B7's job, not A5's; A5 ships the verifier B7 will call).

**Done when:** SRS, README, and CLAUDE.md no longer drift from the shipped surface; `grep -n 'sentence-transformers (or provider embeddings)' docs/` returns no hits (the old default phrasing has been replaced).

---

## Task 11 — Final-review polish

**Files:**
- All files written in Tasks 1–10.

**Steps:**
- [ ] Run the full test suite: `uv run pytest -q tests/unit/rag tests/integration/rag` — green.
- [ ] Run `uv run pytest -q -m "not real_llm and not rag_local"` to confirm no flakes outside the marker-gated paths.
- [ ] Run `uv run mypy --strict agentlabx` — zero errors.
- [ ] Run `uv run ruff check agentlabx tests/unit/rag tests/integration/rag` — clean.
- [ ] Run `uv run ruff format --check agentlabx tests/unit/rag tests/integration/rag` — clean.
- [ ] Verify no `# type: ignore[explicit-any]` snuck in beyond the existing A1/A2/A3 patterns (Pydantic BaseModel inheritance is the only allowed site).
- [ ] Grep for `Any`, `object` placeholders, `# noqa` — confirm none added.
- [ ] Walk the `pyproject.toml` entry-point and dep diff one more time; confirm `chromadb` is in base deps and `sentence-transformers` is in `rag-local` only.
- [ ] Confirm the integration test runs offline (no `real_llm` marker, no network).
- [ ] If A5 introduced any `_MISSING` sentinel or similar, verify ordering (lesson from A4).
- [ ] Stage an end-to-end demo: `uv run python -c "..."` snippet ingesting one fixture and verifying one claim, captured in the PR description.

**Done when:** all gates pass; ready for merge review on `stageA5-rag-component`.

---

## Out-of-band risks to surface in the PR description

1. **Chroma version drift.** `chromadb` is in active development; pin to `>=0.5,<1.0` and revisit on next release; the `query()` response shape and `where`-clause syntax have changed between minors historically.
2. **First-time ST model download.** The `rag-local` extra triggers a model fetch from Hugging Face on first use. Test environments using the extra must pre-warm the model or mark tests `rag_local` so they're skipped when unwarmed.
3. **LiteLLM embedding API key resolution.** A2's `KeyResolver` returns `None` for `local_providers`; embedding through Ollama-style local LiteLLM endpoints works without a key but requires the user's LiteLLM provider config to support embeddings (not all local backends do — flag in README).
4. **`rag_query_log` growth.** Append-only by I-C decision. If a Layer B harness runs thousands of queries, the table grows unbounded. Acceptable for A5; revisit with retention policy when query volume justifies.
5. **Scope-id collision risk.** Two projects naming their scope_id with the same string would share a collection. The Layer A6 orchestrator will issue scope_ids derived from `project_id` (UUID-shaped), so collision is structurally impossible in practice — but A5 doesn't enforce that uniqueness; the caller does. Document in the public docstring.
6. **Embedder mismatch on settings change.** If a user changes `rag_embedder_model` after ingesting, **both ingest and query** against any prior collection raise `EmbedderMismatchError` (I-1: query-time guard is the load-bearing one — without it, mismatched-space queries would silently return high-noise scores that the verifier would treat as real). **Migration path (review IM-2):** call `ChromaStore.delete_collection(index_type, scope_id)` to drop the entire collection — *including* its recorded `{embedder_model, embedder_dim}` metadata — then re-ingest with the new embedder. `delete_paper` alone is insufficient because it clears chunks but leaves the collection's embedder fingerprint in place; a subsequent ingest with the new model would still raise `EmbedderMismatchError`. A REST surface around `delete_collection` is Layer C's job; A5 ships the Python API so operators can script it now. The query-time path matters more than the ingest-time one because verification reads only — a no-op against a mismatched collection would otherwise produce false positives.
7. **A4 `Citation.source` ≠ A5 `IngestRequest.source` literal sets (review M-1).** A4's `Citation.source` is `Literal["arxiv","semantic_scholar","other"]` ([`agentlabx/stages/contracts/_shared.py:93`](agentlabx/stages/contracts/_shared.py#L93)); A5's `IngestRequest.source` is `Literal["arxiv","semantic_scholar","file","artifact"]`. The two layers serve different purposes — A4's `Citation` is corpus-level metadata for *paper citations*; A5's `source` is chunk-level provenance for *anything ingested into the index* (papers, raw files, prior stage artifacts). The divergence is intentional: `file` and `artifact` exist because the `artifact_index` ingests non-paper data; `other` exists on the A4 side because some legitimate citations don't fit arxiv/S2 (e.g., a NeurIPS proceedings entry retrieved by browser MCP). **Mapping at the B-stage call site:** `Citation.source == "arxiv" → IngestRequest.source = "arxiv"`; `"semantic_scholar" → "semantic_scholar"`; `"other" → "file"` (since "other" citations land in the corpus as fetched text files). One-line mapping in B1; do not widen A4's `Citation.source` to include `"artifact"` (A4 already shipped; introducing chunk-source vocabulary into the citation contract would conflate corpus identity with index provenance).

---

## Summary of A5's contribution to the platform

A5 adds the **literature grounding** seam: every report B7 ships will be required to pass through `CitationVerifier`, and B1's curated reference list will be the first index ever populated. Layer B stages don't yet exist, but their bedrock — typed I/O contracts (A4) and grounded retrieval (A5) — does. After A5 lands, the framework's "you can't ship a citation you didn't retrieve" guarantee is structurally enforceable, completing the anti-fabrication chain SRS §1.2 names as the prior project's fatal flaw.
