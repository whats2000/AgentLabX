"""Base stage contract for pipeline stages."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Any, ClassVar, Literal

from pydantic import BaseModel

from agentlabx.core.state import CrossStageRequest, PipelineState, StagePlan, StagePlanItem
from agentlabx.core.zones import ZoneName

if TYPE_CHECKING:
    from agentlabx.agents.base import BaseAgent


def sync_agent_memory_to_state(state: dict, agents: dict[str, BaseAgent]) -> None:
    """Write each dirty agent's snapshot into state[agent_memory][name]. Clears dirty flags.

    Args:
        state: The pipeline state dict to update.
        agents: A dict mapping agent names to BaseAgent instances.
    """
    # INVARIANT (2026-04-13, Plan 6A): this helper mutates state["agent_memory"]
    # in place. PipelineState declares `agent_memory: dict[str, AgentMemoryRecord]`
    # WITHOUT an `Annotated[..., reducer]` wrapper, so LangGraph's default
    # behavior is whole-value overwrite — NOT dict merge. The current pipeline
    # is safe only because (1) stages run sequentially and (2) every stage calls
    # this helper which setdefault's the live dict before mutating.
    #
    # DO NOT refactor this helper to build a fresh dict and return it, OR return
    # `{"agent_memory": memory}` as a partial state update from a stage — either
    # change will silently wipe entries for agents that didn't run in this stage.
    #
    # If Plan 6B/7 introduces event-driven paths that return partial state dicts,
    # switch PipelineState.agent_memory to `Annotated[dict, _merge_agent_memory]`
    # with a proper dict-merge reducer BEFORE relying on partial updates.
    memory = state.setdefault("agent_memory", {})
    for name, agent in agents.items():
        if getattr(agent, "dirty", False):
            memory[name] = agent.snapshot_memory()
            agent.dirty = False


class StageContext(BaseModel):
    """Runtime context passed to every stage.

    Stages receive this with all the infrastructure they need.

    Fields:
    - registry: PluginRegistry for resolving agents and tools
    - event_bus: EventBus for emitting progress events
    - settings: Application settings
    - llm_provider: BaseLLMProvider instance — stages pass this to agents
      when instantiating them. None → agents run in mock mode (Plan 2 default).
    - cost_tracker: Shared CostTracker accumulated across agent calls.
      None → no cost accumulation. PipelineBuilder wires this to the session's
      state["cost_tracker"] so budget policies can see live spend.
    - paused_event: asyncio.Event — set=running, cleared=paused. StageRunner
      awaits this between on_enter and stage.run for cooperative pause.
      None = no pause support (default).
    - model: LLM model identifier to use for all agents in this stage context.
      Sourced from session config_overrides["llm"]["default_model"] or
      AppSettings().llm.default_model. None → ConfigAgent uses its own default
      (Plan 8 B2 fix — prevents hardcoded Anthropic fallback when Gemini is
      configured via AGENTLABX_LLM__DEFAULT_MODEL env var).
    """

    settings: Any = None
    event_bus: Any = None
    storage: Any = None
    registry: Any = None
    llm_provider: Any = None
    cost_tracker: Any = None
    paused_event: Any = None
    model: str | None = None
    model_config = {"arbitrary_types_allowed": True}


class StageResult(BaseModel):
    output: Any
    status: Literal["done", "backtrack", "negative_result", "request"]
    next_hint: str | None = None
    reason: str
    feedback: str | None = None
    requests: list[CrossStageRequest] | None = None


class StageExecution(BaseModel):
    """Intermediate result of the `execute_plan` hook — fed to `evaluate`.

    Shape matches StageResult but `evaluate` may override before `decide`.
    """
    output: Any
    status: Literal["done", "backtrack", "negative_result", "request"]
    reason: str
    feedback: str | None = None
    next_hint: str | None = None
    requests: list[CrossStageRequest] | None = None


class StageEvaluation(BaseModel):
    """Evaluate-hook output. Overrides take precedence in decide()."""
    dead_end: bool = False
    override_status: Literal["done", "backtrack", "negative_result", "request"] | None = None
    override_next_hint: str | None = None
    override_reason: str | None = None
    notes: list[str] = []


class BaseStage(ABC):
    name: str
    description: str
    required_agents: list[str]
    required_tools: list[str]
    zone: ClassVar[ZoneName | None] = None
    invocable_only: ClassVar[bool] = False  # True = callable subgraph, excluded from top-level wiring

    @abstractmethod
    async def run(self, state: PipelineState, context: StageContext) -> StageResult: ...

    # ── Subgraph hooks (Plan 7B) ─────────────────────────────────────────
    # Override these for plan-driven behaviour. Defaults delegate to .run()
    # so non-migrated stages keep working unchanged.

    def build_plan(
        self, state: PipelineState, *, feedback: str | None = None
    ) -> StagePlan:
        """Return a StagePlan for this entry.

        Default: a single `todo` item that the default execute_plan resolves
        by calling `.run()`. Stages overriding this itemise concrete tasks
        per §3.2.2.
        """
        return StagePlan(
            items=[
                StagePlanItem(
                    id=f"{self.name}:run",
                    description=f"Run {self.name} stage (legacy .run() path)",
                    status="todo",
                    source="contract",
                    existing_artifact_ref=None,
                    edit_note=None,
                    removed_reason=None,
                )
            ],
            rationale="Default plan — single todo delegating to .run().",
            hash_of_consumed_inputs="",
        )

    async def execute_plan(
        self,
        state: PipelineState,
        plan: StagePlan,
        context: StageContext,
    ) -> StageExecution:
        """Execute actionable plan items. Default: delegate to .run() (legacy path)."""
        result = await self.run(state, context)
        return StageExecution(
            output=result.output,
            status=result.status,
            reason=result.reason,
            feedback=result.feedback,
            next_hint=result.next_hint,
            requests=result.requests,
        )

    def evaluate(
        self,
        state: PipelineState,
        *,
        plan: StagePlan,
        execution: StageExecution,
    ) -> StageEvaluation:
        """Detect dead-ends or additional work. Default: pass through."""
        return StageEvaluation()

    def decide(
        self,
        state: PipelineState,
        *,
        plan: StagePlan,
        execution: StageExecution,
        evaluation: StageEvaluation,
    ) -> StageResult:
        """Build the final StageResult. Default: compose execution + evaluation.

        evaluation.override_* fields win when set; otherwise execution's
        fields pass through. This lets evaluate upgrade a `done` execution
        into a `backtrack` (e.g., dead-end detected post-work) without the
        execute_plan having to know.
        """
        status = evaluation.override_status or execution.status
        next_hint = evaluation.override_next_hint or execution.next_hint
        reason = evaluation.override_reason or execution.reason
        return StageResult(
            output=execution.output,
            status=status,
            next_hint=next_hint,
            reason=reason,
            feedback=execution.feedback,
            requests=execution.requests,
        )

    def validate(self, state: PipelineState) -> bool:
        return True

    def on_enter(self, state: PipelineState) -> PipelineState:
        return state

    def on_exit(self, state: PipelineState) -> PipelineState:
        return state
