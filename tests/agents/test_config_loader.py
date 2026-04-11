"""Tests for AgentConfig and AgentConfigLoader."""

from __future__ import annotations

from pathlib import Path

import pytest

from agentlabx.agents.config_loader import AgentConfig, AgentConfigLoader
from agentlabx.core.registry import PluginRegistry, PluginType

CONFIGS_DIR = Path(__file__).parent.parent.parent / "agentlabx" / "agents" / "configs"


class TestAgentConfigLoader:
    def setup_method(self):
        self.loader = AgentConfigLoader()

    def test_load_single_config(self):
        config = self.loader.load_config(CONFIGS_DIR / "phd_student.yaml")
        assert config.name == "phd_student"
        assert "literature_review" in config.phases
        assert "plan_formulation" in config.phases
        assert "results_interpretation" in config.phases
        assert config.memory_scope.read is not None
        assert config.memory_scope.write is not None
        assert config.conversation_history_length == 20

    def test_load_all_configs(self):
        configs = self.loader.load_all(CONFIGS_DIR)
        names = {c.name for c in configs}
        assert names == {
            "phd_student",
            "postdoc",
            "ml_engineer",
            "sw_engineer",
            "professor",
            "reviewers",
            "pi_agent",
        }

    def test_pi_agent_has_confidence_threshold(self):
        config = self.loader.load_config(CONFIGS_DIR / "pi_agent.yaml")
        assert config.name == "pi_agent"
        assert config.confidence_threshold == pytest.approx(0.6)

    def test_reviewers_minimal_scope(self):
        config = self.loader.load_config(CONFIGS_DIR / "reviewers.yaml")
        assert config.memory_scope.read == ["report"]
        assert config.memory_scope.write == ["review"]
        assert config.memory_scope.summarize == {}

    def test_register_agents(self):
        registry = PluginRegistry()
        configs = self.loader.load_all(CONFIGS_DIR)
        self.loader.register_all(configs, registry)
        assert registry.has_plugin(PluginType.AGENT, "phd_student")
        assert registry.has_plugin(PluginType.AGENT, "pi_agent")
        assert registry.has_plugin(PluginType.AGENT, "reviewers")
        resolved = registry.resolve(PluginType.AGENT, "ml_engineer")
        assert isinstance(resolved, AgentConfig)

    def test_config_has_system_prompt(self):
        config = self.loader.load_config(CONFIGS_DIR / "ml_engineer.yaml")
        assert "machine learning" in config.system_prompt.lower()

    def test_config_has_tools(self):
        config = self.loader.load_config(CONFIGS_DIR / "ml_engineer.yaml")
        assert "code_executor" in config.tools
        assert "github_search" in config.tools
