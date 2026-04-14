"""Shared helpers for real stage implementations.

Stages need to resolve agents and tools from the plugin registry and build
agent contexts. These helpers centralize that boilerplate so every real stage
doesn't reimplement it (and so we don't hit private-method reuse smells).
"""

from __future__ import annotations

from typing import Any

from agentlabx.agents.base import AgentContext, BaseAgent
from agentlabx.agents.config_agent import ConfigAgent
from agentlabx.agents.config_loader import AgentConfig
from agentlabx.agents.context import ContextAssembler
from agentlabx.core.registry import PluginRegistry, PluginType
from agentlabx.core.state import PipelineState
from agentlabx.stages.base import StageContext
from agentlabx.tools.base import BaseTool
from agentlabx.tools.traced import TracedTool


def resolve_agent(
    registry: PluginRegistry,
    name: str,
    *,
    llm_provider: Any = None,
    model: str | None = None,
    cost_tracker: Any = None,
    state: dict | None = None,
    event_bus: Any = None,
    storage: Any = None,
) -> BaseAgent:
    """Resolve an agent from the registry and instantiate it.

    If the registry holds an AgentConfig (the usual case, registered via
    AgentConfigLoader), instantiate a ConfigAgent from it. If it holds a
    concrete BaseAgent subclass, instantiate that class directly.

    When llm_provider is passed, it's injected into the ConfigAgent so the
    agent uses real LLM inference instead of mock stubs. cost_tracker is
    forwarded so agents accumulate usage into the session's shared tracker.

    When state is provided, the agent's memory is hydrated from
    state["agent_memory"][name] (if that key exists), so the agent resumes
    from its last persisted state rather than starting fresh.

    When event_bus and storage are provided, they are forwarded to ConfigAgent
    so inference() emits agent_turn_started / agent_turn_completed events.
    """
    entry = registry.resolve(PluginType.AGENT, name)

    if isinstance(entry, AgentConfig):
        agent = ConfigAgent.from_config(
            entry,
            llm_provider=llm_provider,
            model=model,
            cost_tracker=cost_tracker,
            event_bus=event_bus,
            storage=storage,
        )
    elif isinstance(entry, type) and issubclass(entry, BaseAgent):
        agent = entry()
    else:
        msg = f"Agent plugin '{name}' is neither AgentConfig nor BaseAgent subclass"
        raise TypeError(msg)

    if state is not None:
        memory_dict = (state.get("agent_memory") or {}).get(name)
        if memory_dict:
            agent.load_memory(memory_dict)

    return agent


def resolve_tool(
    registry: PluginRegistry,
    name: str,
    *,
    event_bus: Any = None,
    storage: Any = None,
) -> BaseTool:
    """Resolve a tool from the registry and instantiate it if it's a class.

    Tools may be registered either as classes (instantiated on demand) or as
    pre-configured instances (e.g., CodeExecutor with an injected backend).

    When both ``event_bus`` and ``storage`` are provided, the resolved tool is
    wrapped in a TracedTool that emits agent_tool_call / agent_tool_result events
    and writes agent_turns rows when a TurnContext is active. If either is None,
    the raw tool is returned (backward-compatible passthrough).
    """
    entry = registry.resolve(PluginType.TOOL, name)

    if isinstance(entry, type) and issubclass(entry, BaseTool):
        raw: BaseTool = entry()
    elif isinstance(entry, BaseTool):
        raw = entry
    else:
        msg = f"Tool plugin '{name}' is neither BaseTool subclass nor instance"
        raise TypeError(msg)

    if event_bus is not None and storage is not None:
        return TracedTool(inner=raw, event_bus=event_bus, storage=storage)
    return raw


def build_agent_context(
    state: PipelineState,
    agent: BaseAgent,
    *,
    phase: str,
) -> AgentContext:
    """Assemble an AgentContext for an agent using memory-scope filtering.

    Uses ContextAssembler to filter pipeline state by the agent's memory_scope,
    then wraps the result in an AgentContext for the agent's inference() call.
    """
    assembler = ContextAssembler()
    filtered = assembler.assemble(state, agent.memory_scope)
    return AgentContext(
        phase=phase,
        state=filtered,
        working_memory=agent.working_memory,
        session_id=state.get("session_id"),
    )


def resolve_agents_for_stage(
    context: StageContext,
    agent_names: list[str],
    *,
    state: dict | None = None,
) -> dict[str, BaseAgent]:
    """Resolve multiple agents from the stage context, injecting the LLM provider.

    Returns a dict mapping agent name to instantiated agent, ready for
    inference calls. All agents share the same llm_provider from the context.

    When ``state`` is provided, each resolved agent is hydrated from
    ``state["agent_memory"][name]`` so notes/working_memory/turn_count survive
    across stage boundaries.
    """
    registry = context.registry
    if registry is None:
        msg = "StageContext has no registry — cannot resolve agents"
        raise ValueError(msg)

    return {
        name: resolve_agent(
            registry,
            name,
            llm_provider=context.llm_provider,
            model=context.model,
            cost_tracker=context.cost_tracker,
            state=state,
            event_bus=context.event_bus,
            storage=context.storage,
        )
        for name in agent_names
    }
