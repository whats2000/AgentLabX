"""Available-plugins endpoint."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Request
from pydantic import BaseModel

from agentlabx.core.registry import PluginType

router = APIRouter(prefix="/api/plugins", tags=["plugins"])


class PluginEntry(BaseModel):
    name: str
    description: str = ""


def _describe(entry_key: str, entry: Any) -> PluginEntry:
    """Extract (name, description) from a registered plugin.

    Registered entries take many shapes:

    - BaseStage / BaseTool / BaseLLMProvider / BaseExecutionBackend /
      BaseStorageBackend / BaseCodeAgent — class OR instance with
      `name` and `description` class attributes.
    - AgentConfig (pydantic model) — has `name` + `role`; role is the
      human-readable description.
    - Anything else — fall back to the registry key + the docstring's
      first line, or empty.
    """
    name = getattr(entry, "name", None) or entry_key
    description = getattr(entry, "description", None)

    if description is None:
        # AgentConfig uses `role` as its short description.
        role = getattr(entry, "role", None)
        if isinstance(role, str):
            description = role

    if description is None:
        doc = getattr(entry, "__doc__", None)
        if isinstance(doc, str) and doc.strip():
            description = doc.strip().splitlines()[0]

    return PluginEntry(name=str(name), description=str(description or ""))


@router.get("", response_model=dict[str, list[PluginEntry]])
async def list_plugins(request: Request) -> dict[str, list[PluginEntry]]:
    """List all registered plugins grouped by type.

    Keys use the singular PluginType.value form (`agent`, `stage`, `tool`,
    `llm_provider`, `execution_backend`, `storage_backend`, `code_agent`).
    Entries are {name, description}; description falls back to the
    registered class's docstring's first line when an explicit
    description isn't set.
    """
    registry = request.app.state.context.registry
    result: dict[str, list[PluginEntry]] = {}
    for plugin_type in PluginType:
        plugins = registry.list_plugins(plugin_type)
        entries = [_describe(key, entry) for key, entry in plugins.items()]
        entries.sort(key=lambda e: e.name)
        result[plugin_type.value] = entries
    return result
