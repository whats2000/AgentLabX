from __future__ import annotations

from collections.abc import Iterator

import pytest

from agentlabx.plugins.registry import PluginRegistry, discover_entry_points


def test_empty_registry_lists_no_plugins() -> None:
    reg = PluginRegistry()
    assert reg.list_group("agentlabx.authers") == []


def test_register_and_list() -> None:
    reg = PluginRegistry()
    reg.register("agentlabx.authers", "fake", "pkg.module:FakeAuther")
    assert reg.list_group("agentlabx.authers") == [("fake", "pkg.module:FakeAuther")]


def test_discover_uses_importlib_metadata(monkeypatch: pytest.MonkeyPatch) -> None:
    class _EP:
        def __init__(self, name: str, value: str, group: str) -> None:
            self.name = name
            self.value = value
            self.group = group

    entries: list[_EP] = [
        _EP("default", "agentlabx.auth.default:DefaultAuther", "agentlabx.authers")
    ]

    def _fake_entry_points(*, group: str) -> Iterator[_EP]:
        return iter(e for e in entries if e.group == group)

    monkeypatch.setattr("agentlabx.plugins.registry.entry_points", _fake_entry_points)
    reg = PluginRegistry()
    discover_entry_points(reg, groups=("agentlabx.authers",))
    assert reg.list_group("agentlabx.authers") == [
        ("default", "agentlabx.auth.default:DefaultAuther")
    ]
