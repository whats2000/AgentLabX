# Plan 6: Observability — Design Companion (Historical, Merged)

**Date:** 2026-04-13
**Status:** Superseded — content merged into the main platform spec.
**See:** `docs/superpowers/specs/2026-04-12-agentlabx-platform-design.md`

Plan 6 shipped on 2026-04-13 (tag `plan6-complete`, commit `2585217`). All binding design content from this companion is now in the main platform spec:

| Original section | Now lives in |
|---|---|
| §2.1–§2.2 PipelineState keys + observability TypedDicts | main spec §3.4, §3.5.1 |
| §2.3 Working memory mechanism | main spec §4.3 |
| §2.4 New REST endpoints | main spec §7.1 |
| §2.5 Event taxonomy | main spec §7.2 |
| §2.6 Layout + component list | main spec §8.2, §8.3 |
| §3.1 `agent_turns` schema + indexes | main spec §9.3 |
| §3.2 `TurnContext` correlation mechanism | main spec §4.4 |
| §3.2.1 PI observability split | main spec §4.4 |
| §3.4 Graph topology mapper shape | main spec §4.4 |

The Plan 6 implementation plans (`2026-04-13-plan6a-data-plane.md`, `2026-04-13-plan6b-events-endpoints.md`, `2026-04-13-plan6c-frontend.md`) remain as-is for historical record. Their `Companion spec:` pointers now resolve to this redirect.

Rationale, open questions, and out-of-scope notes from the original design are preserved in the git history of this file (`git log --follow` it).
