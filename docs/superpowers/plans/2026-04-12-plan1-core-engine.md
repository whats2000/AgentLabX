# Plan 1: Core Engine — Foundation

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the foundational core engine — plugin registry, configuration system, typed pipeline state, base class contracts, and event bus — so that all subsequent plans (pipeline, providers, server, frontend) have a solid foundation to build on.

**Architecture:** Modular monolith with plugin architecture. The core engine provides: (1) a plugin registry for discovering/registering/resolving plugins by type, (2) a Pydantic-based config system with layered YAML/env/defaults, (3) typed pipeline state definitions using TypedDicts, (4) abstract base classes that define contracts for stages, agents, tools, and providers. Everything is async-first.

**Tech Stack:** Python 3.12, uv for packaging, Pydantic v2, pytest + pytest-asyncio for testing, Ruff for linting

**Spec reference:** `docs/superpowers/specs/2026-04-12-agentlabx-platform-design.md`

**Plan series:**
- **Plan 1: Core Engine** (this plan)
- Plan 2: Pipeline & Agents (LangGraph pipeline, stages, agent framework)
- Plan 3: Providers & Tools (LLM, execution, storage, research tools)
- Plan 4: Server (FastAPI, WebSocket, session management)
- Plan 5: Frontend (React, Ant Design, Vite)

---

## File Structure

```
agentlabx/
  __init__.py                    # Package root, version
  core/
    __init__.py
    registry.py                  # PluginRegistry: discover, register, resolve plugins
    config.py                    # Settings (Pydantic), YAML loader, env merge
    state.py                     # PipelineState TypedDict + all sub-types
    events.py                    # EventBus for inter-plugin communication
  stages/
    __init__.py
    base.py                      # BaseStage ABC + StageResult + register_stage decorator
  agents/
    __init__.py
    base.py                      # BaseAgent ABC + MemoryScope + AgentContext
  tools/
    __init__.py
    base.py                      # BaseTool ABC + ToolResult + register_tool decorator
  providers/
    __init__.py
    llm/
      __init__.py
      base.py                    # BaseLLMProvider ABC
    execution/
      __init__.py
      base.py                    # BaseExecutionBackend ABC + ReproducibilityRecord
    storage/
      __init__.py
      base.py                    # BaseStorageBackend ABC
    code_agent/
      __init__.py
      base.py                    # BaseCodeAgent ABC + CodeResult + CodeContext
tests/
  __init__.py
  core/
    __init__.py
    test_registry.py
    test_config.py
    test_state.py
    test_events.py
  stages/
    __init__.py
    test_base_stage.py
  agents/
    __init__.py
    test_base_agent.py
  tools/
    __init__.py
    test_base_tool.py
  providers/
    __init__.py
    test_base_providers.py
pyproject.toml                   # Package config, dependencies, scripts, ruff config
config/
  default.yaml                   # Default configuration file
```

---

### Task 1: Project Scaffolding

**Files:**
- Create: `pyproject.toml`
- Create: `agentlabx/__init__.py`
- Create: `tests/__init__.py`
- Create: `config/default.yaml`
- Create: `.python-version`

- [ ] **Step 1: Create pyproject.toml**

```toml
[project]
name = "agentlabx"
version = "0.1.0"
description = "Modular multi-instance research automation platform"
requires-python = ">=3.12"
dependencies = [
    "pydantic>=2.0,<3.0",
    "pydantic-settings>=2.0,<3.0",
    "pyyaml>=6.0,<7.0",
]

[project.optional-dependencies]
dev = [
    "pytest>=8.0",
    "pytest-asyncio>=0.24",
    "ruff>=0.4",
]

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.ruff]
target-version = "py312"
line-length = 100

[tool.ruff.lint]
select = ["E", "F", "I", "N", "W", "UP"]

[tool.pytest.ini_options]
testpaths = ["tests"]
asyncio_mode = "auto"

[tool.hatch.build.targets.wheel]
packages = ["agentlabx"]
```

- [ ] **Step 2: Create .python-version**

```
3.12
```

- [ ] **Step 3: Create agentlabx/__init__.py**

```python
"""AgentLabX — Modular multi-instance research automation platform."""

__version__ = "0.1.0"
```

- [ ] **Step 4: Create tests/__init__.py**

Empty file.

- [ ] **Step 5: Create config/default.yaml**

```yaml
server:
  host: "0.0.0.0"
  port: 8000
  cors_origins: ["*"]

llm:
  default_model: "claude-sonnet-4-6"
  temperature: 0.0
  max_retries: 3
  cost_ceiling: 10.00

pipeline:
  default_sequence:
    - literature_review
    - plan_formulation
    - data_exploration
    - data_preparation
    - experimentation
    - results_interpretation
    - report_writing
    - peer_review
  max_total_iterations: 50
  default_mode: "auto"

execution:
  backend: "subprocess"
  timeout: 120
  memory_limit: "4g"

storage:
  backend: "sqlite"
  database_url: "sqlite:///data/agentlabx.db"
  artifacts_path: "./data/artifacts"

budget_policy:
  warning_threshold: 0.7
  critical_threshold: 0.9
  hard_ceiling: 1.0

lab_meeting:
  enabled: true
  triggers:
    consecutive_failures: 3
    score_plateau_rounds: 2
    scheduled_interval: null
  participants: "auto"
  max_discussion_rounds: 5
```

- [ ] **Step 6: Initialize uv project and install dependencies**

Run: `cd d:/GitHub/AgentLabX && uv sync --extra dev`
Expected: Dependencies installed, `.venv` created

- [ ] **Step 7: Verify setup**

Run: `cd d:/GitHub/AgentLabX && uv run python -c "import agentlabx; print(agentlabx.__version__)"`
Expected: `0.1.0`

- [ ] **Step 8: Commit**

```bash
git add pyproject.toml .python-version agentlabx/__init__.py tests/__init__.py config/default.yaml
git commit -m "feat: scaffold project with pyproject.toml, uv, and default config"
```

---

### Task 2: Configuration System

**Files:**
- Create: `agentlabx/core/__init__.py`
- Create: `agentlabx/core/config.py`
- Create: `tests/core/__init__.py`
- Create: `tests/core/test_config.py`

- [ ] **Step 1: Create directory init files**

Create empty `agentlabx/core/__init__.py` and `tests/core/__init__.py`.

- [ ] **Step 2: Write failing tests for config**

```python
# tests/core/test_config.py
import os
from pathlib import Path

import pytest
import yaml

from agentlabx.core.config import (
    BudgetPolicyConfig,
    ExecutionConfig,
    LabMeetingConfig,
    LLMConfig,
    PipelineConfig,
    ServerConfig,
    Settings,
    StorageConfig,
    load_yaml_config,
)

FIXTURES_DIR = Path(__file__).parent / "fixtures"


@pytest.fixture()
def yaml_config_path(tmp_path: Path) -> Path:
    config = {
        "server": {"host": "127.0.0.1", "port": 9000},
        "llm": {"default_model": "gpt-4o", "cost_ceiling": 5.00},
        "pipeline": {
            "default_sequence": ["literature_review", "experimentation"],
            "max_total_iterations": 20,
        },
    }
    p = tmp_path / "config.yaml"
    p.write_text(yaml.dump(config))
    return p


class TestServerConfig:
    def test_defaults(self):
        cfg = ServerConfig()
        assert cfg.host == "0.0.0.0"
        assert cfg.port == 8000
        assert cfg.cors_origins == ["*"]

    def test_override(self):
        cfg = ServerConfig(host="127.0.0.1", port=9000)
        assert cfg.host == "127.0.0.1"
        assert cfg.port == 9000


class TestLLMConfig:
    def test_defaults(self):
        cfg = LLMConfig()
        assert cfg.default_model == "claude-sonnet-4-6"
        assert cfg.temperature == 0.0
        assert cfg.max_retries == 3
        assert cfg.cost_ceiling == 10.00

    def test_override(self):
        cfg = LLMConfig(default_model="gpt-4o", cost_ceiling=5.00)
        assert cfg.default_model == "gpt-4o"
        assert cfg.cost_ceiling == 5.00


class TestPipelineConfig:
    def test_defaults(self):
        cfg = PipelineConfig()
        assert "literature_review" in cfg.default_sequence
        assert "experimentation" in cfg.default_sequence
        assert cfg.max_total_iterations == 50
        assert cfg.default_mode == "auto"

    def test_custom_sequence(self):
        cfg = PipelineConfig(default_sequence=["plan_formulation", "experimentation"])
        assert cfg.default_sequence == ["plan_formulation", "experimentation"]


class TestExecutionConfig:
    def test_defaults(self):
        cfg = ExecutionConfig()
        assert cfg.backend == "subprocess"
        assert cfg.timeout == 120
        assert cfg.memory_limit == "4g"


class TestStorageConfig:
    def test_defaults(self):
        cfg = StorageConfig()
        assert cfg.backend == "sqlite"
        assert "sqlite" in cfg.database_url
        assert cfg.artifacts_path == "./data/artifacts"


class TestBudgetPolicyConfig:
    def test_defaults(self):
        cfg = BudgetPolicyConfig()
        assert cfg.warning_threshold == 0.7
        assert cfg.critical_threshold == 0.9
        assert cfg.hard_ceiling == 1.0

    def test_validation_ordering(self):
        with pytest.raises(ValueError):
            BudgetPolicyConfig(
                warning_threshold=0.95,
                critical_threshold=0.9,
                hard_ceiling=1.0,
            )


class TestLabMeetingConfig:
    def test_defaults(self):
        cfg = LabMeetingConfig()
        assert cfg.enabled is True
        assert cfg.triggers.consecutive_failures == 3
        assert cfg.max_discussion_rounds == 5


class TestLoadYamlConfig:
    def test_load_valid_yaml(self, yaml_config_path: Path):
        data = load_yaml_config(yaml_config_path)
        assert data["server"]["host"] == "127.0.0.1"
        assert data["llm"]["default_model"] == "gpt-4o"

    def test_load_nonexistent_returns_empty(self, tmp_path: Path):
        data = load_yaml_config(tmp_path / "nonexistent.yaml")
        assert data == {}


class TestSettings:
    def test_default_construction(self):
        settings = Settings()
        assert settings.server.port == 8000
        assert settings.llm.default_model == "claude-sonnet-4-6"
        assert settings.pipeline.max_total_iterations == 50

    def test_from_yaml(self, yaml_config_path: Path):
        settings = Settings.from_yaml(yaml_config_path)
        assert settings.server.host == "127.0.0.1"
        assert settings.server.port == 9000
        assert settings.llm.default_model == "gpt-4o"
        # Non-overridden fields keep defaults
        assert settings.execution.backend == "subprocess"

    def test_env_override(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setenv("AGENTLABX_LLM__DEFAULT_MODEL", "o3-mini")
        settings = Settings()
        assert settings.llm.default_model == "o3-mini"

    def test_merge_session_overrides(self):
        settings = Settings()
        overrides = {
            "llm": {"default_model": "gpt-4o", "cost_ceiling": 5.00},
            "pipeline": {"max_total_iterations": 10},
        }
        merged = settings.merge_session_overrides(overrides)
        assert merged.llm.default_model == "gpt-4o"
        assert merged.llm.cost_ceiling == 5.00
        assert merged.pipeline.max_total_iterations == 10
        # Original unchanged
        assert settings.llm.default_model == "claude-sonnet-4-6"
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `cd d:/GitHub/AgentLabX && uv run pytest tests/core/test_config.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'agentlabx.core.config'`

- [ ] **Step 4: Implement config.py**

```python
# agentlabx/core/config.py
"""Layered configuration system with Pydantic v2 settings."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, model_validator


class ServerConfig(BaseModel):
    host: str = "0.0.0.0"
    port: int = 8000
    cors_origins: list[str] = ["*"]


class LLMConfig(BaseModel):
    default_model: str = "claude-sonnet-4-6"
    temperature: float = 0.0
    max_retries: int = 3
    cost_ceiling: float = 10.00


class PipelineConfig(BaseModel):
    default_sequence: list[str] = [
        "literature_review",
        "plan_formulation",
        "data_exploration",
        "data_preparation",
        "experimentation",
        "results_interpretation",
        "report_writing",
        "peer_review",
    ]
    max_total_iterations: int = 50
    default_mode: str = "auto"


class ExecutionConfig(BaseModel):
    backend: str = "subprocess"
    timeout: int = 120
    memory_limit: str = "4g"


class StorageConfig(BaseModel):
    backend: str = "sqlite"
    database_url: str = "sqlite:///data/agentlabx.db"
    artifacts_path: str = "./data/artifacts"


class BudgetPolicyConfig(BaseModel):
    warning_threshold: float = 0.7
    critical_threshold: float = 0.9
    hard_ceiling: float = 1.0

    @model_validator(mode="after")
    def validate_ordering(self) -> BudgetPolicyConfig:
        if not (self.warning_threshold <= self.critical_threshold <= self.hard_ceiling):
            msg = (
                f"Budget thresholds must be ordered: "
                f"warning ({self.warning_threshold}) <= "
                f"critical ({self.critical_threshold}) <= "
                f"hard_ceiling ({self.hard_ceiling})"
            )
            raise ValueError(msg)
        return self


class LabMeetingTriggersConfig(BaseModel):
    consecutive_failures: int = 3
    score_plateau_rounds: int = 2
    scheduled_interval: int | None = None


class LabMeetingConfig(BaseModel):
    enabled: bool = True
    triggers: LabMeetingTriggersConfig = LabMeetingTriggersConfig()
    participants: str = "auto"
    max_discussion_rounds: int = 5


def load_yaml_config(path: Path) -> dict[str, Any]:
    """Load a YAML config file. Returns empty dict if file doesn't exist."""
    if not path.exists():
        return {}
    with open(path) as f:
        data = yaml.safe_load(f)
    return data if data is not None else {}


class Settings(BaseModel):
    """Top-level application settings. Supports layered overrides."""

    server: ServerConfig = ServerConfig()
    llm: LLMConfig = LLMConfig()
    pipeline: PipelineConfig = PipelineConfig()
    execution: ExecutionConfig = ExecutionConfig()
    storage: StorageConfig = StorageConfig()
    budget_policy: BudgetPolicyConfig = BudgetPolicyConfig()
    lab_meeting: LabMeetingConfig = LabMeetingConfig()

    @classmethod
    def from_yaml(cls, path: Path) -> Settings:
        """Create Settings from a YAML file, with defaults for missing fields."""
        data = load_yaml_config(path)
        return cls.model_validate(data)

    def merge_session_overrides(self, overrides: dict[str, Any]) -> Settings:
        """Return a new Settings with session-specific overrides merged in.

        Does not mutate the original. Only overrides fields present in the dict.
        """
        base_data = self.model_dump()
        for key, value in overrides.items():
            if key in base_data and isinstance(value, dict):
                base_data[key].update(value)
            else:
                base_data[key] = value
        return Settings.model_validate(base_data)

    model_config = {
        "env_prefix": "AGENTLABX_",
        "env_nested_delimiter": "__",
    }
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd d:/GitHub/AgentLabX && uv run pytest tests/core/test_config.py -v`
Expected: All tests PASS

- [ ] **Step 6: Commit**

```bash
git add agentlabx/core/__init__.py agentlabx/core/config.py tests/core/__init__.py tests/core/test_config.py
git commit -m "feat(core): add layered configuration system with Pydantic v2"
```

---

### Task 3: Plugin Registry

**Files:**
- Create: `agentlabx/core/registry.py`
- Create: `tests/core/test_registry.py`

- [ ] **Step 1: Write failing tests for registry**

```python
# tests/core/test_registry.py
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd d:/GitHub/AgentLabX && uv run pytest tests/core/test_registry.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'agentlabx.core.registry'`

- [ ] **Step 3: Implement registry.py**

```python
# agentlabx/core/registry.py
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
    """Central registry for all plugin types.

    Plugins are registered by (PluginType, name) and resolved by the same key.
    Supports decorator-based registration for built-in plugins.
    """

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
        """Register a plugin class under a type and name.

        Raises ValueError if name is already registered (unless override=True).
        """
        bucket = self._plugins.setdefault(plugin_type, {})
        if name in bucket and not override:
            msg = (
                f"Plugin '{name}' already registered under {plugin_type.value}. "
                f"Use override=True to replace it."
            )
            raise ValueError(msg)
        bucket[name] = cls

    def resolve(self, plugin_type: PluginType, name: str) -> type:
        """Resolve a plugin class by type and name.

        Raises KeyError if not found.
        """
        bucket = self._plugins.get(plugin_type, {})
        if name not in bucket:
            available = list(bucket.keys())
            msg = (
                f"Plugin '{name}' not found under {plugin_type.value}. "
                f"Available: {available}"
            )
            raise KeyError(msg)
        return bucket[name]

    def has_plugin(self, plugin_type: PluginType, name: str) -> bool:
        """Check if a plugin is registered."""
        return name in self._plugins.get(plugin_type, {})

    def list_plugins(self, plugin_type: PluginType) -> dict[str, type]:
        """Return all registered plugins for a given type."""
        return dict(self._plugins.get(plugin_type, {}))

    def register_decorator(
        self, plugin_type: PluginType, name: str
    ) -> Any:
        """Decorator for registering a plugin class.

        Usage:
            @registry.register_decorator(PluginType.STAGE, "my_stage")
            class MyStage(BaseStage):
                ...
        """

        def wrapper(cls: type) -> type:
            self.register(plugin_type, name, cls)
            return cls

        return wrapper
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd d:/GitHub/AgentLabX && uv run pytest tests/core/test_registry.py -v`
Expected: All tests PASS

- [ ] **Step 5: Commit**

```bash
git add agentlabx/core/registry.py tests/core/test_registry.py
git commit -m "feat(core): add plugin registry with decorator support"
```

---

### Task 4: Pipeline State Types

**Files:**
- Create: `agentlabx/core/state.py`
- Create: `tests/core/test_state.py`

- [ ] **Step 1: Write failing tests for state types**

```python
# tests/core/test_state.py
from __future__ import annotations

from datetime import datetime, timezone

from agentlabx.core.state import (
    AgentMessage,
    CostTracker,
    CrossStageRequest,
    EvidenceLink,
    ExperimentResult,
    Hypothesis,
    PipelineState,
    ReproducibilityRecord,
    StageError,
    Transition,
    create_initial_state,
)


class TestHypothesis:
    def test_create_active_hypothesis(self):
        h = Hypothesis(
            id="H1",
            statement="CoT improves MATH accuracy by >5%",
            status="active",
            created_at_stage="plan_formulation",
        )
        assert h.status == "active"
        assert h.evidence_for == []
        assert h.evidence_against == []
        assert h.parent_hypothesis is None
        assert h.resolved_at_stage is None

    def test_add_evidence(self):
        link = EvidenceLink(
            experiment_result_index=0,
            metric="accuracy",
            value=0.782,
            interpretation="Accuracy improved by 4.8%, supporting H1",
        )
        h = Hypothesis(
            id="H1",
            statement="CoT improves accuracy",
            status="supported",
            evidence_for=[link],
            created_at_stage="plan_formulation",
            resolved_at_stage="results_interpretation",
        )
        assert len(h.evidence_for) == 1
        assert h.evidence_for[0].value == 0.782


class TestReproducibilityRecord:
    def test_create_record(self):
        rec = ReproducibilityRecord(
            random_seed=42,
            environment_hash="abc123",
            run_command="python train.py --seed 42",
            timestamp=datetime(2026, 4, 12, tzinfo=timezone.utc),
        )
        assert rec.random_seed == 42
        assert rec.container_image is None
        assert rec.git_ref is None


class TestExperimentResult:
    def test_create_with_tag(self):
        rec = ReproducibilityRecord(
            random_seed=42,
            environment_hash="abc123",
            run_command="python train.py",
            timestamp=datetime(2026, 4, 12, tzinfo=timezone.utc),
        )
        result = ExperimentResult(
            tag="baseline",
            metrics={"accuracy": 0.75},
            description="Baseline run without CoT",
            reproducibility=rec,
        )
        assert result.tag == "baseline"
        assert result.metrics["accuracy"] == 0.75


class TestCrossStageRequest:
    def test_create_request(self):
        req = CrossStageRequest(
            from_stage="report_writing",
            to_stage="experimentation",
            request_type="experiment",
            description="Need ablation study removing CoT component",
            status="pending",
        )
        assert req.status == "pending"
        assert req.from_stage == "report_writing"


class TestCostTracker:
    def test_initial_cost(self):
        ct = CostTracker()
        assert ct.total_tokens_in == 0
        assert ct.total_tokens_out == 0
        assert ct.total_cost == 0.0

    def test_add_usage(self):
        ct = CostTracker()
        ct.add_usage(tokens_in=1000, tokens_out=500, cost=0.05)
        assert ct.total_tokens_in == 1000
        assert ct.total_tokens_out == 500
        assert ct.total_cost == 0.05
        ct.add_usage(tokens_in=200, tokens_out=100, cost=0.01)
        assert ct.total_tokens_in == 1200
        assert ct.total_cost == pytest.approx(0.06)


class TestTransition:
    def test_create_transition(self):
        t = Transition(
            from_stage="experimentation",
            to_stage="data_preparation",
            reason="Dataset quality issues found",
            triggered_by="agent",
            timestamp=datetime(2026, 4, 12, tzinfo=timezone.utc),
        )
        assert t.triggered_by == "agent"


class TestCreateInitialState:
    def test_creates_valid_state(self):
        state = create_initial_state(
            session_id="sess-001",
            user_id="default",
            research_topic="MATH benchmark improvement",
        )
        assert state["session_id"] == "sess-001"
        assert state["user_id"] == "default"
        assert state["research_topic"] == "MATH benchmark improvement"
        assert state["hypotheses"] == []
        assert state["literature_review"] == []
        assert state["experiment_results"] == []
        assert state["current_stage"] == ""
        assert state["total_iterations"] == 0
        assert state["pending_requests"] == []
        assert state["completed_requests"] == []
        assert state["transition_log"] == []

    def test_state_has_all_stage_output_keys(self):
        state = create_initial_state(
            session_id="s1", user_id="u1", research_topic="test"
        )
        for key in [
            "literature_review",
            "plan",
            "data_exploration",
            "dataset_code",
            "experiment_results",
            "interpretation",
            "report",
            "review",
        ]:
            assert key in state, f"Missing state key: {key}"
            assert state[key] == []


import pytest
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd d:/GitHub/AgentLabX && uv run pytest tests/core/test_state.py -v`
Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: Implement state.py**

```python
# agentlabx/core/state.py
"""Typed pipeline state definitions for LangGraph."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal, TypedDict

from pydantic import BaseModel


# --- Sub-types used within PipelineState ---


class EvidenceLink(BaseModel):
    experiment_result_index: int
    metric: str
    value: float
    interpretation: str


class Hypothesis(BaseModel):
    id: str
    statement: str
    status: Literal["active", "supported", "refuted", "abandoned"]
    evidence_for: list[EvidenceLink] = []
    evidence_against: list[EvidenceLink] = []
    parent_hypothesis: str | None = None
    created_at_stage: str
    resolved_at_stage: str | None = None


class ReproducibilityRecord(BaseModel):
    random_seed: int
    environment_hash: str
    run_command: str
    container_image: str | None = None
    git_ref: str | None = None
    dependencies_snapshot: dict[str, str] = {}
    timestamp: datetime


class ExperimentResult(BaseModel):
    tag: Literal["baseline", "main", "ablation"]
    metrics: dict[str, float]
    description: str
    reproducibility: ReproducibilityRecord
    hypothesis_id: str | None = None
    code_path: str | None = None


class CrossStageRequest(BaseModel):
    from_stage: str
    to_stage: str
    request_type: str
    description: str
    status: Literal["pending", "in_progress", "completed", "cancelled"]
    result: Any | None = None


class CostTracker(BaseModel):
    total_tokens_in: int = 0
    total_tokens_out: int = 0
    total_cost: float = 0.0

    def add_usage(self, *, tokens_in: int, tokens_out: int, cost: float) -> None:
        self.total_tokens_in += tokens_in
        self.total_tokens_out += tokens_out
        self.total_cost += cost


class Transition(BaseModel):
    from_stage: str
    to_stage: str
    reason: str
    triggered_by: Literal["agent", "pi_agent", "human", "system"]
    timestamp: datetime


class AgentMessage(BaseModel):
    agent_name: str
    role: Literal["user", "assistant", "system", "tool"]
    content: str
    stage: str
    timestamp: datetime


class StageError(BaseModel):
    stage: str
    error_type: str
    message: str
    timestamp: datetime
    recovered: bool = False


# --- Sub-types for stage outputs ---
# These are intentionally simple at this layer. Stages will produce
# domain-specific data; these wrappers give them a consistent shape.


class LitReviewResult(BaseModel):
    papers: list[dict[str, Any]]
    summary: str


class ResearchPlan(BaseModel):
    goals: list[str]
    methodology: str
    hypotheses: list[str]
    full_text: str


class EDAResult(BaseModel):
    findings: list[str]
    data_quality_issues: list[str]
    recommendations: list[str]


class ReportResult(BaseModel):
    latex_source: str
    sections: dict[str, str]
    compiled_pdf_path: str | None = None


class ReviewResult(BaseModel):
    decision: Literal["accept", "revise", "reject"]
    scores: dict[str, float]
    feedback: str
    reviewer_id: str


# --- The main PipelineState TypedDict ---


class PipelineState(TypedDict):
    # Identity
    session_id: str
    user_id: str
    research_topic: str

    # Hypothesis tracking
    hypotheses: list[Hypothesis]

    # Stage outputs (versioned — each re-run appends)
    literature_review: list[LitReviewResult]
    plan: list[ResearchPlan]
    data_exploration: list[EDAResult]
    dataset_code: list[str]
    experiment_results: list[ExperimentResult]
    interpretation: list[str]
    report: list[ReportResult]
    review: list[ReviewResult]

    # Cross-stage requests
    pending_requests: list[CrossStageRequest]
    completed_requests: list[CrossStageRequest]

    # Pipeline control
    current_stage: str
    stage_config: dict[str, Any]

    # Routing
    next_stage: str | None
    human_override: str | None
    default_sequence: list[str]
    completed_stages: list[str]

    # Iteration tracking
    stage_iterations: dict[str, int]
    total_iterations: int
    max_stage_iterations: dict[str, int]
    max_total_iterations: int

    # History
    transition_log: list[Transition]
    review_feedback: list[ReviewResult]
    messages: list[AgentMessage]
    cost_tracker: CostTracker
    errors: list[StageError]


def create_initial_state(
    *,
    session_id: str,
    user_id: str,
    research_topic: str,
    default_sequence: list[str] | None = None,
    max_total_iterations: int = 50,
    max_stage_iterations: dict[str, int] | None = None,
) -> PipelineState:
    """Create a fresh PipelineState with all fields initialized."""
    from agentlabx.core.config import PipelineConfig

    if default_sequence is None:
        default_sequence = PipelineConfig().default_sequence

    return PipelineState(
        session_id=session_id,
        user_id=user_id,
        research_topic=research_topic,
        hypotheses=[],
        literature_review=[],
        plan=[],
        data_exploration=[],
        dataset_code=[],
        experiment_results=[],
        interpretation=[],
        report=[],
        review=[],
        pending_requests=[],
        completed_requests=[],
        current_stage="",
        stage_config={},
        next_stage=None,
        human_override=None,
        default_sequence=default_sequence,
        completed_stages=[],
        stage_iterations={},
        total_iterations=0,
        max_stage_iterations=max_stage_iterations or {},
        max_total_iterations=max_total_iterations,
        transition_log=[],
        review_feedback=[],
        messages=[],
        cost_tracker=CostTracker(),
        errors=[],
    )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd d:/GitHub/AgentLabX && uv run pytest tests/core/test_state.py -v`
Expected: All tests PASS

- [ ] **Step 5: Commit**

```bash
git add agentlabx/core/state.py tests/core/test_state.py
git commit -m "feat(core): add typed pipeline state with hypothesis tracking and reproducibility"
```

---

### Task 5: Event Bus

**Files:**
- Create: `agentlabx/core/events.py`
- Create: `tests/core/test_events.py`

- [ ] **Step 1: Write failing tests for event bus**

```python
# tests/core/test_events.py
from __future__ import annotations

import asyncio

import pytest

from agentlabx.core.events import Event, EventBus


class TestEvent:
    def test_create_event(self):
        event = Event(type="stage_started", data={"stage": "lit_review"})
        assert event.type == "stage_started"
        assert event.data["stage"] == "lit_review"

    def test_event_with_source(self):
        event = Event(type="agent_thinking", data={}, source="phd_student")
        assert event.source == "phd_student"


class TestEventBus:
    @pytest.fixture()
    def bus(self) -> EventBus:
        return EventBus()

    async def test_subscribe_and_emit(self, bus: EventBus):
        received: list[Event] = []

        async def handler(event: Event) -> None:
            received.append(event)

        bus.subscribe("test_event", handler)
        await bus.emit(Event(type="test_event", data={"key": "value"}))

        assert len(received) == 1
        assert received[0].data["key"] == "value"

    async def test_multiple_subscribers(self, bus: EventBus):
        count = {"a": 0, "b": 0}

        async def handler_a(event: Event) -> None:
            count["a"] += 1

        async def handler_b(event: Event) -> None:
            count["b"] += 1

        bus.subscribe("ping", handler_a)
        bus.subscribe("ping", handler_b)
        await bus.emit(Event(type="ping", data={}))

        assert count["a"] == 1
        assert count["b"] == 1

    async def test_wildcard_subscriber(self, bus: EventBus):
        received: list[Event] = []

        async def handler(event: Event) -> None:
            received.append(event)

        bus.subscribe("*", handler)
        await bus.emit(Event(type="any_event", data={}))
        await bus.emit(Event(type="other_event", data={}))

        assert len(received) == 2

    async def test_unsubscribe(self, bus: EventBus):
        received: list[Event] = []

        async def handler(event: Event) -> None:
            received.append(event)

        bus.subscribe("test", handler)
        await bus.emit(Event(type="test", data={}))
        assert len(received) == 1

        bus.unsubscribe("test", handler)
        await bus.emit(Event(type="test", data={}))
        assert len(received) == 1  # No new event received

    async def test_emit_no_subscribers(self, bus: EventBus):
        # Should not raise
        await bus.emit(Event(type="no_listeners", data={}))
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd d:/GitHub/AgentLabX && uv run pytest tests/core/test_events.py -v`
Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: Implement events.py**

```python
# agentlabx/core/events.py
"""Async event bus for inter-plugin communication."""

from __future__ import annotations

import asyncio
from collections import defaultdict
from typing import Any, Callable, Coroutine

from pydantic import BaseModel


class Event(BaseModel):
    type: str
    data: dict[str, Any]
    source: str | None = None


EventHandler = Callable[[Event], Coroutine[Any, Any, None]]


class EventBus:
    """Simple async pub/sub event bus.

    Supports exact event type matching and wildcard ("*") subscribers
    that receive all events.
    """

    def __init__(self) -> None:
        self._handlers: dict[str, list[EventHandler]] = defaultdict(list)

    def subscribe(self, event_type: str, handler: EventHandler) -> None:
        """Subscribe a handler to an event type. Use "*" for all events."""
        self._handlers[event_type].append(handler)

    def unsubscribe(self, event_type: str, handler: EventHandler) -> None:
        """Remove a handler from an event type."""
        handlers = self._handlers.get(event_type, [])
        if handler in handlers:
            handlers.remove(handler)

    async def emit(self, event: Event) -> None:
        """Emit an event to all matching handlers.

        Calls exact-match handlers and wildcard handlers concurrently.
        """
        handlers: list[EventHandler] = []
        handlers.extend(self._handlers.get(event.type, []))
        if event.type != "*":
            handlers.extend(self._handlers.get("*", []))

        if handlers:
            await asyncio.gather(*(h(event) for h in handlers))
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd d:/GitHub/AgentLabX && uv run pytest tests/core/test_events.py -v`
Expected: All tests PASS

- [ ] **Step 5: Commit**

```bash
git add agentlabx/core/events.py tests/core/test_events.py
git commit -m "feat(core): add async event bus with wildcard support"
```

---

### Task 6: Base Stage Contract

**Files:**
- Create: `agentlabx/stages/__init__.py`
- Create: `agentlabx/stages/base.py`
- Create: `tests/stages/__init__.py`
- Create: `tests/stages/test_base_stage.py`

- [ ] **Step 1: Create directory init files**

Create empty `agentlabx/stages/__init__.py` and `tests/stages/__init__.py`.

- [ ] **Step 2: Write failing tests for BaseStage**

```python
# tests/stages/test_base_stage.py
from __future__ import annotations

from typing import Any

import pytest

from agentlabx.core.state import PipelineState, create_initial_state
from agentlabx.stages.base import BaseStage, StageContext, StageResult


class ConcreteStage(BaseStage):
    name = "test_stage"
    description = "A test stage"
    required_agents = ["phd_student"]
    required_tools = ["arxiv_search"]

    async def run(self, state: PipelineState, context: StageContext) -> StageResult:
        return StageResult(
            output={"test": "data"},
            status="done",
            reason="Test completed",
        )


class IncompleteStage(BaseStage):
    """Missing abstract method — should fail to instantiate."""

    name = "incomplete"
    description = "Incomplete"
    required_agents = []
    required_tools = []


class TestBaseStage:
    def test_concrete_stage_instantiates(self):
        stage = ConcreteStage()
        assert stage.name == "test_stage"
        assert stage.required_agents == ["phd_student"]

    def test_abstract_stage_cannot_instantiate(self):
        with pytest.raises(TypeError):
            IncompleteStage()  # type: ignore[abstract]

    async def test_run_returns_stage_result(self):
        stage = ConcreteStage()
        state = create_initial_state(
            session_id="s1", user_id="u1", research_topic="test"
        )
        context = StageContext(settings={}, event_bus=None, registry=None)
        result = await stage.run(state, context)
        assert result.status == "done"
        assert result.output == {"test": "data"}

    def test_validate_default_returns_true(self):
        stage = ConcreteStage()
        state = create_initial_state(
            session_id="s1", user_id="u1", research_topic="test"
        )
        assert stage.validate(state) is True

    def test_on_enter_returns_state(self):
        stage = ConcreteStage()
        state = create_initial_state(
            session_id="s1", user_id="u1", research_topic="test"
        )
        result = stage.on_enter(state)
        assert result["session_id"] == "s1"


class TestStageResult:
    def test_done_status(self):
        result = StageResult(output={}, status="done", reason="Complete")
        assert result.next_hint is None
        assert result.feedback is None
        assert result.requests is None

    def test_backtrack_with_hint(self):
        result = StageResult(
            output={},
            status="backtrack",
            next_hint="data_preparation",
            reason="Data quality issues",
            feedback="Need cleaner dataset",
        )
        assert result.status == "backtrack"
        assert result.next_hint == "data_preparation"

    def test_negative_result(self):
        result = StageResult(
            output={"finding": "no significant improvement"},
            status="negative_result",
            reason="CoT did not improve accuracy beyond baseline",
        )
        assert result.status == "negative_result"

    def test_request_status(self):
        from agentlabx.core.state import CrossStageRequest

        req = CrossStageRequest(
            from_stage="report_writing",
            to_stage="experimentation",
            request_type="experiment",
            description="Need ablation study",
            status="pending",
        )
        result = StageResult(
            output={},
            status="request",
            reason="Missing ablation for paper",
            requests=[req],
        )
        assert len(result.requests) == 1
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `cd d:/GitHub/AgentLabX && uv run pytest tests/stages/test_base_stage.py -v`
Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 4: Implement base.py**

```python
# agentlabx/stages/base.py
"""Base stage contract for pipeline stages."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Literal

from pydantic import BaseModel

from agentlabx.core.state import CrossStageRequest, PipelineState


class StageContext(BaseModel):
    """Context passed to a stage during execution."""

    settings: Any
    event_bus: Any
    registry: Any

    model_config = {"arbitrary_types_allowed": True}


class StageResult(BaseModel):
    """Result returned by a stage after execution."""

    output: Any
    status: Literal["done", "backtrack", "negative_result", "request"]
    next_hint: str | None = None
    reason: str
    feedback: str | None = None
    requests: list[CrossStageRequest] | None = None


class BaseStage(ABC):
    """Abstract base class for all pipeline stages.

    Subclasses must implement `run()`. Other methods have sensible defaults.
    """

    name: str
    description: str
    required_agents: list[str]
    required_tools: list[str]

    @abstractmethod
    async def run(self, state: PipelineState, context: StageContext) -> StageResult:
        """Execute the stage logic. Returns a StageResult."""
        ...

    def validate(self, state: PipelineState) -> bool:
        """Validate that the state meets this stage's preconditions.

        Default: always valid. Override to enforce requirements.
        """
        return True

    def on_enter(self, state: PipelineState) -> PipelineState:
        """Hook called when the pipeline enters this stage.

        Default: return state unchanged.
        """
        return state

    def on_exit(self, state: PipelineState) -> PipelineState:
        """Hook called when the pipeline exits this stage.

        Default: return state unchanged.
        """
        return state
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd d:/GitHub/AgentLabX && uv run pytest tests/stages/test_base_stage.py -v`
Expected: All tests PASS

- [ ] **Step 6: Commit**

```bash
git add agentlabx/stages/__init__.py agentlabx/stages/base.py tests/stages/__init__.py tests/stages/test_base_stage.py
git commit -m "feat(stages): add BaseStage ABC with StageResult contract"
```

---

### Task 7: Base Tool Contract

**Files:**
- Create: `agentlabx/tools/__init__.py`
- Create: `agentlabx/tools/base.py`
- Create: `tests/tools/__init__.py`
- Create: `tests/tools/test_base_tool.py`

- [ ] **Step 1: Create directory init files**

Create empty `agentlabx/tools/__init__.py` and `tests/tools/__init__.py`.

- [ ] **Step 2: Write failing tests for BaseTool**

```python
# tests/tools/test_base_tool.py
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
        return ToolResult(
            success=True,
            data={"results": [f"result for {query}"]},
        )


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
            IncompleteTool()  # type: ignore[abstract]

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
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `cd d:/GitHub/AgentLabX && uv run pytest tests/tools/test_base_tool.py -v`
Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 4: Implement base.py**

```python
# agentlabx/tools/base.py
"""Base tool contract for research tools."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from pydantic import BaseModel


class ToolResult(BaseModel):
    """Result returned by a tool execution."""

    success: bool
    data: Any | None = None
    error: str | None = None


class BaseTool(ABC):
    """Abstract base class for all research tools.

    Tools are used by agents during stage execution. Each tool declares
    its config schema and provides an execute method.
    """

    name: str
    description: str
    config_schema: type[BaseModel]

    @abstractmethod
    async def execute(self, **kwargs: Any) -> ToolResult:
        """Execute the tool with the given arguments."""
        ...

    def validate_config(self) -> bool:
        """Validate that the tool's configuration is valid.

        Default: always valid. Override for tools that require API keys, etc.
        """
        return True

    def get_schema(self) -> dict[str, Any]:
        """Return a schema dict suitable for LLM tool calling.

        Includes name, description, and JSON schema for parameters.
        """
        return {
            "name": self.name,
            "description": self.description,
            "parameters": self.config_schema.model_json_schema(),
        }
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd d:/GitHub/AgentLabX && uv run pytest tests/tools/test_base_tool.py -v`
Expected: All tests PASS

- [ ] **Step 6: Commit**

```bash
git add agentlabx/tools/__init__.py agentlabx/tools/base.py tests/tools/__init__.py tests/tools/test_base_tool.py
git commit -m "feat(tools): add BaseTool ABC with ToolResult contract"
```

---

### Task 8: Base Agent Contract

**Files:**
- Create: `agentlabx/agents/__init__.py`
- Create: `agentlabx/agents/base.py`
- Create: `tests/agents/__init__.py`
- Create: `tests/agents/test_base_agent.py`

- [ ] **Step 1: Create directory init files**

Create empty `agentlabx/agents/__init__.py` and `tests/agents/__init__.py`.

- [ ] **Step 2: Write failing tests for BaseAgent**

```python
# tests/agents/test_base_agent.py
from __future__ import annotations

import pytest

from agentlabx.agents.base import AgentContext, BaseAgent, MemoryScope


class TestMemoryScope:
    def test_create_scope(self):
        scope = MemoryScope(
            read=["plan.methodology", "experiment_code.*"],
            write=["experiment_code", "experiment_results"],
            summarize={"literature_review": "abstract", "plan": "goals_only"},
        )
        assert "plan.methodology" in scope.read
        assert "experiment_code" in scope.write
        assert scope.summarize["literature_review"] == "abstract"

    def test_default_empty_scope(self):
        scope = MemoryScope()
        assert scope.read == []
        assert scope.write == []
        assert scope.summarize == {}

    def test_can_read(self):
        scope = MemoryScope(read=["plan.*", "experiment_code.main"])
        assert scope.can_read("plan.methodology") is True
        assert scope.can_read("plan.goals") is True
        assert scope.can_read("experiment_code.main") is True
        assert scope.can_read("experiment_code.other") is False
        assert scope.can_read("report") is False

    def test_wildcard_read_all(self):
        scope = MemoryScope(read=["*"])
        assert scope.can_read("anything") is True

    def test_can_write(self):
        scope = MemoryScope(write=["experiment_code"])
        assert scope.can_write("experiment_code") is True
        assert scope.can_write("report") is False


class DummyAgent(BaseAgent):
    async def inference(self, prompt: str, context: AgentContext) -> str:
        return f"Response to: {prompt}"


class IncompleteAgent(BaseAgent):
    """Missing inference — should fail to instantiate."""

    pass


class TestBaseAgent:
    def test_concrete_agent_instantiates(self):
        scope = MemoryScope(read=["plan.*"], write=["experiment_code"])
        agent = DummyAgent(
            name="test_agent",
            role="test role",
            system_prompt="You are a test agent.",
            tools=[],
            memory_scope=scope,
        )
        assert agent.name == "test_agent"
        assert agent.role == "test role"

    def test_abstract_agent_cannot_instantiate(self):
        with pytest.raises(TypeError):
            IncompleteAgent(  # type: ignore[abstract]
                name="x",
                role="x",
                system_prompt="x",
                tools=[],
                memory_scope=MemoryScope(),
            )

    async def test_inference_returns_string(self):
        agent = DummyAgent(
            name="test",
            role="test",
            system_prompt="test",
            tools=[],
            memory_scope=MemoryScope(),
        )
        ctx = AgentContext(phase="experimentation", state={}, working_memory={})
        result = await agent.inference("hello", ctx)
        assert result == "Response to: hello"

    def test_get_context_default(self):
        agent = DummyAgent(
            name="test",
            role="test",
            system_prompt="You are a test.",
            tools=[],
            memory_scope=MemoryScope(),
        )
        ctx_str = agent.get_context("experimentation")
        assert "You are a test." in ctx_str

    def test_reset_clears_history(self):
        agent = DummyAgent(
            name="test",
            role="test",
            system_prompt="test",
            tools=[],
            memory_scope=MemoryScope(),
        )
        agent.conversation_history.append({"role": "user", "content": "hello"})
        assert len(agent.conversation_history) == 1
        agent.reset()
        assert len(agent.conversation_history) == 0
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `cd d:/GitHub/AgentLabX && uv run pytest tests/agents/test_base_agent.py -v`
Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 4: Implement base.py**

```python
# agentlabx/agents/base.py
"""Base agent contract with differentiated memory scopes."""

from __future__ import annotations

import fnmatch
from abc import ABC, abstractmethod
from typing import Any

from pydantic import BaseModel

from agentlabx.tools.base import BaseTool


class MemoryScope(BaseModel):
    """Defines what an agent can read, write, and summarize.

    Read patterns support wildcards: "plan.*" matches "plan.methodology", "plan.goals", etc.
    The special pattern "*" matches everything.
    """

    read: list[str] = []
    write: list[str] = []
    summarize: dict[str, str] = {}

    def can_read(self, key: str) -> bool:
        """Check if this scope allows reading the given key."""
        return any(fnmatch.fnmatch(key, pattern) for pattern in self.read)

    def can_write(self, key: str) -> bool:
        """Check if this scope allows writing the given key."""
        return key in self.write


class AgentContext(BaseModel):
    """Context passed to an agent during inference."""

    phase: str
    state: dict[str, Any]
    working_memory: dict[str, Any]

    model_config = {"arbitrary_types_allowed": True}


class BaseAgent(ABC):
    """Abstract base class for all agents.

    Agents have a role, system prompt, tools, and a memory scope that
    controls what parts of the pipeline state they can access.
    """

    def __init__(
        self,
        *,
        name: str,
        role: str,
        system_prompt: str,
        tools: list[BaseTool],
        memory_scope: MemoryScope,
    ) -> None:
        self.name = name
        self.role = role
        self.system_prompt = system_prompt
        self.tools = tools
        self.memory_scope = memory_scope
        self.conversation_history: list[dict[str, str]] = []
        self.working_memory: dict[str, Any] = {}

    @abstractmethod
    async def inference(self, prompt: str, context: AgentContext) -> str:
        """Run inference with the agent's LLM. Returns the response text."""
        ...

    def get_context(self, phase: str) -> str:
        """Assemble the agent's context string for a given phase.

        Default implementation returns the system prompt.
        Override for phase-specific context assembly.
        """
        return self.system_prompt

    def reset(self) -> None:
        """Clear the agent's conversation history and working memory."""
        self.conversation_history.clear()
        self.working_memory.clear()
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd d:/GitHub/AgentLabX && uv run pytest tests/agents/test_base_agent.py -v`
Expected: All tests PASS

- [ ] **Step 6: Commit**

```bash
git add agentlabx/agents/__init__.py agentlabx/agents/base.py tests/agents/__init__.py tests/agents/test_base_agent.py
git commit -m "feat(agents): add BaseAgent ABC with differentiated memory scopes"
```

---

### Task 9: Base Provider Contracts

**Files:**
- Create: `agentlabx/providers/__init__.py`
- Create: `agentlabx/providers/llm/__init__.py`
- Create: `agentlabx/providers/llm/base.py`
- Create: `agentlabx/providers/execution/__init__.py`
- Create: `agentlabx/providers/execution/base.py`
- Create: `agentlabx/providers/storage/__init__.py`
- Create: `agentlabx/providers/storage/base.py`
- Create: `agentlabx/providers/code_agent/__init__.py`
- Create: `agentlabx/providers/code_agent/base.py`
- Create: `tests/providers/__init__.py`
- Create: `tests/providers/test_base_providers.py`

- [ ] **Step 1: Create all directory init files**

Create empty `__init__.py` files for:
- `agentlabx/providers/`
- `agentlabx/providers/llm/`
- `agentlabx/providers/execution/`
- `agentlabx/providers/storage/`
- `agentlabx/providers/code_agent/`
- `tests/providers/`

- [ ] **Step 2: Write failing tests for all provider base classes**

```python
# tests/providers/test_base_providers.py
from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from agentlabx.providers.code_agent.base import BaseCodeAgent, CodeContext, CodeResult
from agentlabx.providers.execution.base import (
    BaseExecutionBackend,
    ExecutionResult,
)
from agentlabx.providers.llm.base import BaseLLMProvider, LLMResponse
from agentlabx.providers.storage.base import BaseStorageBackend


# --- LLM Provider ---


class DummyLLMProvider(BaseLLMProvider):
    async def query(
        self,
        *,
        model: str,
        prompt: str,
        system_prompt: str = "",
        temperature: float = 0.0,
    ) -> LLMResponse:
        return LLMResponse(
            content="dummy response",
            tokens_in=10,
            tokens_out=5,
            model=model,
            cost=0.001,
        )


class TestBaseLLMProvider:
    async def test_query_returns_response(self):
        provider = DummyLLMProvider()
        resp = await provider.query(model="test", prompt="hello")
        assert resp.content == "dummy response"
        assert resp.tokens_in == 10
        assert resp.cost == 0.001


# --- Execution Backend ---


class DummyExecutionBackend(BaseExecutionBackend):
    async def execute(
        self,
        *,
        code: str,
        workspace: Path,
        timeout: int = 120,
    ) -> ExecutionResult:
        return ExecutionResult(
            success=True,
            stdout="output",
            stderr="",
            exit_code=0,
            execution_time=1.5,
        )

    async def cleanup(self, workspace: Path) -> None:
        pass


class TestBaseExecutionBackend:
    async def test_execute_returns_result(self):
        backend = DummyExecutionBackend()
        result = await backend.execute(code="print(1)", workspace=Path("/tmp"))
        assert result.success is True
        assert result.stdout == "output"
        assert result.exit_code == 0

    async def test_cleanup_does_not_raise(self):
        backend = DummyExecutionBackend()
        await backend.cleanup(Path("/tmp"))


# --- Storage Backend ---


class DummyStorageBackend(BaseStorageBackend):
    def __init__(self) -> None:
        self._store: dict[str, Any] = {}

    async def save_state(self, session_id: str, stage: str, state: dict[str, Any]) -> None:
        self._store[f"{session_id}/{stage}"] = state

    async def load_state(self, session_id: str, stage: str) -> dict[str, Any] | None:
        return self._store.get(f"{session_id}/{stage}")

    async def save_artifact(
        self, session_id: str, artifact_type: str, name: str, data: bytes
    ) -> str:
        key = f"{session_id}/{artifact_type}/{name}"
        self._store[key] = data
        return key

    async def load_artifact(self, path: str) -> bytes | None:
        return self._store.get(path)


class TestBaseStorageBackend:
    async def test_save_and_load_state(self):
        backend = DummyStorageBackend()
        await backend.save_state("s1", "lit_review", {"papers": 5})
        state = await backend.load_state("s1", "lit_review")
        assert state == {"papers": 5}

    async def test_load_missing_state(self):
        backend = DummyStorageBackend()
        state = await backend.load_state("nonexistent", "stage")
        assert state is None

    async def test_save_and_load_artifact(self):
        backend = DummyStorageBackend()
        path = await backend.save_artifact("s1", "code", "train.py", b"print(1)")
        data = await backend.load_artifact(path)
        assert data == b"print(1)"


# --- Code Agent ---


class DummyCodeAgent(BaseCodeAgent):
    name = "dummy"
    supports_streaming = False

    async def generate(
        self, task: str, context: CodeContext, workspace: Path
    ) -> CodeResult:
        return CodeResult(
            success=True,
            files=["train.py"],
            explanation="Generated training script",
        )

    async def edit(
        self, instruction: str, files: list[Path], context: CodeContext
    ) -> CodeResult:
        return CodeResult(
            success=True,
            files=[str(f) for f in files],
            explanation="Edited files",
        )

    async def debug(
        self, error: str, files: list[Path], execution_log: str
    ) -> CodeResult:
        return CodeResult(
            success=True,
            files=[str(f) for f in files],
            explanation="Fixed the bug",
        )


class TestBaseCodeAgent:
    async def test_generate(self):
        agent = DummyCodeAgent()
        ctx = CodeContext(task_description="train a model", references=[], imports=[])
        result = await agent.generate("implement CoT", ctx, Path("/tmp"))
        assert result.success is True
        assert "train.py" in result.files

    async def test_edit(self):
        agent = DummyCodeAgent()
        ctx = CodeContext(task_description="modify", references=[], imports=[])
        result = await agent.edit("add logging", [Path("train.py")], ctx)
        assert result.success is True

    async def test_debug(self):
        agent = DummyCodeAgent()
        result = await agent.debug("IndexError", [Path("train.py")], "traceback...")
        assert result.success is True
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `cd d:/GitHub/AgentLabX && uv run pytest tests/providers/test_base_providers.py -v`
Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 4: Implement LLM provider base**

```python
# agentlabx/providers/llm/base.py
"""Base LLM provider contract."""

from __future__ import annotations

from abc import ABC, abstractmethod

from pydantic import BaseModel


class LLMResponse(BaseModel):
    content: str
    tokens_in: int
    tokens_out: int
    model: str
    cost: float


class BaseLLMProvider(ABC):
    """Abstract base class for LLM providers."""

    @abstractmethod
    async def query(
        self,
        *,
        model: str,
        prompt: str,
        system_prompt: str = "",
        temperature: float = 0.0,
    ) -> LLMResponse:
        """Send a query to the LLM and return the response."""
        ...
```

- [ ] **Step 5: Implement execution backend base**

```python
# agentlabx/providers/execution/base.py
"""Base execution backend contract."""

from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path

from pydantic import BaseModel


class ExecutionResult(BaseModel):
    success: bool
    stdout: str
    stderr: str
    exit_code: int
    execution_time: float


class BaseExecutionBackend(ABC):
    """Abstract base class for code execution backends."""

    @abstractmethod
    async def execute(
        self,
        *,
        code: str,
        workspace: Path,
        timeout: int = 120,
    ) -> ExecutionResult:
        """Execute code in the backend environment."""
        ...

    @abstractmethod
    async def cleanup(self, workspace: Path) -> None:
        """Clean up resources for a workspace."""
        ...
```

- [ ] **Step 6: Implement storage backend base**

```python
# agentlabx/providers/storage/base.py
"""Base storage backend contract."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any


class BaseStorageBackend(ABC):
    """Abstract base class for storage backends."""

    @abstractmethod
    async def save_state(
        self, session_id: str, stage: str, state: dict[str, Any]
    ) -> None:
        """Save pipeline state for a session at a given stage."""
        ...

    @abstractmethod
    async def load_state(
        self, session_id: str, stage: str
    ) -> dict[str, Any] | None:
        """Load pipeline state. Returns None if not found."""
        ...

    @abstractmethod
    async def save_artifact(
        self, session_id: str, artifact_type: str, name: str, data: bytes
    ) -> str:
        """Save an artifact and return its storage path."""
        ...

    @abstractmethod
    async def load_artifact(self, path: str) -> bytes | None:
        """Load an artifact by path. Returns None if not found."""
        ...
```

- [ ] **Step 7: Implement code agent base**

```python
# agentlabx/providers/code_agent/base.py
"""Base code agent contract for external code generation."""

from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path

from pydantic import BaseModel


class CodeContext(BaseModel):
    task_description: str
    references: list[str]
    imports: list[str]


class CodeResult(BaseModel):
    success: bool
    files: list[str]
    explanation: str
    error: str | None = None


class BaseCodeAgent(ABC):
    """Abstract base class for external code agents.

    Code agents handle the HOW of implementation. Our research agents
    decide WHAT to implement and delegate to code agents.
    """

    name: str
    supports_streaming: bool

    @abstractmethod
    async def generate(
        self, task: str, context: CodeContext, workspace: Path
    ) -> CodeResult:
        """Generate code from a task description."""
        ...

    @abstractmethod
    async def edit(
        self, instruction: str, files: list[Path], context: CodeContext
    ) -> CodeResult:
        """Edit existing code files based on an instruction."""
        ...

    @abstractmethod
    async def debug(
        self, error: str, files: list[Path], execution_log: str
    ) -> CodeResult:
        """Debug and fix code based on an error and execution log."""
        ...
```

- [ ] **Step 8: Run tests to verify they pass**

Run: `cd d:/GitHub/AgentLabX && uv run pytest tests/providers/test_base_providers.py -v`
Expected: All tests PASS

- [ ] **Step 9: Commit**

```bash
git add agentlabx/providers/ tests/providers/
git commit -m "feat(providers): add base contracts for LLM, execution, storage, and code agent"
```

---

### Task 10: Core Package Exports and Full Test Suite

**Files:**
- Modify: `agentlabx/core/__init__.py`
- Modify: `agentlabx/__init__.py`

- [ ] **Step 1: Update agentlabx/core/__init__.py with public exports**

```python
# agentlabx/core/__init__.py
"""Core engine — plugin registry, config, state, events."""

from agentlabx.core.config import Settings
from agentlabx.core.events import Event, EventBus
from agentlabx.core.registry import PluginRegistry, PluginType
from agentlabx.core.state import PipelineState, create_initial_state

__all__ = [
    "Event",
    "EventBus",
    "PipelineState",
    "PluginRegistry",
    "PluginType",
    "Settings",
    "create_initial_state",
]
```

- [ ] **Step 2: Run the full test suite**

Run: `cd d:/GitHub/AgentLabX && uv run pytest tests/ -v --tb=short`
Expected: All tests PASS (should be ~40+ tests across all files)

- [ ] **Step 3: Run linter**

Run: `cd d:/GitHub/AgentLabX && uv run ruff check agentlabx/ tests/`
Expected: No errors

- [ ] **Step 4: Run ruff format check**

Run: `cd d:/GitHub/AgentLabX && uv run ruff format --check agentlabx/ tests/`
Expected: All files formatted correctly (or run `ruff format agentlabx/ tests/` to fix)

- [ ] **Step 5: Commit**

```bash
git add agentlabx/core/__init__.py
git commit -m "feat(core): add public exports for core package"
```

---

## Summary

After completing all 10 tasks, you will have:

- A properly scaffolded Python package with `uv` and `pyproject.toml`
- **Configuration system** — Pydantic v2 settings with YAML + env var layering and session overrides
- **Plugin registry** — type-safe register/resolve/list with decorator support
- **Pipeline state** — fully typed `PipelineState` TypedDict with hypothesis tracking, versioned outputs, cross-stage requests, reproducibility records, and cost tracking
- **Event bus** — async pub/sub with wildcard support
- **Base contracts** — `BaseStage`, `BaseTool`, `BaseAgent` (with `MemoryScope`), `BaseLLMProvider`, `BaseExecutionBackend`, `BaseStorageBackend`, `BaseCodeAgent`
- **Full test coverage** — every contract tested with concrete implementations
- **Default config** — `config/default.yaml` with all platform defaults

This foundation is what Plan 2 (Pipeline & Agents) builds on.
