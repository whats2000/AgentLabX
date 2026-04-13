"""Real results interpretation stage — postdoc + PhD dialogue updates hypothesis status."""

from __future__ import annotations

import json
import re

from agentlabx.core.event_types import EventTypes
from agentlabx.core.events import Event
from agentlabx.core.state import EvidenceLink, Hypothesis, PipelineState
from agentlabx.stages._helpers import build_agent_context, resolve_agent
from agentlabx.stages.base import BaseStage, StageContext, StageResult, sync_agent_memory_to_state


class ResultsInterpretationStage(BaseStage):
    name = "results_interpretation"
    description = "Postdoc and PhD interpret results and update hypothesis status."
    required_agents = ["postdoc", "phd_student"]
    required_tools = []

    async def run(self, state: PipelineState, context: StageContext) -> StageResult:
        registry = context.registry
        if registry is None:
            return StageResult(
                output={},
                status="backtrack",
                next_hint=None,
                reason="No registry in StageContext",
            )

        postdoc = resolve_agent(
            registry,
            "postdoc",
            llm_provider=context.llm_provider,
            cost_tracker=context.cost_tracker,
            state=state,
            event_bus=context.event_bus,
            storage=context.storage,
        )
        phd = resolve_agent(
            registry,
            "phd_student",
            llm_provider=context.llm_provider,
            cost_tracker=context.cost_tracker,
            state=state,
            event_bus=context.event_bus,
            storage=context.storage,
        )

        experiments = state.get("experiment_results", [])
        hypotheses = state.get("hypotheses", [])

        exp_summary = "\n".join(f"- {e.tag}: {e.metrics}" for e in experiments) or "(none)"
        hyp_summary = "\n".join(f"- {h.id}: {h.statement}" for h in hypotheses) or "(none)"

        # Step 1: Postdoc drafts
        interp_prompt = (
            f"Experiment results:\n{exp_summary}\n\nHypotheses:\n{hyp_summary}\n\n"
            f"Write a 200-word interpretation. For each hypothesis, state whether the "
            f"evidence supports, refutes, or is inconclusive. Cite specific metric values."
        )
        draft = await postdoc.inference(
            interp_prompt,
            build_agent_context(state, postdoc, phase="results_interpretation"),
        )

        # Step 2: PhD adds nuance
        phd_prompt = (
            f"Postdoc's interpretation:\n{draft}\n\n"
            f"Add 1-2 nuanced observations or caveats. Be concise."
        )
        phd_input = await phd.inference(
            phd_prompt,
            build_agent_context(state, phd, phase="results_interpretation"),
        )

        # Step 3: Postdoc finalizes + JSON hypothesis updates
        final_prompt = (
            f"Draft:\n{draft}\n\nPhD input:\n{phd_input}\n\n"
            f"Finalize interpretation AND emit hypothesis updates. Respond ONLY with JSON:\n"
            f'{{"interpretation": "200-word final text", '
            f'"hypothesis_updates": [{{"id": "H1", '
            f'"new_status": "supported|refuted|active|abandoned", '
            f'"evidence": [{{"experiment_result_index": 0, "metric": "accuracy", '
            f'"value": 0.78, "interpretation": "..."}}]}}]}}\n\nNo prose outside JSON.'
        )
        final_response = await postdoc.inference(
            final_prompt,
            build_agent_context(state, postdoc, phase="results_interpretation"),
        )
        parsed = _parse_json(final_response)

        interpretation_text = parsed.get("interpretation") or (draft + "\n" + phd_input)
        hypothesis_updates = parsed.get("hypothesis_updates", [])

        updated_hypotheses: list[Hypothesis] = []
        hyp_by_id = {h.id: h for h in hypotheses}
        for update in hypothesis_updates:
            hid = update.get("id")
            if hid not in hyp_by_id:
                continue
            original = hyp_by_id[hid]
            new_status = update.get("new_status", original.status)
            if new_status not in ("active", "supported", "refuted", "abandoned"):
                new_status = original.status
            evidence_records = update.get("evidence", [])
            evidence_links: list[EvidenceLink] = []
            for e in evidence_records:
                try:
                    evidence_links.append(
                        EvidenceLink(
                            experiment_result_index=int(e.get("experiment_result_index", 0)),
                            metric=str(e.get("metric", "")),
                            value=float(e.get("value", 0.0)),
                            interpretation=str(e.get("interpretation", "")),
                        )
                    )
                except (TypeError, ValueError):
                    continue

            updated_hyp = Hypothesis(
                id=original.id,
                statement=original.statement,
                status=new_status,
                evidence_for=(
                    list(original.evidence_for)
                    + (evidence_links if new_status == "supported" else [])
                ),
                evidence_against=(
                    list(original.evidence_against)
                    + (evidence_links if new_status == "refuted" else [])
                ),
                parent_hypothesis=original.parent_hypothesis,
                created_at_stage=original.created_at_stage,
                resolved_at_stage=("results_interpretation" if new_status != "active" else None),
            )
            updated_hypotheses.append(updated_hyp)

            if context.event_bus is not None:
                await context.event_bus.emit(
                    Event(
                        type=EventTypes.HYPOTHESIS_UPDATE,
                        data={
                            "hypothesis_id": hid,
                            "new_status": new_status,
                            "evidence_link": update.get("evidence"),
                        },
                        source="postdoc",
                    )
                )

        output: dict = {"interpretation": [interpretation_text]}
        if updated_hypotheses:
            output["hypotheses"] = updated_hypotheses

        sync_agent_memory_to_state(state, {"postdoc": postdoc, "phd_student": phd})
        return StageResult(
            output=output,
            status="done",
            reason=(f"Interpretation complete with {len(updated_hypotheses)} hypothesis updates"),
        )


def _parse_json(text: str) -> dict:
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if match:
        try:
            return json.loads(match.group(0))
        except json.JSONDecodeError:
            pass
    return {}
