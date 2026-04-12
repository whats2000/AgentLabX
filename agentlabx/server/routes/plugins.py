"""Available-plugins endpoint."""

from __future__ import annotations

from fastapi import APIRouter, Request

from agentlabx.core.registry import PluginType

router = APIRouter(prefix="/api/plugins", tags=["plugins"])


@router.get("")
async def list_plugins(request: Request):
    """List all registered plugins grouped by type."""
    registry = request.app.state.context.registry
    result: dict[str, list[str]] = {}
    for plugin_type in PluginType:
        plugins = registry.list_plugins(plugin_type)
        result[plugin_type.value] = sorted(plugins.keys())
    return result
