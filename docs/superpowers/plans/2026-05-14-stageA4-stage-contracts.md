# Stage A4 — Stage Contract Framework Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development` (recommended) or `superpowers:executing-plans` to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Lock down the stage contract surface — `Stage` Protocol, **Pydantic v2 input + output contracts for every pipeline stage** (literature_review → peer_review), `ReproducibilityContract`, `BacktrackSignal`, `StageContext`, plugin-discovery for stage implementations, and a `StageIOValidator` that enforces contract conformance + reproducibility-field presence. **No real stage implementations** — only deterministic echo stubs registered through entry points to prove the framework end-to-end. This stage exists to make Layer B drift-free: every B-stage's I/O shape is fixed *before* B-stage code is written.

**Architecture (one-paragraph mental model).** A stage is "a thing that, given a typed input, eventually returns a typed output (or a typed backtrack signal asking the orchestrator to rewind)." A6 will own *when* stages run; A4 owns *what* they consume and produce. Each pipeline stage gets a pair of frozen Pydantic v2 models: `LiteratureReviewInput` / `LiteratureReviewOutput`, etc. Concrete implementations subclass `Stage[InputT, OutputT]` (a `Generic[InputT, OutputT]` ABC, not a Protocol — we want runtime-callable `validate_input()` / `validate_output()` and `__init_subclass__` registration) and declare four `ClassVar`s: `stage_name`, `input_model`, `output_model`, `backtrack_targets`. The framework discovers implementations through entry-point group `agentlabx.stages`, validates the declared models match the canonical contract registry, and exposes a `StageRegistry` listing all impls per stage. A `StageContext` is a frozen dataclass passed alongside the input — it carries the `run_id`, `project_id`, `stage_run_id`, the user `identity`, and *function references* (not bound services) the stage may call (`emit_event`, `now()`); the actual LLM/MCP/RAG service handles arrive in A6 when the orchestrator wires them. `execute()` returns a `StageResult` — a discriminated union of `StageOutput[OutputT]` (success, with optional `ReproducibilityContract`) and `BacktrackSignal` (`target_stage`, `reason`, `preserve` hint). The `StageIOValidator` is a pure function: given a stage name + a candidate output payload, validate against the contract registry's output model and (for experimentation-class artifacts that declare `requires_reproducibility=True`) require a complete `ReproducibilityContract`.

**Tech stack:** Python 3.12 · Pydantic v2 (frozen `BaseModel`s) · `importlib.metadata.entry_points` (existing pattern from A2/A3 plugin registry) · pytest + pytest-asyncio · ruff (`ANN`/`ANN401`) · mypy `--strict`. **No new runtime deps.** No DB schema changes (run/checkpoint persistence is A6).

**Verification gate (SRS §4.2 Stage A4):**

1. **Contract registry covers all 8 pipeline stages** — `literature_review`, `plan_formulation`, `data_exploration`, `data_preparation`, `experimentation`, `interpretation`, `report_writing`, `peer_review` — each with input + output Pydantic models that import cleanly and round-trip through `model_validate` / `model_dump`.
2. **Echo-stub stage registered for every contract via entry point.** `agentlabx.stages` entry-point group lists 8 names; each resolves to a class whose `stage_name` matches its entry-point name and whose declared `input_model`/`output_model` are exactly the canonical models from the registry (mismatch → `StageContractMismatchError` at registration).
3. **Validator accepts conforming output, rejects schema violations** — `StageIOValidator.validate_output("experimentation", {...})` accepts a complete payload; rejects (a) missing required fields, (b) wrong type, (c) for stages flagged `requires_reproducibility=True`, missing/incomplete `ReproducibilityContract`.
4. **Backtrack signal type round-trips** — a stage may return `BacktrackSignal(target_stage="plan_formulation", reason="…", preserve={"citations"})`; the orchestrator (stubbed in A4 tests) reads `.target_stage`, the validator confirms `target_stage` is in the calling stage's declared `backtrack_targets` (refusal otherwise).
5. **Reproducibility contract** — every required FR-7 field present (`seed`, `env_hash`, `deps_snapshot`, `run_command`, `container_image`, `git_ref`); validator rejects partial contracts.
6. **mypy --strict + ruff ANN clean** on production + test code; no `Any`, no `object`-as-placeholder.
7. **No DB migration, no REST surface, no UI work.** A4 is internal Python contract surface only — discovery/validation paths exercised through pytest, not HTTP.

**Non-goals (deferred, do not creep):**

- ❌ Stage execution. A6 owns `execute()`-call invocation, transition rules, checkpoint+resume, and the actual graph.
- ❌ Run/checkpoint persistence. No SQLite tables in A4.
- ❌ Backtrack-attempt counters / per-edge retry caps. A6 owns these.
- ❌ Frontend. Layer C only.
- ❌ Real LLM/MCP/RAG wiring. Echo stubs use the inputs they receive and produce minimal valid outputs deterministically — they do not call A2/A3.
- ❌ Internal stage flow (Plan→Gate→Work→Evaluate→Decide). Per SRS §4.1 (2): each stage owns its internal shape — A4 only fixes the I/O boundary.

---

## File structure (locked in before task decomposition)

```
agentlabx/
├── stages/
│   ├── __init__.py              # re-exports: Stage, StageContext, StageResult, StageOutput, BacktrackSignal,
│   │                            #            ReproducibilityContract, StageIOValidator, StageRegistry,
│   │                            #            and every canonical Input/Output model
│   ├── protocol.py              # Stage[InputT, OutputT] ABC + StageContext + StageResult + StageOutput +
│   │                            # BacktrackSignal + exceptions (StageContractMismatchError,
│   │                            # StageValidationError, BacktrackTargetError)
│   ├── reproducibility.py       # ReproducibilityContract Pydantic model (FR-7 fields, frozen)
│   ├── registry.py              # StageRegistry — canonical-contract map + impl discovery via entry points;
│   │                            # registers EchoStage subclasses; raises on contract mismatch
│   ├── validator.py             # StageIOValidator — pure functions: validate_input, validate_output,
│   │                            # validate_backtrack
│   └── contracts/
│       ├── __init__.py          # re-exports the 8 contract pairs
│       ├── _shared.py           # shared sub-models: Citation, ChunkRef, Hypothesis, Metric, ArtifactRef,
│       │                        # ResearchQuestion, DatasetRef
│       ├── literature_review.py # LiteratureReviewInput / LiteratureReviewOutput
│       ├── plan_formulation.py  # PlanFormulationInput / PlanFormulationOutput
│       ├── data_exploration.py  # DataExplorationInput / DataExplorationOutput
│       ├── data_preparation.py  # DataPreparationInput / DataPreparationOutput
│       ├── experimentation.py   # ExperimentationInput / ExperimentationOutput  (requires_reproducibility=True)
│       ├── interpretation.py    # InterpretationInput / InterpretationOutput
│       ├── report_writing.py    # ReportWritingInput / ReportWritingOutput
│       └── peer_review.py       # PeerReviewInput / PeerReviewOutput
│
└── stages/echo/
    ├── __init__.py
    └── stages.py                # 8 EchoStage subclasses — minimal valid output for each contract;
                                 # registered as entry points; no LLM/MCP/RAG calls

tests/
├── unit/stages/
│   ├── __init__.py
│   ├── test_reproducibility.py        # round-trip + missing-field rejection
│   ├── test_contracts_roundtrip.py    # every Input/Output model: model_validate(model_dump(x)) == x
│   ├── test_validator_output.py       # validator accepts/rejects (schema + reproducibility)
│   ├── test_validator_backtrack.py    # target_stage in declared backtrack_targets; rejects otherwise
│   ├── test_registry_discovery.py     # entry-point discovery picks up all 8 echo stubs
│   ├── test_registry_mismatch.py      # impl declaring wrong input_model raises StageContractMismatchError
│   └── test_echo_stages.py            # each EchoStage produces valid output per StageIOValidator
└── integration/stages/
    ├── __init__.py
    └── test_pipeline_chain.py         # chain all 8 echo stubs end-to-end through validator,
                                       # piping each output into the next stage's input where shapes overlap
                                       # (e.g., literature_review.output.citations → plan_formulation.input.citations);
                                       # asserts entire pipeline validates without modifying types
```

---

## Cross-cutting prerequisites (do these first; not a numbered task)

- [ ] Confirm `pydantic>=2.7,<3.0` is already in `pyproject.toml` (it is — A1) — no new runtime dep.
- [ ] No new entry-point group needed in `pyproject.toml` until echo stubs exist; add `[project.entry-points."agentlabx.stages"]` block in **Task 9** alongside the echo stubs.
- [ ] Re-read SRS §3.2 (Data Flow), §3.3.2 (Orchestrator), §4.2 row A4. Note that the stage's *internal flow* is **out of scope** — only the I/O boundary is contracted here.
- [ ] Re-read FR-7 carefully — the reproducibility contract fields are normative.

---

## Tool-grounded contract shapes (locked before Task 3)

This plan was revised after a deep audit of the 6 bundled MCP servers' actual tool returns. **Every output field in §Task 4 traces back to a real tool's return shape** — no invented vocabulary. The mapping is summarised here so Tasks 3–4 can be implemented without re-deriving it.

### MCP wire convention reused from A3

Per AgentLabX's bundled-server convention (`agentlabx/mcp/bundles/memory_server.py` line 23, `code_execution_server.py` line 18) and MCP spec **2025-06-18** ([modelcontextprotocol.io/specification/2025-06-18/server/tools](https://modelcontextprotocol.io/specification/2025-06-18/server/tools)): every tool returns one `TextContent` whose `text` is `json.dumps(payload)`. A4's contracts consume `payload` shapes — `BaseModel.model_validate(json.loads(text_content.text))` is the one-liner Layer B will use.

### Bundle → tool → return-payload summary

| Bundle | Tool | Returned payload (shape Layer B parses) |
|--------|------|-----------------------------------------|
| `filesystem` | `read_text_file` | raw `str` |
|              | `directory_tree` | recursive `{name, type, children?}` |
|              | `write_file` / `edit_file` | confirmation/diff `str` |
|              | `list_directory` | text listing `str` |
| `arxiv` | `search_papers` | `{papers: [{paper_id, title, authors:[str], abstract, categories:[str], published_date, pdf_url}]}` |
|         | `download_paper` | `{success, paper_id, storage_path, format}` |
|         | `read_paper` | `{paper_id, title, content (markdown)}` |
| `semantic_scholar` | `paper_relevance_search` / `paper_bulk_search` | `{data: [PaperObj], total, offset, next?}` |
|                    | `paper_details` | `PaperObj` |
|                    | `paper_citations` / `paper_references` | `{data: [{citingPaper|citedPaper: PaperObj, contexts:[str], intents:[str]}]}` |
| `browser` | `fetch` | raw `str` (markdown when `raw=false`, HTML text when `raw=true`) |
| `code_execution` | `code.exec` | `{stdout: str, stderr: str, exit_code: int}` (`exit_code = -1` on timeout; output truncated to 256 KiB) |
| `memory` | `memory.create` | `{id: str}` |
|          | `memory.get` / `memory.search` | `{id, category, body, source_run_id: str|null, created_at: ISO-8601}` (search returns list) |
|          | `memory.delete` | `{deleted: bool}` |

`PaperObj` (S2): `paperId, title, authors:[{authorId, name}], abstract, year, citationCount, referenceCount, externalIds:{DOI?, ArXiv?, ...}, openAccessPdf:{url, status}|null, fieldsOfStudy:[str]|null, venue|null`.

### Watch-outs encoded in this plan

1. **arxiv vs S2 `paper_id` collision** — keep one normalised `Citation` model with `source: Literal["arxiv","semantic_scholar","other"]` discriminator; pair `(source, paper_id)` when keying dicts across mixed sources. Do **not** use a discriminated union — downstream stages iterate citations uniformly without `match` ladders.
2. **S2 author shape flattens** — S2 returns `[{authorId, name}]`; arxiv returns `[str]`. Flatten everything to `list[str]` in `Citation.authors`. Future stages that need h-index get a separate `AuthorRef` model — not in `Citation`.
3. **`code.exec` payload appears in B3/B4/B5/B7** — define one shared `ExecLog` sub-model with field names *exactly matching* the tool (`stdout`, `stderr`, `exit_code`) so `ExecLog.model_validate(json.loads(text))` works directly.
4. **`ArtifactRef.content_hash` is stage-computed**, not tool-produced — filesystem MCP returns no hash. Keep `content_hash` required; document in the docstring that Layer B stages SHA-256 the bytes after `write_file`.
5. **`directory_tree` is recursive** — use `from __future__ import annotations` + `model_rebuild()` at module bottom for `DirectoryNode`.
6. **`memory.created_at` is ISO-8601 string** — declare as `datetime`; Pydantic v2 parses ISO-8601 in `mode="json"` automatically.
7. **`browser.fetch` is plain text** — no JSON shape. Any stage consuming it accepts `str` (currently only a future report_writing usage; not encoded in A4 contracts unless needed).
8. **`paper_citations.contexts/intents` is rich citation context** — useful for B2 related-work paragraphs, but **deferred to v1**: do not add `CitationContext` until a stage actually wants it.
9. **Capability tag cross-reference** — record in each stage's docstring which A3 capability tags its agents will need (`fs_read`, `fs_write`, `paper_search`, `paper_fetch`, `web_fetch`, `code_exec`, `memory_read`, `memory_write`) so A8 allow-list wiring stays consistent. A4 does not enforce this — it's a documentation contract for Layer B implementers.

---

## Tasks

### Task 1 — Reproducibility contract

- [ ] Create `agentlabx/stages/reproducibility.py` with frozen Pydantic `ReproducibilityContract` model.
- [ ] Required fields per FR-7: `seed: int`, `env_hash: str`, `deps_snapshot: dict[str, str]` (package → version), `run_command: str`, `container_image: str | None` (None when not containerised — but field must be *present*; partial omission rejected), `git_ref: str | None` (likewise).
- [ ] Add `created_at: datetime` (default factory `datetime.now(UTC)`).
- [ ] `model_config = ConfigDict(frozen=True, extra="forbid")`.
- [ ] Test: `tests/unit/stages/test_reproducibility.py` — round-trip; partial dict raises `ValidationError`; `env_hash=""` (empty string) rejected via `Field(min_length=1)`.

### Task 2 — Stage protocol primitives

- [ ] Create `agentlabx/stages/protocol.py`.
- [ ] `StageContext` — frozen dataclass with: `run_id: str`, `project_id: str`, `stage_run_id: str`, **`identity_id: str`** (UUID — matches A1's VARCHAR(36) `users.id` and `RegisteredServer.owner_id: str | None` from A3; an `int` here would silently misroute or coerce-fail on real user IDs), **`run_mode: Literal["auto", "hitl"]`** (I-1 fix — SRS §4.2 A6 stores per-run mode; SRS §4.2 A8 says `pi_agent` behaviour depends on it. Stages must read this inside `execute()` to decide whether to call `pi_agent` autonomously or escalate. Threading it later through every stage's payload would be expensive — A4 ships it on the context now), `emit_event: Callable[[str, dict[str, JSONValue]], Awaitable[None]]`, `now: Callable[[], datetime]`. **No service handles** (LLM, MCP, RAG handles arrive in A6). Note: A3's `EventBus.Event.payload` is `dict[str, Any]`; the tighter signature here means the call-site adapter in A6 will need to revalidate before dispatching to the bus — flagged for A6, not A4.

  **HITL audit log is load-bearing (I-5 design note).** Per the Q6 decision, `PIRatification` is not a contract field — A8 emits `PIEscalation` events and A6 gates transitions on them. This is structurally right for HITL flow, but it means the **C2 reproduce CLI must reconstruct HITL decisions by correlating events with stage outputs** — there is no breadcrumb on the artifact itself. A6/C2 implementers should treat the JsonlEventSink as the canonical record of HITL decisions; if event-log retention is ever shortened, HITL-replay will break. Recorded here so A6 doesn't accidentally drop the breadcrumb.
- [ ] `BacktrackSignal` — frozen Pydantic model with `target_stage: str`, `reason: str` (Field min_length=1), `preserve: frozenset[str] = frozenset()`. `model_config = ConfigDict(frozen=True, extra="forbid")`.
- [ ] `StageOutput[OutputT]` — frozen Pydantic generic with `payload: OutputT`, `reproducibility: ReproducibilityContract | None = None`, **`notes: list[NoteRef] = Field(default_factory=list)`** (I-3 fix — SRS §4.2 A7 + FR-12/C4 derive taxonomy from observed notes; per-note metadata is needed, not just cardinality. `NoteRef` is a placeholder shared model defined in Task 3 — A7 fills the list at run time without changing the `StageOutput` contract).
- [ ] `StageResult` — **PEP 695 syntax** (Python 3.12): `type StageResult[OutputT] = StageOutput[OutputT] | BacktrackSignal`. Matches the project's established preference (a3-prereqs commit).
- [ ] `Stage[InputT, OutputT]` — `abc.ABC`, `Generic[InputT, OutputT]`. ClassVars:
  - `stage_name: ClassVar[str]`
  - `input_model: ClassVar[type[BaseModel]]`
  - `output_model: ClassVar[type[BaseModel]]`
  - `backtrack_targets: ClassVar[frozenset[str]]`
  - `required_capabilities: ClassVar[frozenset[str]] = frozenset()` — **the A8 allow-list cross-reference, programmatic not docstring** (so A8 reads a typed surface instead of grepping docstrings; each EchoStage subclass populates it with exactly the capability tags listed in §Task 4). **Docstring MUST clarify (M-2):** "This is the *per-stage union* — every capability any agent in this stage might need. SRS §4.2 A8 specifies the actual allow-list is per-(agent, stage); A8 narrows this set per agent at LLM-call time. A4's value is the orchestrator's pre-flight check, not the runtime gate."
  - `requires_reproducibility: ClassVar[bool] = False` — **doc/sanity field only**. Validator does NOT consult this; canonical source is `STAGE_REPRODUCIBILITY_REQUIRED` in `registry.py` (Task 5). At registration time, `__init_subclass__` checks the subclass's `requires_reproducibility` matches `stage_name in STAGE_REPRODUCIBILITY_REQUIRED` and raises `StageContractMismatchError` on drift. This separates *enforcement* (contract-driven) from *advertisement* (impl-driven), avoiding the I1 footgun where an unregistered impl silently disables validation.
  - Abstract: `async def execute(self, payload: InputT, ctx: StageContext) -> StageResult[OutputT]`.
- [ ] Exceptions: `StageContractMismatchError`, `StageValidationError`, `BacktrackTargetError`.
- [ ] Test: instantiating a `Stage` subclass that omits a required ClassVar fails at `__init_subclass__` (raise `StageContractMismatchError`).
- [ ] Test: a `Stage` subclass declaring `requires_reproducibility=True` for a stage NOT in `STAGE_REPRODUCIBILITY_REQUIRED` raises at `__init_subclass__`. And vice versa: declaring `False` for `experimentation` raises.

### Task 3 — Shared sub-models for contracts (tool-grounded)

- [ ] Create `agentlabx/stages/contracts/_shared.py` with frozen Pydantic models. Every model below traces to a specific MCP tool return (in brackets) or to internal stage glue.

  **Identity / domain primitives:**
  - `ResearchQuestion(text: str, project_id: str)` — internal.
  - `Hypothesis(id: str, statement: str, baselines: list[str], ablations: list[str])` — LLM-synthesised.
  - `DatasetRef(dataset_id: str, name: str, split_hint: str | None)` — internal.
  - `Metric(name: str, value: float, unit: str | None)` — parsed from `code.exec.stdout`.

  **Citation (normalised across arxiv + S2):**
  - `Citation`:
    - `paper_id: str` — arxiv id (`2304.12345v1`) when `source=="arxiv"`, S2 `paperId` (40-char hex) when `source=="semantic_scholar"`. Always pair with `source` to disambiguate.
    - `title: str`
    - `authors: list[str]` — flatten S2 `[{authorId,name}]` to names; arxiv ships names already.
    - `year: int` — for arxiv, parse from `published_date`.
    - `source: Literal["arxiv","semantic_scholar","other"]`
    - `url: str | None`
    - `external_ids: dict[str, str] = Field(default_factory=dict)` — populated from S2 `externalIds` (DOI, ArXiv, MAG, PubMed); empty for arxiv-source.
    - `abstract: str | None = None`
    - `venue: str | None = None` — S2 only.
    - `citation_count: int | None = None` — S2 only.
    - `fields_of_study: list[str] = Field(default_factory=list)` — union of S2 `fieldsOfStudy` and arxiv `categories`.
    - `open_access_pdf_url: str | None = None`

  **RAG / grounding:**
  - `ChunkRef(chunk_id: str, paper_id: str, span_start: int, span_end: int, score: float)` — A5 RAG return shape. Not a tool — internal. **I-4 fix:** flattened from `span: tuple[int, int]` because Chroma's metadata payload is `dict[str, str|int|float|bool]`; tuples serialize to JSON arrays and a frozen Pydantic model with `tuple` field would diverge on round-trip equality after Chroma persistence. Add a model validator asserting `span_end >= span_start`.

  **A7 hook (placeholder for current-run notes):**
  - `NoteRef(id: str, category: str)` — minimal placeholder so A4's `StageOutput.notes: list[NoteRef]` field carries per-note metadata (not just cardinality) per FR-12 + SRS §4.2 A7 / C4 needs. A7 will populate the list and may extend `NoteRef` with `body: str`, `created_at: datetime`, etc. — but the *field name `notes`* and *list-of-`NoteRef` shape* are locked here so A7 doesn't reshape `StageOutput` later.

  **Artifacts (filesystem-produced + stage-hashed):**
  - `ArtifactRef(artifact_id: str, kind: Literal["dataset","split","script","model","report","plot","table","other"], path: str, content_hash: str)`. **Docstring MUST note**: `path` is the absolute path passed to `filesystem.write_file`; `content_hash` is computed in stage code (SHA-256 of the bytes after write) — filesystem MCP returns no hash.

  **Tool-output sub-models (from §Tool-grounded contract shapes):**
  - `ExecLog(stdout: str, stderr: str, exit_code: int)` — exact match to `code.exec` payload. `exit_code = -1` indicates timeout. Output strings are pre-truncated upstream at 256 KiB.
  - `MemoryEntryRef(id: str, category: str, body: str, source_run_id: str | None, created_at: datetime)` — exact match to `memory.get` / `memory.search` element shape. `created_at` is ISO-8601 string on the wire; Pydantic parses to `datetime` in `mode="json"`.

  **(Q5 pushback applied — these models are NOT in `_shared.py`.)** `DirectoryNode`, `ArxivPaperRef`, and `S2PaperRef` are *not* shipped as part of A4 contracts. Raw arxiv/S2 hits and directory snapshots already land in the A3 JsonlEventSink (every MCP tool call is persisted). The C2 reproduce CLI replays from events — that is what the event log is for. Adding these to the contract layer would create a surface Layer B has to maintain forever; contracts should carry only what downstream stages need to function. The `test_tool_payload_compat.py` test (Task 4) still asserts `arxiv.search_papers.papers[0]`-shaped dicts and `filesystem.directory_tree` 3-level dicts validate cleanly against an *inline* test-only model — so the grounding assertion is preserved without polluting the contract surface.

  **(Q6 pushback applied — `PIRatification` is NOT in `_shared.py`.)** A4 will not pre-bake A8 hooks. Per the SRS, `pi_agent` may be called at the end of multiple stages (plan_formulation, experimentation, peer_review). The ratification artifact belongs in the *event log* (`PIEscalation` events emitted by A8), not in stage output payloads. Including it on only one output is half a forward-compat hedge; including it on all of them inflates every contract for a hook that doesn't exist yet. Decision: omit entirely from A4; A8 will emit the ratification signal as an event and the orchestrator (A6) will gate transitions on it.

  **Findings / action items (synthesis-side):**
  - `Finding(id: str, statement: str, cited_metric_names: list[str], cited_artifact_ids: list[str], cited_chunk_ids: list[str] = Field(default_factory=list), verbatim_values: dict[str, float])` — `verbatim_values` reproduces the exact `Metric.value` referenced (per SRS B6: "cites actual metric values verbatim; no fabricated numbers"). **I-2 fix:** `cited_chunk_ids` enables per-finding RAG grounding so the B7 citation verifier can trace each finding to its source chunk(s) without reconstructing the mapping post-hoc. Aggregate `ReportWritingOutput.cited_chunk_ids` is a union over `findings[*].cited_chunk_ids`. Validator on `interpretation` should optionally check `verbatim_values` keys are a subset of `cited_metric_names` (defer enforcement to validator Task 6 only as a non-fatal warning if added).
  - `ActionItem(id: str, severity: Literal["minor","major","blocker"], description: str, target_section: str | None)` — used by `peer_review`.

- [ ] All models `frozen=True`, `extra="forbid"`. Re-exported from `agentlabx/stages/contracts/__init__.py`.
- [ ] Test: `tests/unit/stages/test_contracts_roundtrip.py` round-trips every shared model. Specifically test (a) `MemoryEntryRef` parses an ISO-8601 string into `datetime`, (b) `Citation` round-trips both arxiv-source and s2-source variants with the right optional fields populated, (c) `ExecLog` round-trips a `code.exec` payload with `exit_code = -1`.

### Task 4 — Per-stage contracts (8 files, tool-grounded)

For **each** of the 8 stages, create `agentlabx/stages/contracts/<stage_name>.py` with two frozen Pydantic models. Every output field cites the producing tool in brackets — when the source is `[LLM]` the field is synthesised by the stage's agents and has no MCP origin.

Each contract module **MUST** include a module docstring listing the A3 capability tags the stage's agents will need (for A8 allow-list cross-reference) — e.g. `# Capabilities: paper_search, paper_fetch, memory_read`.

- [ ] **literature_review** — Capabilities: `paper_search`, `paper_fetch`, `memory_read`.
  - `Input`: `question: ResearchQuestion`, `prior_corpus_ids: list[str] = []`, `target_count_min: int = 10`.
  - `Output`:
    - `citations: list[Citation]` — len ≥ `target_count_min`. Each item normalised from `arxiv.search_papers.papers[*]` or S2 `paper_relevance_search.data[*]`.
    - `summaries: list[CitationSummary]` where `CitationSummary = {citation_id: str, paragraph: str, chunk_refs: list[ChunkRef]}`. `paragraph` LLM-synthesised over `arxiv.read_paper.content` (markdown) or RAG; `chunk_refs` from A5.
    - `corpus_id: str` — assigned by RAG ingestion (A5). [internal]
    - (Raw arxiv/S2 hits are NOT carried — they live in the JsonlEventSink. See Q5 pushback in Task 3.)

- [ ] **plan_formulation** — Capabilities: `memory_read`, optionally `paper_search` (related-work expansion).
  - `Input`: `citations: list[Citation]`, `corpus_id: str`, `question: ResearchQuestion`.
  - `Output`:
    - `hypotheses: list[Hypothesis]` — ≥1. [LLM]
    - `methodology: str` [LLM]
    - `success_criteria: list[str]` [LLM]
    - `accepted_citation_ids: list[str]` — subset of input `citations[*].paper_id`.
    - (PI ratification is NOT carried on the output — A8 emits it as an event. See Q6 pushback in Task 3.)

- [ ] **data_exploration** — Capabilities: `fs_read`, `fs_write`, `code_exec`.
  - `Input`: `dataset: DatasetRef`, `hypotheses: list[Hypothesis]`.
  - `Output`:
    - `summary_stats: dict[str, float]` — parsed from `code.exec.stdout` (pandas describe() JSON-print).
    - `plots: list[ArtifactRef]` — paths written via `filesystem.write_file`.
    - `characterization: str` [LLM]
    - `exec_log: ExecLog` [← `code.exec`]
    - (Directory snapshot is NOT carried — `filesystem.directory_tree` calls land in events. See Q5 pushback in Task 3.)

- [ ] **data_preparation** — Capabilities: `fs_read`, `fs_write`, `code_exec`.
  - `Input`: `dataset: DatasetRef`, `characterization: str`, `plan_excerpt: str`.
  - `Output`:
    - `prep_script: ArtifactRef` — written via `filesystem.write_file`; `content_hash` computed in stage code.
    - `splits: dict[str, ArtifactRef]` — keys e.g. `train`/`val`/`test`; each path is the `filesystem.write_file` arg.
    - `transforms: list[str]` [LLM]
    - `exec_log: ExecLog` [← `code.exec`]

- [ ] **experimentation** — Capabilities: `fs_read`, `fs_write`, `code_exec`, `memory_write`. **`requires_reproducibility = True`** (set as `ClassVar` on the Stage subclass).
  - `Input`: `hypotheses: list[Hypothesis]`, `splits: dict[str, ArtifactRef]`, `prep_script: ArtifactRef`.
  - `Output`:
    - `metrics: list[Metric]` — ≥1. Values parsed from `code.exec.stdout` (JSON or numeric line).
    - `artifacts: list[ArtifactRef]` — ≥1. Model checkpoints / plots / tables; paths from `filesystem.write_file`.
    - `exec_logs: list[ExecLog]` — one entry per run (baseline + each ablation per SRS B5). [← `code.exec`]
    - `memory_entries_created: list[str] = Field(default_factory=list)` — ids returned by `memory.create.id` for findings persisted during the run.
  - **Reproducibility**: validator requires a complete `ReproducibilityContract` accompanying any `experimentation` output. Fields populated by the orchestrator/runtime (A6) — NOT by MCP tools.

- [ ] **interpretation** — Capabilities: `memory_read`, optionally `code_exec` (sanity-check derivations).
  - `Input`: `metrics: list[Metric]`, `artifacts: list[ArtifactRef]`, `hypotheses: list[Hypothesis]`.
  - `Output`:
    - `findings: list[Finding]` — ≥1. Each carries `verbatim_values` reproducing exact `Metric.value`s referenced (per SRS B6 anti-fabrication rule).
    - `confidence_notes: list[str]` [LLM]

- [ ] **report_writing** — Capabilities: `fs_read`, `fs_write`, optionally `code_exec` (pandoc/pdflatex render), optionally `web_fetch`.
  - `Input`: `findings: list[Finding]`, `citations: list[Citation]`, `metrics: list[Metric]`, `methodology: str`.
  - `Output`:
    - `report_markdown: ArtifactRef` — written via `filesystem.write_file`.
    - `report_latex: ArtifactRef | None`
    - `report_pdf: ArtifactRef | None`
    - `cited_chunk_ids: list[str]` — RAG chunk ids the citation verifier (A5) is to confirm. [internal]
    - `pandoc_log: ExecLog | None = None` — present iff PDF render ran. [← `code.exec`]

- [ ] **peer_review** — Capabilities: `fs_read`, `memory_read`.
  - `Input`: `report_markdown: ArtifactRef`, `findings: list[Finding]`, **`metrics: list[Metric]`** (M-1 fix — SRS §4.2 B8 expects peer_review to emit a backtrack on a "fundamental issue"; that requires reading the actual numbers, not just the rendered report), **`methodology: str`** (mirrors `ReportWritingInput`).
  - `Output`:
    - `critique: str` [LLM]
    - `action_items: list[ActionItem]` — minor/major/blocker severities.
    - `recommended_backtrack: BacktrackSignal | None` — `target_stage` may be any earlier stage (see Task 7).

- [ ] Test: `tests/unit/stages/test_contracts_roundtrip.py` — for each contract, build a minimal-valid instance, dump, re-validate, assert equal. Specifically assert (a) `ExperimentationOutput.exec_logs` round-trips a list of `ExecLog`s with mixed `exit_code` values (incl. `-1` timeout); (b) `DataExplorationOutput.exec_log` round-trips; (c) `ReportWritingOutput.pandoc_log = None` round-trips alongside the populated case.

- [ ] Test: `tests/unit/stages/test_tool_payload_compat.py` — **the load-bearing assertion that A4 stays grounded**. For each tool whose payload feeds a contract field, construct a representative JSON dict matching the tool's documented return and assert a `model_validate(...)` on the corresponding shared model accepts it without modification:
  - `code.exec` `{stdout, stderr, exit_code}` → `ExecLog` (incl. `exit_code = -1`)
  - `memory.get` `{id, category, body, source_run_id, created_at: ISO-8601}` → `MemoryEntryRef`
  - `arxiv.search_papers.papers[0]` (full shape: `paper_id, title, authors, abstract, categories, published_date, pdf_url`) → maps cleanly to a constructed `Citation` via the documented projection (`source="arxiv"`, `year` parsed from `published_date`, `fields_of_study=categories`, `open_access_pdf_url=pdf_url`). Asserts the projection is loss-tolerant — a stage author can take the raw arxiv dict and produce a valid `Citation` with no other inputs.
  - S2 `paper_relevance_search.data[0]` → maps cleanly to a constructed `Citation` via the documented projection (`source="semantic_scholar"`, `external_ids` from `externalIds`, `citation_count` from `citationCount`, `venue` from `venue`).
  - The `filesystem.directory_tree` payload is **not** asserted against an A4 model (no `DirectoryNode` ships) — but the test file should include a comment noting where the raw dict goes (event log) so a future reader doesn't think it was forgotten.

### Task 5 — Stage registry (canonical contracts + discovery)

- [ ] Create `agentlabx/stages/registry.py` with module-level constants (canonical, contract-driven enforcement — not impl-driven):
  - `STAGE_NAMES: tuple[str, ...]` — the 8 canonical names in pipeline order.
  - `CANONICAL_CONTRACTS: dict[str, tuple[type[BaseModel], type[BaseModel]]]` — name → (input, output) pair.
  - **`STAGE_REPRODUCIBILITY_REQUIRED: frozenset[str] = frozenset({"experimentation"})`** — the *single source of truth* for which stages need a `ReproducibilityContract`. Validator (Task 6) reads this constant; `Stage` subclasses' `requires_reproducibility` ClassVar is checked against it at registration but never consulted by the validator.
  - **`CANONICAL_BACKTRACK_TARGETS: dict[str, frozenset[str]]`** — the upper-bound set of stages each stage may target. Encodes the SRS Layer-B table (see Task 7 for the actual mapping). Implementations may *narrow* but not *broaden* — registry enforces this at `register()`.
  - **`CANONICAL_PRESERVE_TAGS: dict[str, frozenset[str]]`** — the upper-bound set of preserve-tag names each stage may emit on a `BacktrackSignal.preserve` (B-2 fix: opaque `frozenset[str]` would cause silent data loss on a typo). Tags are conceptually "names of fields on this stage's *own* output that the orchestrator should keep across the rollback." Seeded from the contract field names below; A6 may extend per stage as needed:
    - `literature_review`: `frozenset()` (no backtrack targets — tag set unused, declared for symmetry)
    - `plan_formulation`: `frozenset({"accepted_citation_ids"})` — explicitly required by SRS §4.2 B2 ("partial rollback preserves accepted citations"). **Tag matches the actual field name on `PlanFormulationOutput`** (Task 4); the SRS prose says "accepted citations" but the per-stage tag namespace is field names per the docstring above. A Layer B impl emitting `preserve=frozenset({"accepted_citations"})` (without `_ids` suffix) would correctly raise `BacktrackTargetError` — which is the whole point of B-2.
    - `data_exploration`: `frozenset({"summary_stats", "plots", "characterization"})`
    - `data_preparation`: `frozenset({"prep_script", "splits", "transforms"})`
    - `experimentation`: `frozenset({"metrics", "artifacts", "memory_entries_created"})`
    - `interpretation`: `frozenset({"findings"})`
    - `report_writing`: `frozenset({"report_markdown", "report_latex", "report_pdf", "cited_chunk_ids"})`
    - `peer_review`: `frozenset({"action_items"})`
- [ ] `class StageRegistry`:
  - `register(impl: type[Stage])` — validates ALL of:
    1. `impl.stage_name in STAGE_NAMES`,
    2. `(impl.input_model, impl.output_model)` is exactly `CANONICAL_CONTRACTS[stage_name]`,
    3. `impl.requires_reproducibility == (stage_name in STAGE_REPRODUCIBILITY_REQUIRED)`,
    4. `impl.backtrack_targets <= CANONICAL_BACKTRACK_TARGETS[stage_name]` (subset, not equality — narrowing is allowed),
    5. every tag in `impl.required_capabilities` appears in `agentlabx.mcp.capabilities.SEED_CAPABILITIES` (imported — keeps A4 in lockstep with A3's seed; A9's future `skill_invoke` extends the seed and "just works" without an A4 change). **Unknown tags warn via `warnings.warn(UserWarning)` rather than raise** — matches A3's docstring policy at `agentlabx/mcp/capabilities.py:26` ("Tools may declare capabilities outside this set, but doing so should produce a warning"). Only rules 1–4 raise `StageContractMismatchError`.
  - **`implementations_for(stage_name: str) -> list[type[Stage]]`** — renamed from `list()` to avoid shadowing the builtin (I2).
  - `default_for(stage_name: str) -> type[Stage]` — returns the sole registered impl when N=1; **raises `NotImplementedError("multiple impls registered for {stage_name} — A6 will read selected_impl from settings")` when N>1**, and `LookupError` when N=0. This makes A4 the smallest correct surface: ship the interface but force A6 to make the selection rule explicit before Layer B can shadow an echo stub. (Q1 pushback applied — no hidden non-determinism.)
- [ ] `discover_stages(registry: StageRegistry) -> None` — calls `entry_points(group="agentlabx.stages")`, loads each, calls `registry.register(impl)`.
- [ ] Test: `tests/unit/stages/test_registry_mismatch.py` covers the four `register()` failure modes that raise (wrong output model, wrong stage name, mismatched `requires_reproducibility`, broadened `backtrack_targets`). Capability-tag handling is separate (next bullet).
- [ ] Test: `tests/unit/stages/test_registry_capability_warning.py` — register a Stage subclass declaring `required_capabilities={"fs_read", "made_up_cap"}`; assert `pytest.warns(UserWarning)` fires and registration *succeeds* (matches A3's warn-not-reject policy). Also assert that no warning fires when `required_capabilities={"web_browse"}` (already in `SEED_CAPABILITIES`).
- [ ] Test: `tests/unit/stages/test_registry_discovery.py` — after `discover_stages` runs, every name in `STAGE_NAMES` has ≥1 registered impl AND `default_for(stage_name)` returns the echo stub (N=1 case).
- [ ] Test: `tests/unit/stages/test_registry_default_for.py` — register a second impl for `literature_review`; assert `default_for("literature_review")` raises `NotImplementedError` with the A6 message.

### Task 6 — Stage I/O validator

- [ ] Create `agentlabx/stages/validator.py` with pure functions. **Reproducibility enforcement is contract-driven**: validator reads `STAGE_REPRODUCIBILITY_REQUIRED` directly — never queries the registry for a Stage subclass (avoids the I1 footgun where an unregistered impl silently disables validation).
  - `validate_input(stage_name: str, payload: dict[str, JSONValue]) -> BaseModel` — looks up `CANONICAL_CONTRACTS[stage_name][0]`, calls `model_validate(payload)`, re-raises as `StageValidationError`.
  - `validate_output(stage_name: str, output: dict[str, JSONValue], reproducibility: dict[str, JSONValue] | None) -> StageOutput[BaseModel]` — looks up `CANONICAL_CONTRACTS[stage_name][1]`, validates the payload, then **if `stage_name in STAGE_REPRODUCIBILITY_REQUIRED`** requires `reproducibility` to be a complete `ReproducibilityContract` (calls `ReproducibilityContract.model_validate(reproducibility)`); rejects when missing. Raises `StageValidationError` on any failure.
  - **Docstring note (M1):** "The return type is `StageOutput[BaseModel]` because Pydantic v2 generic erasure prevents recovering the concrete `OutputT` at the validator boundary. Callers that need the concrete type for static checking should `assert isinstance(result.payload, LiteratureReviewOutput)` (or the relevant model) — the runtime instance IS the concrete type, only the static binding is erased."
  - `validate_backtrack(origin_stage_name: str, signal: BacktrackSignal) -> None` — raises `BacktrackTargetError` if `signal.target_stage not in CANONICAL_BACKTRACK_TARGETS[origin_stage_name]`. **Also raises `BacktrackTargetError` if `signal.preserve` is not a subset of `CANONICAL_PRESERVE_TAGS[origin_stage_name]`** (B-2 enforcement — catches preserve-tag typos at the validator boundary; the silent-data-loss case where `"citation"` vs `"citations"` means "preserve nothing" cannot happen). **Reads from the canonical constants, NOT from the registered impl's fields** — enforcement must not depend on which impl happens to be registered.
- [ ] Test: `tests/unit/stages/test_validator_output.py` — happy path; schema violation; missing reproducibility on experimentation; **reproducibility presence on a non-experimentation stage is silently allowed** (it's just an extra dict the validator ignores) — confirm this is the intended behavior.
- [ ] Test: `tests/unit/stages/test_validator_backtrack.py` — `peer_review` may target any earlier stage; `literature_review` (no targets) raises on any backtrack; backtrack to a stage that *exists* in `STAGE_NAMES` but is *not* in the origin's canonical targets still raises (e.g. `data_preparation → literature_review`). **Plus B-2 cases:** `BacktrackSignal(target_stage="literature_review", preserve=frozenset({"accepted_citation_ids"}))` from `plan_formulation` is accepted; `preserve=frozenset({"accepted_citations"})` (suffix-drop typo — exactly the silent-data-loss class B-2 prevents) raises `BacktrackTargetError`; `preserve=frozenset()` (empty) is always accepted.

### Task 7 — Backtrack-target declarations on echo stubs

- [ ] Encode the SRS Layer-B backtrack table in the echo stubs' `backtrack_targets`:
  - literature_review → `frozenset()`
  - plan_formulation → `frozenset({"literature_review"})`
  - data_exploration → `frozenset({"plan_formulation"})`
  - data_preparation → `frozenset({"data_exploration"})`
  - experimentation → `frozenset({"plan_formulation","data_preparation","data_exploration"})`
  - interpretation → `frozenset({"experimentation"})`
  - report_writing → `frozenset({"interpretation"})`
  - peer_review → `frozenset(set(STAGE_NAMES) - {"peer_review"})`
- [ ] These are the **default** backtrack targets carried by the echo stubs; real B-stage impls in Layer B may *narrow* but not *broaden* (validator enforced). Note in plan: A6 may relax this rule if needed; A4 just enforces the contract as declared.

### Task 8 — Echo stage stubs

- [ ] Create `agentlabx/stages/echo/stages.py` with **8 deterministic** `Stage` subclasses (`EchoLiteratureReviewStage`, etc.).
- [ ] Each `execute()` synthesises a minimum-valid instance of its `output_model` from the input — e.g., `EchoLiteratureReviewStage` returns `target_count_min` dummy citations + matching summaries; `EchoExperimentationStage` returns one metric + one artifact + a synthetic `ReproducibilityContract`.
- [ ] No LLM/MCP/RAG calls. No randomness — outputs are pure functions of the input.
- [ ] Each emits a single `stage.echo.completed` event via `ctx.emit_event` so observability is sanity-checkable.
- [ ] Register in `pyproject.toml` under `[project.entry-points."agentlabx.stages"]`:
  ```
  literature_review = "agentlabx.stages.echo.stages:EchoLiteratureReviewStage"
  plan_formulation  = "agentlabx.stages.echo.stages:EchoPlanFormulationStage"
  data_exploration  = "agentlabx.stages.echo.stages:EchoDataExplorationStage"
  data_preparation  = "agentlabx.stages.echo.stages:EchoDataPreparationStage"
  experimentation   = "agentlabx.stages.echo.stages:EchoExperimentationStage"
  interpretation    = "agentlabx.stages.echo.stages:EchoInterpretationStage"
  report_writing    = "agentlabx.stages.echo.stages:EchoReportWritingStage"
  peer_review       = "agentlabx.stages.echo.stages:EchoPeerReviewStage"
  ```
- [ ] After editing `pyproject.toml`, run `uv pip install -e .` (or `uv sync`) so entry-point metadata is regenerated.
- [ ] Test: `tests/unit/stages/test_echo_stages.py` — invoke each echo stub with a minimal valid input, assert validator accepts the output.

### Task 9 — Pipeline-chain integration test

- [ ] Create `tests/integration/stages/test_pipeline_chain.py`:
  - Construct a minimal `ResearchQuestion`.
  - Run `EchoLiteratureReviewStage` → take its output → construct `PlanFormulationInput` from the output's citations + corpus_id + question → run `EchoPlanFormulationStage` → continue through all 8.
  - At every boundary, call `StageIOValidator.validate_input(next_stage, payload)` and `validate_output(prev_stage, output, repro)`.
  - Asserts entire chain validates; asserts `ReproducibilityContract` present on `experimentation` output and absent on others (where it should be `None`).
  - Asserts `EchoPeerReviewStage` returns either a clean output or a `BacktrackSignal` with a valid target.
- [ ] Mark with `@pytest.mark.integration`.

### Task 10 — Documentation + SRS reverse-engineer pass

- [ ] Update `README.md` "What's shipped" to add an **A4** bullet. Mirror the existing format used for A1/A2/A3.
- [ ] Update `CLAUDE.md` "What's shipped" to add A4.
- [ ] Reverse-engineer SRS §4.2 row A4 to reflect what actually shipped (per the spec-alignment memory rule). Specifically: confirm the contract-model names match what is in code; confirm the verification gate language matches; record the `requires_reproducibility` mechanism.

### Task 11 — Quality gate

- [ ] `uv run ruff check agentlabx tests` — clean.
- [ ] `uv run ruff format --check agentlabx tests` — clean.
- [ ] `uv run mypy --strict agentlabx tests/unit/stages tests/integration/stages` — clean.
- [ ] `uv run pytest tests/unit/stages tests/integration/stages -v` — all pass.
- [ ] `uv run pytest -q` (full suite, including A1/A2/A3) — no regressions.
- [ ] Commit on `stageA4-stage-contracts` feature branch. **Do not merge to main without explicit user approval.** ("Continue" never means "merge.")

---

## Resolved decisions (from the 2026-05-14 review)

All seven open questions answered + four code-review findings folded back into the tasks above. Captured here so the rationale survives.

| # | Topic | Decision |
|---|-------|----------|
| Q1 | `default_for` tiebreak | **Raise `NotImplementedError` when N>1** (with the message `"multiple impls registered for {stage_name} — A6 will read selected_impl from settings"`). Ship the interface; force A6 to make the selection rule explicit. No hidden non-determinism. |
| Q2 | `requires_reproducibility = experimentation only` | **Confirmed.** Matches FR-7 verbatim. |
| Q3 | ABC + Generic over Protocol | **Confirmed.** `__init_subclass__` and ClassVar enforcement need a base class. |
| Q4 | `BacktrackSignal.preserve = frozenset[str]` | **Confirmed.** Opaque stage-local tags; future structured needs go on stage outputs, not on the signal. |
| Q5 | Raw provenance fields on outputs | **Dropped.** A3 JsonlEventSink already persists every MCP tool call; C2 reproduces from events. Keeping `raw_*` on contracts would saddle Layer B with a maintenance surface for no downstream consumer. `DirectoryNode`, `ArxivPaperRef`, `S2PaperRef` are NOT shipped. |
| Q6 | `PIRatification` placeholder | **Dropped.** Including it on only one stage is half a hedge; including it on every stage that could gate inflates contracts for an unbuilt hook. A8 emits `PIEscalation` events; A6 gates transitions on them. The output payload stays clean. |
| Q7 | `Citation` discriminator vs union | **Confirmed.** Single normalised model with `source` discriminator + optional source-specific fields. |
| C1 | `StageContext.identity_id: int` was wrong | **Fixed to `str`** (UUID, matches A1's `users.id` and A3's `RegisteredServer.owner_id`). |
| I1 | Validator looking up `requires_reproducibility` via the registered Stage was a footgun | **Moved to `STAGE_REPRODUCIBILITY_REQUIRED: frozenset[str]`** in `registry.py`. Validator reads the constant. Stage subclasses' `requires_reproducibility` becomes a doc field checked against the constant at registration. |
| I2 | `StageRegistry.list(...)` shadows builtin | **Renamed to `implementations_for(stage_name)`.** |
| I3 | Capabilities buried in docstrings | **Promoted to `Stage.required_capabilities: ClassVar[frozenset[str]]`.** A8 reads a typed surface. Registry validates each tag against the known A3 capability set at `register()`. |
| I4 | "Narrow but not broaden" backtrack rule was unenforced | **`CANONICAL_BACKTRACK_TARGETS` constant** in registry; `register()` checks `impl.backtrack_targets <= canonical[stage_name]`. |
| M1 | `validate_output` return type erases concrete `OutputT` | **Documented in the validator docstring** with the canonical `assert isinstance(...)` recovery pattern for callers needing static narrowing. |
| M2 | PEP 695 type alias syntax | **Adopted.** `type StageResult[OutputT] = StageOutput[OutputT] | BacktrackSignal`. |
| M3 | `emit_event` signature tighter than `EventBus.Event.payload` | **Acknowledged in Task 2 note.** A6's call-site adapter will revalidate before dispatching to the bus. No A4 change needed. |

### Second-pass review (2026-05-15)

| # | Topic | Decision |
|---|-------|----------|
| B-1 | Capability whitelist contradicted A3 + missed `web_browse` | **Imported `SEED_CAPABILITIES` from `agentlabx.mcp.capabilities`**; unknown tags now `warnings.warn(UserWarning)` (matches A3 docstring policy) instead of raising. A9's future `skill_invoke` extends the seed and "just works." |
| B-2 | Opaque `BacktrackSignal.preserve` tags risked silent data loss | **Added `CANONICAL_PRESERVE_TAGS: dict[str, frozenset[str]]` per-stage seed** (plan_formulation: `{"accepted_citations"}`, etc.); validator checks `signal.preserve <= canonical[origin]`. Typo cases now raise `BacktrackTargetError` instead of meaning "preserve nothing." |
| I-1 | `StageContext` missing `run_mode` | **Added `run_mode: Literal["auto", "hitl"]`.** Cheaper now than threading through every stage payload later. |
| I-2 | `Finding` had no per-finding RAG grounding | **Added `cited_chunk_ids: list[str] = Field(default_factory=list)`.** B7 citation verifier now traces each finding directly to source chunks. |
| I-3 | `StageOutput.notes_count: int` too thin for A7/C4 | **Replaced with `notes: list[NoteRef]`** + new `NoteRef(id: str, category: str)` placeholder in `_shared.py`. A7 fills the list, may extend `NoteRef`, doesn't reshape `StageOutput`. |
| I-4 | `ChunkRef.span: tuple[int, int]` won't survive Chroma round-trip | **Flattened to `span_start: int, span_end: int`** + `span_end >= span_start` validator. Avoids tuple→JSON-array equality drift discovered at A5. |
| I-5 | HITL replay depends on event log only | **Recorded as Task 2 design note** for A6/C2 implementers — JsonlEventSink is the canonical record of HITL decisions; if retention shortens, replay breaks. |
| M-1 | `PeerReviewInput` missing `metrics` + `methodology` | **Added.** B8 needs actual numbers to emit "fundamental issue" backtracks. |
| M-2 | `required_capabilities` per-stage vs per-(agent,stage) | **Added docstring on `Stage.required_capabilities`** clarifying it is the per-stage union; A8 narrows per-agent at LLM-call time. |
| M-3 | A9 `skill_invoke` reservation | **Resolved by B-1.** Importing `SEED_CAPABILITIES` makes A4 stay in lockstep — A9's tag will appear when A9 ships. |

No remaining open questions. Ready to start prerequisites + Task 1.
