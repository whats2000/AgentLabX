"""Real experimentation stage — baseline, main, ablations with enforced validation."""

from __future__ import annotations

import json
import re
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

from agentlabx.core.state import ExperimentResult, PipelineState, ReproducibilityRecord
from agentlabx.stages._helpers import build_agent_context, resolve_agent, resolve_tool
from agentlabx.stages.base import BaseStage, StageContext, StageResult


class ExperimentationStage(BaseStage):
    name = "experimentation"
    description = "ML engineer runs baseline/main/ablation experiments with validation."
    required_agents = ["ml_engineer"]
    required_tools = ["code_executor"]

    async def run(self, state: PipelineState, context: StageContext) -> StageResult:
        registry = context.registry
        if registry is None:
            return StageResult(
                output={},
                status="backtrack",
                next_hint=None,
                reason="No registry in StageContext",
            )

        ml = resolve_agent(
            registry,
            "ml_engineer",
            llm_provider=context.llm_provider,
            cost_tracker=context.cost_tracker,
        )
        code_executor = resolve_tool(registry, "code_executor")

        plan_list = state.get("plan", [])
        hypotheses = state.get("hypotheses", [])
        methodology = plan_list[-1].methodology if plan_list else "No plan"

        results: list[ExperimentResult] = []

        for tier in ("baseline", "main", "ablation"):
            prompt = self._build_experiment_prompt(tier, methodology, hypotheses, results)
            response = await ml.inference(
                prompt,
                build_agent_context(state, ml, phase="experimentation"),
            )
            parsed = _parse_json(response)
            code = parsed.get("code", "")
            if not code:
                continue

            with tempfile.TemporaryDirectory() as tmpdir:
                exec_result = await code_executor.execute(
                    code=code,
                    workspace=str(Path(tmpdir)),
                    timeout=180,
                    seed=42,
                )
                if not exec_result.success:
                    continue

                stdout = exec_result.data.get("stdout", "") if exec_result.data else ""
                metrics = _extract_metrics(stdout) or parsed.get("metrics", {})

                # Cast metrics values to float defensively
                clean_metrics: dict[str, float] = {}
                for k, v in metrics.items():
                    try:
                        clean_metrics[str(k)] = float(v)
                    except (TypeError, ValueError):
                        continue

                repro_data = exec_result.data.get("reproducibility") if exec_result.data else None
                if repro_data:
                    try:
                        repro_record = ReproducibilityRecord(**repro_data)
                    except Exception:
                        repro_record = ReproducibilityRecord(
                            random_seed=42,
                            environment_hash="",
                            run_command="",
                            timestamp=datetime.now(UTC),
                        )
                else:
                    repro_record = ReproducibilityRecord(
                        random_seed=42,
                        environment_hash="",
                        run_command="",
                        timestamp=datetime.now(UTC),
                    )

                result = ExperimentResult(
                    tag=tier,  # type: ignore[arg-type]
                    metrics=clean_metrics,
                    description=parsed.get("description", f"{tier} experiment"),
                    reproducibility=repro_record,
                )
                results.append(result)

            # Skip ablation if main didn't show improvement
            if tier == "main" and not _has_positive_improvement(results):
                break

        has_baseline = any(r.tag == "baseline" for r in results)
        has_main = any(r.tag == "main" for r in results)
        has_ablation = any(r.tag == "ablation" for r in results)

        # Spec §3.6 validation
        if not has_baseline:
            return StageResult(
                output={"experiment_results": results},
                status="backtrack",
                next_hint="plan_formulation",
                reason="Experimentation requires at least one baseline result",
            )

        if has_main and _has_positive_improvement(results) and not has_ablation:
            return StageResult(
                output={"experiment_results": results},
                status="backtrack",
                next_hint="experimentation",
                reason="Positive main result requires at least one ablation study",
            )

        if has_main and not _has_positive_improvement(results):
            return StageResult(
                output={"experiment_results": results},
                status="negative_result",
                reason="Experiments did not show significant improvement over baseline",
            )

        return StageResult(
            output={"experiment_results": results},
            status="done",
            reason=f"Experimentation complete: {len(results)} runs",
        )

    def _build_experiment_prompt(
        self,
        tier: Literal["baseline", "main", "ablation"],
        methodology: str,
        hypotheses: list,
        prior_results: list,
    ) -> str:
        prior_summary = "\n".join(f"- {r.tag}: {r.metrics}" for r in prior_results) or "(none yet)"
        hyp_summary = "\n".join(f"- {h.statement}" for h in hypotheses[:3]) or "(no hypotheses)"
        tier_goal = {
            "baseline": "Establish baseline performance without any new techniques.",
            "main": "Test the main hypothesis against the baseline.",
            "ablation": "Ablate one component at a time to understand contributions.",
        }[tier]
        return (
            f"Methodology: {methodology}\n\nHypotheses:\n{hyp_summary}\n\n"
            f"Prior results:\n{prior_summary}\n\n"
            f"Current tier: {tier}. {tier_goal}\n\n"
            f"Write a short Python script that runs this experiment. "
            f"The script MUST print a JSON line like "
            f'`{{"metrics": {{"accuracy": 0.75, "f1": 0.72}}}}` as its final line.\n\n'
            f"Respond ONLY with JSON:\n"
            f'{{"code": "...", "description": "...", "metrics": {{}}}}\n\nNo prose.'
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


def _extract_metrics(stdout: str) -> dict:
    """Find the last {"metrics": {...}} line in stdout."""
    for line in reversed(stdout.strip().split("\n")):
        line = line.strip()
        if line.startswith("{") and "metrics" in line:
            try:
                parsed = json.loads(line)
                return parsed.get("metrics", {})
            except json.JSONDecodeError:
                continue
    return {}


def _has_positive_improvement(results: list) -> bool:
    """Check if main result shows improvement over baseline."""
    baselines = [r for r in results if r.tag == "baseline"]
    mains = [r for r in results if r.tag == "main"]
    if not baselines or not mains:
        return False
    for metric in mains[-1].metrics:
        if metric in baselines[-1].metrics:
            if mains[-1].metrics[metric] > baselines[-1].metrics[metric]:
                return True
    return False
