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


def resolve_agent(
    registry: PluginRegistry,
    name: str,
    *,
    llm_provider: Any = None,
    model: str = "claude-sonnet-4-6",
    cost_tracker: Any = None,
) -> BaseAgent:
    """Resolve an agent from the registry and instantiate it.

    If the registry holds an AgentConfig (the usual case, registered via
    AgentConfigLoader), instantiate a ConfigAgent from it. If it holds a
    concrete BaseAgent subclass, instantiate that class directly.

    When llm_provider is passed, it's injected into the ConfigAgent so the
    agent uses real LLM inference instead of mock stubs. cost_tracker is
    forwarded so agents accumulate usage into the session's shared tracker.
    """
    entry = registry.resolve(PluginType.AGENT, name)

    if isinstance(entry, AgentConfig):
        return ConfigAgent.from_config(
            entry,
            llm_provider=llm_provider,
            model=model,
            cost_tracker=cost_tracker,
        )

    if isinstance(entry, type) and issubclass(entry, BaseAgent):
        return entry()

    msg = f"Agent plugin '{name}' is neither AgentConfig nor BaseAgent subclass"
    raise TypeError(msg)


def resolve_tool(registry: PluginRegistry, name: str) -> BaseTool:
    """Resolve a tool from the registry and instantiate it if it's a class.

    Tools may be registered either as classes (instantiated on demand) or as
    pre-configured instances (e.g., CodeExecutor with an injected backend).
    """
    entry = registry.resolve(PluginType.TOOL, name)

    if isinstance(entry, type) and issubclass(entry, BaseTool):
        return entry()

    if isinstance(entry, BaseTool):
        return entry

    msg = f"Tool plugin '{name}' is neither BaseTool subclass nor instance"
    raise TypeError(msg)


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
    )


def resolve_agents_for_stage(
    context: StageContext,
    agent_names: list[str],
) -> dict[str, BaseAgent]:
    """Resolve multiple agents from the stage context, injecting the LLM provider.

    Returns a dict mapping agent name to instantiated agent, ready for
    inference calls. All agents share the same llm_provider from the context.
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
            cost_tracker=context.cost_tracker,
        )
        for name in agent_names
    }
