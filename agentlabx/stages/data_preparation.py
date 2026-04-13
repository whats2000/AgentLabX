"""Real data preparation stage — ML/SW engineers collaborate on dataset pipeline."""

from __future__ import annotations

import json
import re
import tempfile
from pathlib import Path

from agentlabx.core.state import PipelineState
from agentlabx.stages._helpers import build_agent_context, resolve_agent, resolve_tool
from agentlabx.stages.base import BaseStage, StageContext, StageResult, sync_agent_memory_to_state


class DataPreparationStage(BaseStage):
    name = "data_preparation"
    zone = "implementation"
    description = "ML + SW engineers collaborate on data pipeline; validate via execution."
    required_agents = ["ml_engineer", "sw_engineer"]
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
            state=state,
            event_bus=context.event_bus,
            storage=context.storage,
        )
        sw = resolve_agent(
            registry,
            "sw_engineer",
            llm_provider=context.llm_provider,
            cost_tracker=context.cost_tracker,
            state=state,
            event_bus=context.event_bus,
            storage=context.storage,
        )
        code_executor = resolve_tool(
            registry, "code_executor", event_bus=context.event_bus, storage=context.storage
        )

        plan_list = state.get("plan", [])
        methodology = plan_list[-1].methodology if plan_list else "No plan"
        eda_list = state.get("data_exploration", [])
        eda_summary = "; ".join(eda_list[-1].recommendations) if eda_list else "No EDA yet"

        # Step 1: ML engineer describes requirements
        specs_prompt = (
            f"Plan methodology:\n{methodology}\n\nEDA recommendations:\n{eda_summary}\n\n"
            f"Describe the dataset shape and preprocessing steps you need for the "
            f"experimentation stage. Be specific (features, splits, batch format)."
        )
        specs = await ml.inference(
            specs_prompt,
            build_agent_context(state, ml, phase="data_preparation"),
        )

        # Step 2: SW writes the loader
        code_prompt = (
            f"ML engineer requirements:\n{specs}\n\n"
            f"Write a Python script that loads and preprocesses the dataset as specified. "
            f'Respond ONLY with JSON: {{"code": "..."}}. No prose.'
        )
        code_response = await sw.inference(
            code_prompt,
            build_agent_context(state, sw, phase="data_preparation"),
        )
        code = _parse_json(code_response).get("code", "")

        # Step 3: Execute to validate
        validation_passed = False
        stderr = ""
        if code:
            with tempfile.TemporaryDirectory() as tmpdir:
                exec_result = await code_executor.execute(
                    code=code,
                    workspace=str(Path(tmpdir)),
                    timeout=120,
                )
                validation_passed = exec_result.success
                if exec_result.data:
                    stderr = exec_result.data.get("stderr", "") or (exec_result.error or "")
                else:
                    stderr = exec_result.error or ""

        # Step 4: One debug attempt on failure
        if code and not validation_passed:
            debug_prompt = (
                f"The preprocessing script failed:\n\nStderr:\n{stderr[:500]}\n\n"
                f'Fix the code. Respond ONLY with JSON: {{"code": "..."}}'
            )
            debug_response = await sw.inference(
                debug_prompt,
                build_agent_context(state, sw, phase="data_preparation"),
            )
            fixed = _parse_json(debug_response).get("code", "")
            if fixed:
                code = fixed

        sync_agent_memory_to_state(state, {"ml_engineer": ml, "sw_engineer": sw})
        return StageResult(
            output={"dataset_code": [code] if code else []},
            status="done" if code else "backtrack",
            next_hint=None if code else "data_exploration",
            reason=(
                "Data preparation pipeline ready"
                if code
                else "Could not produce working data pipeline"
            ),
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
