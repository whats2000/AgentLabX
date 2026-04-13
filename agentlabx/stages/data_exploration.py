"""Real data exploration stage — SW engineer runs EDA via code_executor."""

from __future__ import annotations

import json
import re
import tempfile
from pathlib import Path

from agentlabx.core.state import EDAResult, PipelineState
from agentlabx.stages._helpers import build_agent_context, resolve_agent, resolve_tool
from agentlabx.stages.base import BaseStage, StageContext, StageResult, sync_agent_memory_to_state

EDA_SCRIPT_JSON_FORMAT = (
    '{"code": "Python script that loads a dataset and prints shape/schema/stats", '
    '"expected_outputs": ["what the script should print"]}'
)


class DataExplorationStage(BaseStage):
    name = "data_exploration"
    description = "SW engineer runs exploratory data analysis via code executor."
    required_agents = ["sw_engineer"]
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

        sw = resolve_agent(
            registry,
            "sw_engineer",
            llm_provider=context.llm_provider,
            cost_tracker=context.cost_tracker,
            state=state,
        )
        code_executor = resolve_tool(registry, "code_executor", event_bus=context.event_bus, storage=context.storage)

        plan_list = state.get("plan", [])
        plan_summary = plan_list[-1].methodology if plan_list else "No plan yet"
        topic = state["research_topic"]

        # Step 1: SW engineer drafts EDA script
        eda_prompt = (
            f"Topic: {topic}\n\nPlan methodology:\n{plan_summary}\n\n"
            f"Write a short Python script that performs exploratory data analysis. "
            f"The script should print dataset shape, first few rows, and basic stats. "
            f"Respond ONLY with JSON:\n{EDA_SCRIPT_JSON_FORMAT}\n\nNo prose outside the JSON."
        )
        eda_response = await sw.inference(
            eda_prompt,
            build_agent_context(state, sw, phase="data_exploration"),
        )
        parsed = _parse_json(eda_response)
        code = parsed.get("code", "")

        # Step 2: Execute
        exec_result = None
        stdout = ""
        stderr = ""
        if code:
            with tempfile.TemporaryDirectory() as tmpdir:
                exec_result = await code_executor.execute(
                    code=code,
                    workspace=str(Path(tmpdir)),
                    timeout=60,
                )
            if exec_result.success:
                stdout = exec_result.data.get("stdout", "")
            else:
                stderr = exec_result.error or ""
                if exec_result.data:
                    stderr = exec_result.data.get("stderr", stderr)

        # Step 3: SW engineer synthesizes findings
        findings_prompt = (
            f"EDA script output:\n\nSTDOUT:\n{stdout[:2000]}\n\n"
            f"STDERR:\n{stderr[:500]}\n\n"
            f"Summarize findings. Respond ONLY with JSON:\n"
            f'{{"findings": ["finding 1", ...], '
            f'"data_quality_issues": ["issue 1", ...], '
            f'"recommendations": ["rec 1", ...]}}\n\nNo prose outside the JSON.'
        )
        findings_response = await sw.inference(
            findings_prompt,
            build_agent_context(state, sw, phase="data_exploration"),
        )
        findings_parsed = _parse_json(findings_response)

        eda = EDAResult(
            findings=findings_parsed.get("findings", []) or ["EDA completed"],
            data_quality_issues=findings_parsed.get("data_quality_issues", []) or [],
            recommendations=findings_parsed.get("recommendations", []) or [],
        )

        sync_agent_memory_to_state(state, {"sw_engineer": sw})
        return StageResult(
            output={"data_exploration": [eda]},
            status="done",
            reason=f"Data exploration complete. {len(eda.findings)} findings.",
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
