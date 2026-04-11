from __future__ import annotations

from abc import ABC, abstractmethod

import pytest

from agentlabx.core.registry import PluginRegistry, PluginType


class DummyBase(ABC):
    @abstractmethod
    def do_thing(self) -> str: ...


class DummyPluginA(DummyBase):
    def do_thing(self) -> str:
        return "A"


class DummyPluginB(DummyBase):
    def do_thing(self) -> str:
        return "B"


class NotAPlugin:
    pass


class TestPluginRegistry:
    def setup_method(self):
        self.registry = PluginRegistry()

    def test_register_and_resolve(self):
        self.registry.register(PluginType.STAGE, "dummy_a", DummyPluginA)
        cls = self.registry.resolve(PluginType.STAGE, "dummy_a")
        assert cls is DummyPluginA

    def test_resolve_unknown_raises(self):
        with pytest.raises(KeyError, match="dummy_x"):
            self.registry.resolve(PluginType.STAGE, "dummy_x")

    def test_register_duplicate_raises(self):
        self.registry.register(PluginType.STAGE, "dummy_a", DummyPluginA)
        with pytest.raises(ValueError, match="already registered"):
            self.registry.register(PluginType.STAGE, "dummy_a", DummyPluginB)

    def test_register_duplicate_override(self):
        self.registry.register(PluginType.STAGE, "dummy_a", DummyPluginA)
        self.registry.register(PluginType.STAGE, "dummy_a", DummyPluginB, override=True)
        cls = self.registry.resolve(PluginType.STAGE, "dummy_a")
        assert cls is DummyPluginB

    def test_list_plugins_by_type(self):
        self.registry.register(PluginType.STAGE, "stage_a", DummyPluginA)
        self.registry.register(PluginType.TOOL, "tool_a", DummyPluginB)
        stages = self.registry.list_plugins(PluginType.STAGE)
        assert stages == {"stage_a": DummyPluginA}
        tools = self.registry.list_plugins(PluginType.TOOL)
        assert tools == {"tool_a": DummyPluginB}

    def test_list_empty_type(self):
        result = self.registry.list_plugins(PluginType.STAGE)
        assert result == {}

    def test_all_plugin_types_exist(self):
        assert PluginType.STAGE is not None
        assert PluginType.TOOL is not None
        assert PluginType.AGENT is not None
        assert PluginType.LLM_PROVIDER is not None
        assert PluginType.EXECUTION_BACKEND is not None
        assert PluginType.STORAGE_BACKEND is not None
        assert PluginType.CODE_AGENT is not None

    def test_decorator_registration(self):
        registry = PluginRegistry()

        @registry.register_decorator(PluginType.STAGE, "decorated_stage")
        class DecoratedStage(DummyBase):
            def do_thing(self) -> str:
                return "decorated"

        cls = registry.resolve(PluginType.STAGE, "decorated_stage")
        assert cls is DecoratedStage

    def test_has_plugin(self):
        self.registry.register(PluginType.STAGE, "exists", DummyPluginA)
        assert self.registry.has_plugin(PluginType.STAGE, "exists") is True
        assert self.registry.has_plugin(PluginType.STAGE, "nope") is False
