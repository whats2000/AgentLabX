---
title: AgentLabX — Project Vision
status: active
authors: [whats2000, claude]
created: 2026-04-15
scope: north-star
---

# AgentLabX — Project Vision

## 1. What AgentLabX is

AgentLabX is an open research-automation platform.
A user defines a research topic; a team of LLM-powered agents takes it end-to-end — reviewing literature, forming a plan, preparing data, running experiments with baselines and ablations, interpreting results, writing a report, and critiquing it — with a principal-investigator agent overseeing strategic decisions.

It is a rewrite of `AgentLaboratory` focused on producing research that resembles real lab output rather than a prompt chain.
Every stage is a swappable module with a formal input/output contract, every tool is a standards-compliant MCP server, every credential is per-user and encrypted, and every step is observable.

## 2. Why a rewrite

The prior implementation mixed identity, secrets, pipeline state, stage logic, and tool integration in a single tangled object graph. Stages bulk-processed without curation; backtracks wiped accumulated knowledge; `.env`-scoped API keys made multi-user impossible; and there was no contract telling a stage what it should produce.
The platform ran but did not function — passing mechanical checks while producing empty or hallucinated artifacts.

AgentLabX starts over with strict boundaries so that the failure modes above become structurally impossible: a stage that produces nothing cannot be declared "done," a tool that wasn't actually called cannot be claimed as used, and a secret that belongs to one user cannot leak across sessions.

## 3. What AgentLabX ships

**A user-facing desktop app** (local-first, browser UI) that takes a research question and returns a full, reproducible research artifact: literature survey with curated references, a research plan, executed experiments with baselines and ablations, interpretation, written report, and peer review — all editable and rerunnable at any point.

**A foundation layer** that any researcher or builder can host locally:
- Per-user identity (default single-user + pluggable OAuth / token authers).
- Encrypted secret storage tied to OS keyring.
- Standards-compliant tool integration (MCP) — bring your own tools, or use bundled ones.
- Observable event stream for every agent turn, tool call, transition, and PI decision.

**A stage-plug-in model** where each research stage (literature review, plan formulation, experimentation, …) declares:
- What state it reads.
- What state it writes.
- What tools it requires.
- What makes the stage genuinely "done" (testable completion criteria).

Multiple implementations of each stage can coexist — a simple baseline, a curated multi-turn version, a wrapper around a reference implementation — letting users compare method quality head-to-head on the same task.

**A rule-based traffic engine** for moving between stages: forward-by-default, honours stage-level "I need to go back" requests, applies partial rollback that preserves prior work, consults a PI agent at strategic checkpoints, and stops loops with per-edge retry governance.

**A reproducibility contract** on every experiment artifact: seed, environment hash, dependency snapshot, run command, container image, and git ref. Any result can be reproduced or compared across runs.

## 4. Principles

- **Isolation over integration.** Modules talk through narrow typed interfaces. A module's inputs and outputs are the whole contract; internals are free to change.
- **Contracts over conventions.** Every stage declares its I/O schema and completion criteria. Tests verify the contract; implementations are swappable behind it.
- **Deterministic types are mandatory in main code.** `typing.Any` is disallowed. **`object` is also disallowed** — it accepts every value, exposes no discoverable interface, and is `Any` with a different name. Use a `Protocol`, a `TypedDict`, a Pydantic model, or a concrete type / union — never a placeholder that erases information.
  Past experience: undeterministic types caused runtime errors that surfaced far from their declaration site, dominating debug time. The rule is enforced by ruff (`ANN` rule family, including `ANN401`) and applies to test code as well as production code.
  Frontend (TypeScript) carries the equivalent rule via `strict: true` + `noImplicitAny: true`; `any` and `unknown` (without narrowing) are treated identically to Python `Any`.
- **Real work, real verification.** A harness exercises the platform against real models and asserts that artifacts are semantically correct (not just that events fired). If it works but doesn't function, the harness calls it a failure.
- **User sovereignty.** Credentials are the user's. They live encrypted under the user's OS keyring, never in env files or config repositories, never process-global.
- **Incremental build-up.** The platform is assembled one stage at a time, each with its own spec, plan, and review cycle. No monolithic mega-plan. Plans declare the **contract** (what to build); subagent execution writes the code (how to build it). The two stay separate.
- **Observable over opaque.** Every agent turn, tool call, transition, and PI decision is visible in a structured event stream usable by both humans and automated test harnesses.

## 5. What AgentLabX does not ship

- Multi-tenant hosted SaaS. The architecture does not prevent it, but the product shape is local-first, single-user-per-install.
- Opaque "magic" pipelines. Every stage transition and agent decision is inspectable and overridable.
- Hardcoded provider choice. LLM providers, execution backends, storage backends, and tools are all pluggable; users choose at runtime.
- A one-click research button that replaces judgement. The user remains in the loop — approving zone transitions, editing outputs, adjusting hypotheses. Automation accelerates the researcher, not replaces them.

## 6. Success, in one sentence

AgentLabX succeeds when a researcher can paste a novel question, watch agents execute a real research workflow end-to-end with full observability, intervene at any checkpoint, compare alternative stage implementations on the same question, and hand the produced artifact (paper, code, results, references) to a peer who can reproduce every number it contains.
