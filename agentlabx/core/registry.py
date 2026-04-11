"""Plugin registry for discovering, registering, and resolving plugins."""

from __future__ import annotations

from enum import Enum
from typing import Any


class PluginType(Enum):
    STAGE = "stage"
    TOOL = "tool"
    AGENT = "agent"
    LLM_PROVIDER = "llm_provider"
    EXECUTION_BACKEND = "execution_backend"
    STORAGE_BACKEND = "storage_backend"
    CODE_AGENT = "code_agent"


class PluginRegistry:
    """Central registry for all plugin types."""

    def __init__(self) -> None:
        self._plugins: dict[PluginType, dict[str, type]] = {}

    def register(
        self,
        plugin_type: PluginType,
        name: str,
        cls: type,
        *,
        override: bool = False,
    ) -> None:
        bucket = self._plugins.setdefault(plugin_type, {})
        if name in bucket and not override:
            msg = (
                f"Plugin '{name}' already registered under {plugin_type.value}. "
                f"Use override=True to replace it."
            )
            raise ValueError(msg)
        bucket[name] = cls

    def resolve(self, plugin_type: PluginType, name: str) -> type:
        bucket = self._plugins.get(plugin_type, {})
        if name not in bucket:
            available = list(bucket.keys())
            msg = f"Plugin '{name}' not found under {plugin_type.value}. Available: {available}"
            raise KeyError(msg)
        return bucket[name]

    def has_plugin(self, plugin_type: PluginType, name: str) -> bool:
        return name in self._plugins.get(plugin_type, {})

    def list_plugins(self, plugin_type: PluginType) -> dict[str, type]:
        return dict(self._plugins.get(plugin_type, {}))

    def register_decorator(self, plugin_type: PluginType, name: str) -> Any:
        def wrapper(cls: type) -> type:
            self.register(plugin_type, name, cls)
            return cls

        return wrapper
