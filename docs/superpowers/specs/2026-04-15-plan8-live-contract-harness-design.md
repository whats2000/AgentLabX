---
plan: 8
title: Live DFS Contract Harness — End-to-End Real-Model System Test
status: design
authors: [whats2000, claude]
created: 2026-04-15
---

# Plan 8 — Live DFS Contract Harness

## 1. Purpose

AgentLabX has reached a point where unit and integration tests pass, but the **first live run against a real model (Gemini flash, 2026-04-15) surfaced four previously-invisible bugs** within eight seconds:

- **B1** — `/graph` 500s on `Transition.get("from_stage")` (Pydantic model vs dict)
- **B2** — `resolve_agent` hardcoded `claude-sonnet-4-6`; `settings.llm.default_model` never reaches the stage call path
- **B3** — session reports `completed` after every stage raises `AuthenticationError`
- **B4** — `stage_internal_node_changed.stage` field is empty on first stage, stale on subsequent stages

None of these were caught by ~645 existing tests because the test suite leans heavily on mocked LLM providers. Mocked tests can only assert that code paths are structurally reachable; they cannot assert that **the real system wires real model calls to real contracts**.

Plan 8 builds a **live-model, DFS-traversal, contract-based harness** that exercises every decision point in the pipeline against a real LLM, records what actually happened, and fails loudly on contract violations. The harness is also self-diagnostic: when it cannot steer the model via the production HITL channel, that failure is itself a finding (either the HITL point is missing or the model is not following directives).

## 2. Design summary

| Dimension | Decision |
|---|---|
| Reproducibility | **Live every run.** No mocks, no record/replay, no fixtures. Every `pytest -m live_harness` invocation hits the real provider. |
| Scope | **DFS tree traversal.** Every decision point in the pipeline spawns children for each branch; leaves are terminal states (complete/fail/max-iter). |
| Steering | **HITL-driven + context-shaping.** HITL checkpoints steered via production `/checkpoint/approve` HTTP endpoint. Non-HITL branches steered via context shaping (artifacts, priors, `max_iterations`). Un-steerable non-HITL branches are themselves a finding. |
| Pass/fail | **Contract-based.** Per-node input contracts (model received correct context) + output contracts (node emitted expected events / wrote expected state). Model output quality is observational, not asserted. |
| Error policy | **Retry 3× then halt + notify user.** No silent skip, no mock-fallback. |
| Bug discipline | **Halt-fix-retest-continue.** Any bug halts the DFS; fix inline, retest the path, resume. Final gate: one clean full run before plan-complete. |
| Surface | **Backend only.** Frontend explicitly out of scope for Plan 8. |

## 3. Decision-point taxonomy

Every DFS node corresponds to one of the following pipeline decision points:

| Level | Node | Branches | Steering channel |
|---|---|---|---|
| Subgraph | `gate` | skip / run | Context (prior-stage artifacts present/absent) |
| Subgraph | `evaluate` | iterate-again / done | Context (`max_stage_iterations`, items-done marks) |
| Subgraph | `decide` | needs_approval=true (HITL) / false | HITL (control_mode) |
| Stage | `transition_node` | default-seq / backtrack / PI-redirect / terminal | Context (evaluate output, backtrack budget, PI verdict) |
| PI advisor | verdict | approve / revise / replan | Context (failures, goals, prior verdicts) |
| HITL | `/checkpoint/approve` | approve / reject / redirect / edit | **HITL (direct HTTP)** |

**Traversal strategy.** DFS from root, pre-order. At each decision point the harness takes the first unexplored branch, recurses; on leaf, backtracks to nearest decision with unexplored branches; replays from root with new branch choices (fresh session per leaf — no resume-mid-path).

**Bounds.**
- `max_depth = 6` (prevents unbounded PI-revise-revise-revise chains; any DFS node exceeding depth is treated as a P0 unbounded-behavior finding)
- `max_leaves_per_root = 20` (soft advisory; run continues but warns)
- **No cost/token cap** — Plan 8 is best-effort system testing; budget gating is a future concern. Cost is recorded per path for visibility only.

## 4. Contract model (two dimensions per node)

Every harness contract has two parts:

### 4.1 Input contracts

**What must be true about the prompt/context the LLM receives at this node.** Verified by capturing the serialized prompt via the existing `agent_llm_request` event on the bus and asserting required fields are present, non-empty, and freshly-computed (not stale from a prior stage).

### 4.2 Output contracts

**What the node must do regardless of model output.** Verified by watching the WebSocket event stream + state snapshots + REST responses. Independent of LLM content.

### 4.3 Initial contract catalog

The following is the v1 catalog; the implementation plan expands each row into concrete assertion code. Additional contracts will be added as bugs surface during authoring.

| Node / component | Input contract | Output contract |
|---|---|---|
| `enter` | state has `current_stage == <name>` | emits `stage_internal_node_changed(node=enter, stage=<name>)` — non-empty and matches running stage (covers B4) |
| `stage_plan` | prompt contains stage goals + prior-stage summary | returns `StagePlan` with ≥1 item; emits `stage_plan_persisted`; plan items queryable via `/stage_plans/<stage>` |
| `gate` | context has bypass-markers from prior artifacts when applicable | returns bool cleanly; both branches reachable via context shaping |
| `work` | prompt contains all `plan.items`; correct agent resolved for this stage | emits ≥1 `agent_turn_started`/`agent_turn_finished`; no unhandled exception |
| `evaluate` | prompt sees `work` outputs + items-done marks | returns `needs_another_iteration: bool`; respects `max_stage_iterations` bound; never infinite-loops |
| `decide` | sees `control_mode`, iteration count, prior decisions | when `needs_approval=True`: `paused_event.clear()` called **and** `checkpoint_reached` event emitted with `control_mode` field (covers A2, C1) |
| `transition_node` | sees PI verdict if consulted + backtrack-budget + cursor | priority 1-6 resolution as specified in `platform-design.md §3.2.1`; **never silently resolves to `session.complete()` on `stage_failed`** (covers B3) |
| PI advisor | context contains all failures + goals + prior verdicts + relevant artifacts | emits `pi_agent_turn_*`; returns verdict ∈ {approve, revise, replan}; verdict and rationale persisted to `/pi/history` |
| `/checkpoint/approve` | payload schema validated; 409 when `executor is None` (A2) | applies action; unblocks `paused_event`; pipeline resumes |
| `/graph` endpoint | — | returns 200 after ≥1 stage transition (covers B1) |
| `resolve_agent` | `settings.llm.default_model` plumbed through `StageContext`; no hardcoded provider default (covers B2) | returns configured provider's agent; fails loudly (not silently) when model is unresolvable |

**Contract authoring pattern.** Each contract is a pure function `check(trace: HarnessTrace) -> ContractResult` where `HarnessTrace` is the harness's per-path record (events + state snapshots + HTTP responses + captured LLM prompts). Contracts live under `tests/harness/contracts/` in stage-focused modules; they are unit-testable independently of the DFS driver.

## 5. Bug severity taxonomy

Every contract violation surfaced by the harness is classified into one of four severities. Classification is proposed by the harness runner (based on which contract failed) and confirmed with the user.

| Severity | Category | Disposition |
|---|---|---|
| **P0 — blocker** | Deadlock, unbounded loop, unbounded resource growth, unbounded retry, non-terminating pipeline, DFS-depth exceeded | **Halt immediately. Fix before any further testing.** |
| **P1 — critical** | System feeds model wrong/missing context (plumbing bug, stale state, wrong closure, empty prompt field, misrouted config) | **Halt-fix-retest-continue.** System-side bug; model cannot be blamed. |
| **P2 — second critical** | Model receives correct context but fails to follow the directive it was given (ignores HITL redirect, skips plan item, hallucinates tool, refuses structured output) | **Halt-fix-retest-continue.** Usually prompt/agent-design fix. |
| **P3 — observational** | Model makes a defensible choice we didn't anticipate but that doesn't violate a contract | Recorded in trace; no halt, no fix. |

## 6. Error handling policy

| Outcome | Policy |
|---|---|
| API call succeeds | Record prompt+response+tokens+cost in trace; continue |
| API call fails (transient OR auth OR malformed) | Retry 3× with exponential backoff, 30s total cap; then **HALT + notify user** with provider/model/last-error. No silent skip. No mock fallback. |
| Model returned response but content malformed (JSON parse, schema violation) | Counts as contract violation (P1 or P2 depending on which contract); triggers halt-fix-retest |
| Contract violation (any severity) | Halt current DFS path; write partial trace; pause and report to user; after fix, retest the path; then resume DFS |
| Spec divergence during authoring | Stop; ask user fix-to-spec vs update-spec; proceed only after decision |

## 7. File layout

```
tests/harness/
├── __init__.py
├── conftest.py                       # live_harness marker, API-key skip, trace fixture
├── contracts/
│   ├── __init__.py
│   ├── base.py                       # Contract, ContractResult, HarnessTrace dataclasses
│   ├── stage_nodes.py                # enter/stage_plan/gate/work/evaluate/decide contracts
│   ├── transition.py                 # transition_node priority contracts
│   ├── pi_advisor.py                 # PI verdict + escalation contracts
│   ├── hitl.py                       # /checkpoint/approve + paused_event contracts
│   └── endpoints.py                  # /graph, /stage_plans, /cost, /pi/history contracts
├── harness/
│   ├── __init__.py
│   ├── runner.py                     # DFS driver: session bootstrap, WS subscribe, HTTP client
│   ├── steering.py                   # HITL directive generator + context-shape helpers
│   ├── capture.py                    # prompt/response capture via agent_llm_request event
│   └── trace.py                      # per-path record + JSON artifact writer
├── test_stage_literature_review.py   # module test — subgraph in isolation
├── test_stage_plan_formulation.py
├── test_stage_data_exploration.py
├── test_stage_data_preparation.py
├── test_stage_experimentation.py
├── test_stage_results_interpretation.py
├── test_stage_report_writing.py
├── test_stage_peer_review.py
├── test_stage_lab_meeting.py
├── test_transition_priorities.py     # 6-priority transition resolution
├── test_pi_advisor_verdicts.py       # approve/revise/replan paths
├── test_hitl_checkpoints.py          # full round-trip via real HTTP
└── test_full_pipeline_dfs.py         # full DFS root — runs after module tests pass
runs/                                  # git-ignored; created at first run
```

**Pytest config additions:**
- `live_harness` marker registered in `pyproject.toml`
- `conftest.py` auto-skips the marker unless both `AGENTLABX_LLM__DEFAULT_MODEL` and a provider API key env var are present

**Invocation:**
- `uv run pytest tests/harness -m live_harness` — full harness (module tests + DFS root)
- `uv run pytest tests/harness/test_stage_<name>.py -m live_harness` — single stage module

## 8. Entry points and layering

**Module tests run first.** Each stage subgraph is exercised in isolation via `StageSubgraphBuilder.compile(stage)` with a minimal state fixture. Both input and output contracts are asserted at every internal node. If any module test fails, the full-pipeline DFS test is skipped — no point traversing the tree when the building blocks don't hold.

**Full-pipeline DFS runs second.** `test_full_pipeline_dfs.py` boots the actual `PipelineExecutor`, opens a real WS connection to `/ws/sessions/{id}`, and drives the DFS traversal end-to-end. All contracts from §4.3 are checked at every node across every path.

## 9. Known-bug fix slots

Plan 8 reserves implementation slots for the four bugs found in the 2026-04-15 observation run. These are expected to be fixed *as their contracts surface during harness authoring* (not as a separate preliminary cleanup task):

| Bug | Location | Contract that will catch it |
|---|---|---|
| B1 — `/graph` 500 on `Transition.get` | `agentlabx/core/graph_mapper.py:98` | `/graph` endpoint output contract |
| B2 — hardcoded `claude-sonnet-4-6` in `resolve_agent` | `agentlabx/stages/_helpers.py:28`, `StageContext` | `resolve_agent` input contract (plumbed default_model) |
| B3 — session completes after all-stages-failed | `agentlabx/core/pipeline.py` run_pipeline completion | `transition_node` output contract |
| B4 — stale `stage_internal_node_changed.stage` | `agentlabx/stages/subgraph.py:45` closure over `stage.name` | `enter` output contract |

Additional bugs surfacing during implementation will be handled via the halt-fix-retest-continue discipline and added to the plan as new task slots.

## 10. Spec-alignment expectations

Plan 8 contracts reference `docs/superpowers/specs/2026-04-12-agentlabx-platform-design.md` — especially §3.2.1 (subgraph shape) and the transition-priority table. If a harness contract, once written, would contradict a published spec diagram or table, the implementer **stops** and asks the user whether to fix-to-spec or update-spec before proceeding. No silent drift.

## 11. Out of scope

- **Frontend tests.** UI already has its own suite; Plan 8 drives backend surfaces only (REST + WS + PipelineExecutor).
- **Nightly CI integration.** Plan 8 ships as opt-in local invocation. Once the harness proves stable, a follow-up plan can wire it into CI.
- **Record/replay caching.** User explicitly chose strictly-live; no fixtures.
- **Cost/budget gating.** Cost is recorded for visibility but not enforced.
- **Model-behavior benchmarking.** Plan 8 tests the *system around the model*, not the model's quality.

## 12. Deliverables

1. `tests/harness/` tree as laid out in §7, with all module tests + full DFS test
2. Contract catalog (§4.3) implemented as assertion functions
3. DFS runner with HITL steering + context-shape helpers + halt-fix-retest loop
4. JSON trace artifact format + example artifact checked into `tests/harness/examples/` after first clean run
5. Fixes for B1-B4 (and any additional bugs surfaced during authoring)
6. Updated `pyproject.toml` with `live_harness` marker
7. One clean full-DFS run from root (zero P0/P1/P2 violations) before plan-complete

## 13. Success criteria

Plan 8 is complete when:
- All module tests in `tests/harness/test_stage_*.py` pass under `-m live_harness` against real Gemini flash (or equivalent configured provider)
- `test_full_pipeline_dfs.py` completes one clean DFS traversal from root with zero P0/P1/P2 violations
- All four known bugs (B1-B4) are fixed and covered by harness contracts
- Any additional bugs surfaced during implementation have been fixed inline following halt-fix-retest-continue
- Trace artifact schema is stable and example artifact is committed
- No spec divergence remains unresolved
