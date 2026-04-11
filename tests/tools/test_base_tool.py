from __future__ import annotations

from typing import Any

import pytest
from pydantic import BaseModel

from agentlabx.tools.base import BaseTool, ToolResult


class DummyConfig(BaseModel):
    api_key: str = "test-key"


class DummyTool(BaseTool):
    name = "dummy_tool"
    description = "A test tool"
    config_schema = DummyConfig

    async def execute(self, **kwargs: Any) -> ToolResult:
        query = kwargs.get("query", "")
        return ToolResult(success=True, data={"results": [f"result for {query}"]})


class IncompleteTool(BaseTool):
    name = "incomplete"
    description = "Missing execute"
    config_schema = DummyConfig


class TestToolResult:
    def test_success_result(self):
        result = ToolResult(success=True, data={"key": "value"})
        assert result.success is True
        assert result.error is None

    def test_error_result(self):
        result = ToolResult(success=False, error="Connection timeout")
        assert result.success is False
        assert result.error == "Connection timeout"
        assert result.data is None


class TestBaseTool:
    def test_concrete_tool_instantiates(self):
        tool = DummyTool()
        assert tool.name == "dummy_tool"
        assert tool.config_schema is DummyConfig

    def test_abstract_tool_cannot_instantiate(self):
        with pytest.raises(TypeError):
            IncompleteTool()

    async def test_execute_returns_result(self):
        tool = DummyTool()
        result = await tool.execute(query="test")
        assert result.success is True
        assert "result for test" in result.data["results"]

    def test_validate_config_default(self):
        tool = DummyTool()
        assert tool.validate_config() is True

    def test_get_schema(self):
        tool = DummyTool()
        schema = tool.get_schema()
        assert schema["name"] == "dummy_tool"
        assert schema["description"] == "A test tool"
        assert "parameters" in schema
