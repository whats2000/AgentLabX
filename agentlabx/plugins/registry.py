from __future__ import annotations

from importlib.metadata import entry_points


class PluginRegistry:
    """Group → (name, target-spec) map. Targets are resolved lazily by consumers."""

    def __init__(self) -> None:
        self._entries: dict[str, list[tuple[str, str]]] = {}

    def register(self, group: str, name: str, target: str) -> None:
        self._entries.setdefault(group, []).append((name, target))

    def list_group(self, group: str) -> list[tuple[str, str]]:
        return list(self._entries.get(group, []))


def discover_entry_points(registry: PluginRegistry, *, groups: tuple[str, ...]) -> None:
    for group in groups:
        for ep in entry_points(group=group):
            registry.register(group, ep.name, ep.value)
