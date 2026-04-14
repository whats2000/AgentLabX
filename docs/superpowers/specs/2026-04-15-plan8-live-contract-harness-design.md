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
| Scope | **DFS coverage enumeration.** I walk the pipeline's decision tree in DFS order as a *planning* exercise to enumerate every distinct path; each enumerated path becomes one explicit deterministic test. No runtime tree-traversal engine — the harness is a flat set of tests, structured by DFS-enumerated scenarios. |
| Steering | **HITL-driven + context-shaping, per-test deterministic.** Each test sets up exactly the state/context needed to exercise its target path. HITL checkpoints steered via production `/checkpoint/approve` HTTP endpoint. Non-HITL branches steered via context shaping (artifacts, priors, `max_iterations`). Un-steerable non-HITL branches are themselves a finding. |
| Pass/fail | **Contract-based.** Per-node input contracts (model received correct context) + output contracts (node emitted expected events / wrote expected state). Model output quality is observational, not asserted. |
| Error policy | **Retry 3× then halt + notify user.** No silent skip, no mock-fallback. |
| Bug discipline | **Halt-fix-retest-continue.** Easy mechanical bugs auto-patched inline (plumbing, missing state pass-through, attribute access, closure capture); architectural bugs (tool-capability gaps, design changes, spec divergence) escalated to user. Final gate: one clean full run before plan-complete. |
| Execution order | **Station-by-station first, then full DFS.** Each stage validated green in order (with prior-station output feeding next-station input) before advancing. Full-path DFS runs only after every station is green. |
| Surface | **Backend only.** Frontend explicitly out of scope for Plan 8. |

## 3. Decision-point taxonomy and coverage enumeration

### 3.1 Decision points

Every branching point in the pipeline is one of the following. Each decision × branch becomes a cell that must be covered by at least one test.

| Level | Node | Branches | Steering channel |
|---|---|---|---|
| Subgraph | `gate` | skip / run | Context (prior-stage artifacts present/absent) |
| Subgraph | `evaluate` | iterate-again / done | Context (`max_stage_iterations`, items-done marks) |
| Subgraph | `decide` | needs_approval=true (HITL) / false | HITL (control_mode) |
| Stage | `transition_node` | default-seq / backtrack / PI-redirect / terminal | Context (evaluate output, backtrack budget, PI verdict) |
| PI advisor | verdict | approve / revise / replan | Context (failures, goals, prior verdicts) |
| HITL | `/checkpoint/approve` | approve / reject / redirect / edit | **HITL (direct HTTP)** |

### 3.2 DFS enumeration (planning-time, not runtime)

Before writing any test, the implementer walks the decision tree above in **depth-first pre-order** to enumerate distinct paths:

1. Start at `literature_review.enter`.
2. At each decision point, visit branch 0 first; recurse into its subtree.
3. When a branch subtree is fully enumerated, back up and visit branch 1; recurse.
4. A leaf is a terminal state (`session.complete`, `session.fail`, `max_total_iterations`, `max_stage_iterations`, unrecoverable contract violation).

The output of this walk is a **static list of path descriptors**, e.g.:

- `P001: lit_review(gate=run, eval=done, decide=no-approval) → plan_form(gate=run, eval=done, decide=no-approval) → ... → peer_review → complete`
- `P017: lit_review(...) → plan_form(eval=iterate-again×1, done) → ... backtrack to data_exploration → ...`
- `P023: lit_review(...) → PI consulted (verdict=replan) → redirect to plan_form → ...`

Each path descriptor becomes **one concrete test function** in `tests/harness/` with hand-written context shaping + HITL directives that deterministically drive that exact path. **The harness does not discover paths at runtime** — it verifies the paths the implementer enumerated during planning.

### 3.3 Enumeration bounds

- `max_depth = 6` decision points per path (any enumerated path exceeding this is pruned during planning and flagged as a P0 unbounded-behavior concern for the code under test)
- Not every combinatorial path is enumerated — the implementer applies judgment (e.g. `evaluate=iterate-again` explored up to 2 iterations, not exhaustively; PI `revise` verdict explored once per stage, not recursively). The planning rationale for which paths are dropped is documented alongside the path list in the implementation plan.
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

**Contract authoring pattern.** Each contract is a pure function `check(trace: HarnessTrace) -> ContractResult` where `HarnessTrace` is the per-test record (events + state snapshots + HTTP responses + captured LLM prompts). Contracts live under `tests/harness/contracts/` in stage-focused modules; they are unit-testable independently of any individual test, reused by both the spine test and fork tests.

## 5. Bug severity taxonomy

Every contract violation surfaced by the harness is classified into one of four severities. Classification is proposed by the harness runner (based on which contract failed) and the implementer decides auto-patch vs escalate per §5.1.

| Severity | Category | Disposition |
|---|---|---|
| **P0 — blocker** | Deadlock, unbounded loop, unbounded resource growth, unbounded retry, non-terminating pipeline, DFS-depth exceeded | **Halt immediately.** Auto-patch if mechanical; escalate if architectural. |
| **P1 — critical** | System feeds model wrong/missing context (plumbing bug, stale state, wrong closure, empty prompt field, misrouted config) | **Halt-fix-retest-continue.** System-side bug; auto-patch if mechanical; escalate if architectural. |
| **P2 — second critical** | Model receives correct context but fails to follow the directive it was given (ignores HITL redirect, skips plan item, hallucinates tool, refuses structured output) | **Halt-fix-retest-continue.** Usually prompt/agent-design fix; escalate if the agent/tool itself is architecturally underspecified. |
| **P3 — observational** | Model makes a defensible choice we didn't anticipate but that doesn't violate a contract | Recorded in trace; no halt, no fix. |

### 5.1 Auto-patch vs escalate

Not every bug requires user notification. Classify each finding along a second axis and act accordingly:

| Fix class | Examples | Action |
|---|---|---|
| **Auto-patch (mechanical)** | Missing state pass-through (e.g. `StageContext` field not populated), wrong attribute access (`dict.get` vs Pydantic `.attr`), stale closure capture, hardcoded default where config should flow, missing event emission, misrouted prompt field, forgotten `await`, schema field typo | Implementer fixes inline, retests failing path/station, continues. Reports the fix in the station summary at the end. No interruption. |
| **Escalate to user** | Tool's capability is insufficient for what the contract requires (new feature or redesign); agent's method/prompt structure needs architectural change (not just wording); spec divergence between code and `platform-design.md`; multiple contracts failing from one root cause where fix direction is unclear; fix would touch public API or cross-module boundary; any P0 where the root cause isn't obvious | Implementer halts, reports finding with root-cause hypothesis and 2-3 proposed directions, awaits user decision before proceeding. |

When in doubt, escalate. A 30-second user check is cheaper than a wrong architectural patch that needs revisiting later.

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
│   ├── session.py                    # session bootstrap, WS subscribe, HTTP client
│   ├── steering.py                   # HITL directive helpers + context-shape helpers
│   ├── capture.py                    # prompt/response capture via agent_llm_request event
│   ├── snapshots.py                  # StateSnapshot capture + replay helpers (spine handoff)
│   └── trace.py                      # per-test trace record + JSON artifact writer
├── test_spine.py                     # Phase 1 — end-to-end happy-path spine, captures snapshots
├── test_stage_literature_review.py   # standalone module test (dev aid)
├── test_stage_plan_formulation.py    # standalone module test (dev aid)
├── test_stage_data_exploration.py    # standalone module test (dev aid)
├── test_stage_data_preparation.py    # standalone module test (dev aid)
├── test_stage_experimentation.py     # standalone module test (dev aid)
├── test_stage_results_interpretation.py # standalone module test (dev aid)
├── test_stage_report_writing.py      # standalone module test (dev aid)
├── test_stage_peer_review.py         # standalone module test (dev aid)
├── test_stage_lab_meeting.py         # standalone module test (dev aid)
├── forks/                             # Phase 2 — one file per decision-node family
│   ├── __init__.py
│   ├── test_fork_gate.py             # gate=skip forks from each station's snapshot
│   ├── test_fork_evaluate.py         # evaluate=iterate-again forks
│   ├── test_fork_decide_hitl.py      # decide=needs_approval forks, HITL round-trip
│   ├── test_fork_transition.py       # backtrack + terminal forks
│   └── test_fork_pi_advisor.py       # PI revise + replan forks
└── runs/                              # git-ignored; trace artifacts + spine snapshots
```

**Pytest config additions:**
- `live_harness` marker registered in `pyproject.toml`
- `conftest.py` auto-skips the marker unless both `AGENTLABX_LLM__DEFAULT_MODEL` and a provider API key env var are present
- Phase 2 fork tests declare dependency on `test_spine.py` so they skip (with clear message) if the spine is not green

**Invocation:**
- `uv run pytest tests/harness/test_spine.py -m live_harness` — Phase 1 only (spine build + validate)
- `uv run pytest tests/harness/forks -m live_harness` — Phase 2 only (requires snapshots from Phase 1)
- `uv run pytest tests/harness -m live_harness` — full run (spine + all forks)
- `uv run pytest tests/harness/test_stage_<name>.py -m live_harness` — single-stage development aid (§8.3)

## 8. Execution order: spine-first, then alternate-branch forks

Plan 8 runs in **two phases**. Phase 1 builds and validates a single happy-path spine through every station, chained with correct state flow. Phase 2 adds alternate-branch tests that fork off the validated spine at specific decision points. If the spine stations are correctly wired with realistic state, each alternate-branch test automatically reflects real-system behavior — no synthetic state required.

### 8.1 Phase 1 — Happy-path spine

The spine is a single end-to-end default-path run through every station in pipeline order, validated station-by-station:

**Station order (spine):**
1. `literature_review` (gate=run, evaluate=done, decide=no-approval)
2. `plan_formulation` (same default branches) → triggers `lab_meeting` interstitial
3. `data_exploration`
4. `data_preparation`
5. `experimentation`
6. `results_interpretation`
7. `report_writing`
8. `peer_review` → `session.complete`

Each station in the spine is exercised sequentially. When a station runs, it receives the **real prior-station output** already persisted in state (not a synthetic fixture). The harness asserts both input contracts (context to the model) and output contracts (events + state + REST) at each station. If any contract fails, the spine halts; the bug is classified (§5.1) and either auto-patched or escalated; once fixed, the spine resumes from the last-known-green station.

**Spine completion gate.** Phase 2 does not begin until the entire spine is green end-to-end with zero unfixed contract violations. Cumulative failures/PI-consultations observed during the spine feed naturally into Phase 2's PI-verdict coverage.

**State snapshotting.** As the spine runs, a `StateSnapshot` is captured at each station boundary (after the station's `transition_node` resolves). Snapshots preserve the full shared state (artifacts, `stage_plans`, transition log, cursor, cost tally) and are keyed by station name. Snapshots are the handoff artifact consumed by Phase 2.

### 8.2 Phase 2 — Alternate-branch fork tests

With the spine validated and snapshots captured, Phase 2 covers every enumerated alternate branch (§3.2) as an individual test. Each test:

1. **Loads the spine snapshot** taken just before the station where the fork happens.
2. **Shapes context or issues a HITL directive** (§3.1 steering column) to push the model toward the target non-default branch.
3. **Runs the station** (and any downstream stations the fork reaches before terminating or reaching a stable point).
4. **Asserts the target path's contracts.**

Because upstream state comes from a real spine run, not a hand-crafted fixture, each fork test exercises the exact same wiring the production pipeline would experience at that state. Bugs that only surface under realistic state composition are catchable this way and not otherwise.

**Fork coverage examples:**
- `F001`: fork at `experimentation.evaluate` — shape context to force `iterate-again`; assert no infinite loop, `max_stage_iterations` respected, second iteration's prompt contains items-done marks from first iteration
- `F012`: fork at `plan_formulation.transition_node` — shape context to trigger backtrack to `literature_review`; assert backtrack budget decremented, cursor updated, PI consulted on second backtrack
- `F023`: fork at `report_writing.decide` — force `needs_approval=True`; HITL-redirect via `/checkpoint/approve`; assert pipeline pauses, directive applied, resumes correctly

The full fork list is enumerated during the writing-plans step (§3.2 DFS walk) and becomes individual tasks.

### 8.3 Module-level standalone tests (development aid)

In parallel with phases 1 and 2, each stage also has a standalone module test that exercises its subgraph in isolation via `StageSubgraphBuilder.compile(stage)` with a minimal state fixture. These are a **development convenience** — fast iteration when authoring contracts for a single subgraph, without running the full spine each time. They are *not* authoritative: if a module test passes but the corresponding spine-phase test fails, the spine-phase test wins (its state is realistic; the module fixture may have hidden the bug).

Invoked with `uv run pytest tests/harness/test_stage_<name>.py -m live_harness`.

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

1. `tests/harness/` tree as laid out in §7 — contracts module, harness helpers, spine test, per-stage module tests, fork tests
2. Contract catalog (§4.3) implemented as assertion functions under `tests/harness/contracts/`
3. Phase 1 spine test (`test_spine.py`) that runs every station in order with real state chaining, asserts all station contracts, and captures per-station snapshots to `runs/`
4. Phase 2 fork test suite (`tests/harness/forks/`) covering the enumerated alternate branches from §3.2, each fork test starting from the appropriate spine snapshot
5. Steering helpers: HITL directive generator (wraps production `/checkpoint/approve` HTTP client) + context-shaping helpers for non-HITL branches
6. JSON trace artifact format + example artifact committed under `tests/harness/examples/` after first clean spine run
7. Fixes for B1-B4 (inline during contract authoring) and any additional bugs surfaced during implementation
8. Updated `pyproject.toml` with `live_harness` marker + fork-depends-on-spine skip behavior

## 13. Success criteria

Plan 8 is complete when:
- `test_spine.py` passes under `-m live_harness` against real Gemini flash (or equivalent configured provider) — every station green, all station-boundary snapshots captured
- Every enumerated fork test under `tests/harness/forks/` passes with zero P0/P1/P2 violations
- Per-stage standalone module tests pass as a development aid
- All four known bugs (B1-B4) are fixed and covered by harness contracts
- Any additional bugs surfaced during implementation have been fixed inline following halt-fix-retest-continue (auto-patched if mechanical, escalated if architectural per §5.1)
- Trace artifact schema is stable and example artifact is committed
- No spec divergence remains unresolved
