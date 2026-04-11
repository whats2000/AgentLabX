# Plan 2: Pipeline & Agents — LangGraph Orchestration

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the LangGraph pipeline orchestration layer — session management, agent config loading, context assembly, PI agent routing, HITL checkpoints, and skeleton stage implementations — so the full research pipeline runs end-to-end with mock LLM responses.

**Architecture:** The pipeline is a LangGraph `StateGraph` where each research stage is a node. A transition handler (PI agent) uses `Command` to route between stages dynamically. Each stage is a subgraph with internal agent loops. Sessions manage lifecycle and isolation. Agents are loaded from YAML configs with memory-scoped context assembly. HITL uses LangGraph's `interrupt()` mechanism.

**Tech Stack:** LangGraph 0.4+, langgraph-checkpoint-sqlite, Python 3.12, Pydantic v2, pytest

**Spec reference:** `docs/superpowers/specs/2026-04-12-agentlabx-platform-design.md` §3-5

**Depends on:** Plan 1 (core engine — all base classes, config, registry, state, events)

**Note on LLM calls:** Plan 2 does NOT implement real LLM calls. All agent inference uses a mock/stub that returns configurable responses. Real LLM integration comes in Plan 3 (Providers & Tools). This keeps Plan 2 focused on orchestration and testable without API keys.

---

## File Structure

```
agentlabx/
  core/
    session.py               # SessionManager: create, run, pause, resume, preferences
    pipeline.py              # PipelineBuilder: assembles StateGraph from registered stages
  agents/
    config_agent.py          # ConfigAgent: generic agent instantiated from YAML
    config_loader.py         # Load agent YAML configs, register with plugin system
    context.py               # ContextAssembler: memory-scope-based state filtering
    pi_agent.py              # PIAgent: transition handler with confidence scoring
    configs/                 # Default agent YAML configs
      phd_student.yaml
      postdoc.yaml
      ml_engineer.yaml
      sw_engineer.yaml
      professor.yaml
      reviewers.yaml
      pi_agent.yaml
  stages/
    runner.py                # StageRunner: LangGraph node wrapper for BaseStage
    transition.py            # TransitionHandler: routing logic between stages
    skeleton.py              # Skeleton implementations of all 8 default stages
    lab_meeting.py           # Lab meeting subgraph
tests/
  core/
    test_session.py
    test_pipeline.py
  agents/
    test_config_agent.py
    test_config_loader.py
    test_context.py
    test_pi_agent.py
  stages/
    test_runner.py
    test_transition.py
    test_skeleton_stages.py
    test_lab_meeting.py
  integration/
    __init__.py
    test_pipeline_e2e.py     # End-to-end pipeline test with mocks
```

---

### Task 1: Add LangGraph Dependencies

**Files:**
- Modify: `pyproject.toml`

- [ ] **Step 1: Add langgraph dependencies to pyproject.toml**

Add to `[project] dependencies`:
```toml
dependencies = [
    "pydantic>=2.0,<3.0",
    "pydantic-settings>=2.0,<3.0",
    "pyyaml>=6.0,<7.0",
    "langgraph>=0.4,<1.0",
    "langgraph-checkpoint-sqlite>=2.0,<3.0",
]
```

- [ ] **Step 2: Install**

Run: `cd d:/GitHub/AgentLabX && uv sync --extra dev`

- [ ] **Step 3: Verify langgraph import**

Run: `cd d:/GitHub/AgentLabX && uv run python -c "import langgraph; print('langgraph OK')"`
Expected: `langgraph OK`

- [ ] **Step 4: Commit**

```bash
git add pyproject.toml uv.lock
git commit -m "build: add langgraph and langgraph-checkpoint-sqlite dependencies"
```

---

### Task 2: Agent YAML Configs

**Files:**
- Create: `agentlabx/agents/configs/phd_student.yaml`
- Create: `agentlabx/agents/configs/postdoc.yaml`
- Create: `agentlabx/agents/configs/ml_engineer.yaml`
- Create: `agentlabx/agents/configs/sw_engineer.yaml`
- Create: `agentlabx/agents/configs/professor.yaml`
- Create: `agentlabx/agents/configs/reviewers.yaml`
- Create: `agentlabx/agents/configs/pi_agent.yaml`
- Create: `agentlabx/agents/config_loader.py`
- Create: `tests/agents/test_config_loader.py`

- [ ] **Step 1: Create agent YAML configs**

Each YAML config follows this schema:
```yaml
name: <agent_name>
role: <role_description>
system_prompt: |
  <multi-line system prompt>
tools: [<tool_names>]
phases: [<stage_names where this agent participates>]
memory_scope:
  read:
    - <state_key_patterns>
  write:
    - <state_keys>
  summarize:
    <key>: <summary_level>
conversation_history_length: <int>
```

Create `agentlabx/agents/configs/phd_student.yaml`:
```yaml
name: phd_student
role: "Core researcher — deepest project knowledge, executes literature review, collaborates on planning and interpretation"
system_prompt: |
  You are a PhD student researcher. You are thorough, detail-oriented, and deeply engaged with the literature. You read papers carefully, take detailed notes, and can connect findings across different works. You collaborate respectfully with your postdoc advisor and follow guidance from your professor.
tools:
  - arxiv_search
  - semantic_scholar
  - hf_dataset_search
phases:
  - literature_review
  - plan_formulation
  - data_exploration
  - results_interpretation
  - report_writing
  - peer_review
memory_scope:
  read:
    - "literature_review.*"
    - "plan.*"
    - "experiment_results.*"
    - "interpretation.*"
    - "hypotheses.*"
    - "review_feedback.*"
  write:
    - literature_review
    - interpretation
  summarize:
    experiment_code: "approach and results summary"
conversation_history_length: 20
```

Create `agentlabx/agents/configs/postdoc.yaml`:
```yaml
name: postdoc
role: "Senior researcher — plans methodology, interprets results, bridges literature and implementation"
system_prompt: |
  You are a postdoctoral researcher. You have deep expertise in experimental methodology and research design. You guide the PhD student, design research plans, and interpret experimental results. You connect literature findings to practical experiments.
tools:
  - arxiv_search
  - semantic_scholar
phases:
  - plan_formulation
  - results_interpretation
memory_scope:
  read:
    - "literature_review.*"
    - "plan.*"
    - "experiment_results.*"
    - "interpretation.*"
    - "hypotheses.*"
    - "data_exploration.*"
  write:
    - plan
    - interpretation
  summarize:
    experiment_code: "approach summary"
conversation_history_length: 15
```

Create `agentlabx/agents/configs/ml_engineer.yaml`:
```yaml
name: ml_engineer
role: "ML specialist — designs and optimizes experiment code, runs experiments"
system_prompt: |
  You are a machine learning engineer. You write clean, efficient experiment code. You understand model architectures, training loops, and evaluation metrics. You iterate on experiments methodically: establish baselines first, then test hypotheses, then run ablations.
tools:
  - code_executor
  - hf_dataset_search
  - github_search
phases:
  - data_preparation
  - experimentation
memory_scope:
  read:
    - "plan.methodology"
    - "experiment_code.*"
    - "execution_logs.*"
    - "dataset.*"
    - "experiment_results.*"
    - "hypotheses.*"
  write:
    - experiment_code
    - experiment_results
  summarize:
    literature_review: "abstracts and key findings"
    report: "results section"
conversation_history_length: 15
```

Create `agentlabx/agents/configs/sw_engineer.yaml`:
```yaml
name: sw_engineer
role: "Software specialist — handles data pipelines, infrastructure, dataset preparation"
system_prompt: |
  You are a software engineer specializing in data pipelines. You write reliable data loading, cleaning, and preprocessing code. You understand dataset formats, APIs, and data quality validation.
tools:
  - code_executor
  - hf_dataset_search
  - github_search
phases:
  - data_exploration
  - data_preparation
memory_scope:
  read:
    - "dataset_code.*"
    - "data_exploration.*"
    - "execution_logs.*"
  write:
    - dataset_code
    - data_exploration
  summarize:
    plan: "data requirements"
    experiment_results: "what data shape is needed"
conversation_history_length: 10
```

Create `agentlabx/agents/configs/professor.yaml`:
```yaml
name: professor
role: "Senior mentor — guides report writing, provides academic expertise"
system_prompt: |
  You are a professor with extensive publication experience. You guide the writing of research papers, ensuring academic rigor, clear argumentation, and proper citation. You focus on the narrative arc of the paper and its contribution to the field.
tools:
  - arxiv_search
  - latex_compiler
phases:
  - report_writing
memory_scope:
  read:
    - "literature_review.*"
    - "plan.*"
    - "interpretation.*"
    - "report.*"
    - "review_feedback.*"
    - "hypotheses.*"
  write:
    - report
  summarize:
    experiment_results: "metrics and interpretation"
conversation_history_length: 10
```

Create `agentlabx/agents/configs/reviewers.yaml`:
```yaml
name: reviewers
role: "Peer reviewers — evaluate the paper with no access to internal project state (blind review)"
system_prompt: |
  You are an anonymous peer reviewer for a top-tier venue. You evaluate the submitted paper on its own merits. You have no knowledge of the authors' process, failed attempts, or internal discussions. Judge only what is in the paper: originality, quality, clarity, significance.
tools: []
phases:
  - peer_review
memory_scope:
  read:
    - "report"
  write:
    - review
  summarize: {}
conversation_history_length: 5
```

Create `agentlabx/agents/configs/pi_agent.yaml`:
```yaml
name: pi_agent
role: "Principal Investigator — research director, makes transition decisions, monitors overall progress"
system_prompt: |
  You are the Principal Investigator directing this research project. You see the big picture: research goals, progress across all stages, budget status, and hypothesis trajectories. You decide what the lab should do next based on the current state of the research, not implementation details.

  When making routing decisions, consider:
  1. Are the research goals being met?
  2. What is the budget situation? (warning = bias toward completing, critical = must advance)
  3. What do the hypothesis statuses tell us?
  4. Is the current approach productive or should we pivot?

  Always include a confidence score (0.0-1.0) with your decision. If you are uncertain, say so — the system will fall back to the default sequence.
tools: []
phases: []
memory_scope:
  read:
    - "hypotheses.*"
    - "transition_log.*"
    - "review_feedback.*"
    - "cost_tracker.*"
    - "stage_iterations.*"
    - "errors.*"
  write: []
  summarize:
    literature_review: "abstract"
    plan: "goals and methodology summary"
    experiment_results: "metrics and outcomes"
    interpretation: "key findings"
    report: "abstract and conclusion"
conversation_history_length: 10
confidence_threshold: 0.6
```

- [ ] **Step 2: Write failing tests for config loader**

```python
# tests/agents/test_config_loader.py
from __future__ import annotations

from pathlib import Path

import pytest

from agentlabx.agents.config_loader import AgentConfigLoader
from agentlabx.agents.base import MemoryScope
from agentlabx.core.registry import PluginRegistry, PluginType


CONFIGS_DIR = Path(__file__).parent.parent.parent / "agentlabx" / "agents" / "configs"


class TestAgentConfigLoader:
    def test_load_single_config(self):
        loader = AgentConfigLoader()
        config = loader.load_config(CONFIGS_DIR / "phd_student.yaml")
        assert config.name == "phd_student"
        assert "literature_review" in config.phases
        assert isinstance(config.memory_scope, MemoryScope)
        assert "literature_review.*" in config.memory_scope.read

    def test_load_all_configs(self):
        loader = AgentConfigLoader()
        configs = loader.load_all(CONFIGS_DIR)
        names = [c.name for c in configs]
        assert "phd_student" in names
        assert "postdoc" in names
        assert "ml_engineer" in names
        assert "sw_engineer" in names
        assert "professor" in names
        assert "reviewers" in names
        assert "pi_agent" in names
        assert len(configs) == 7

    def test_pi_agent_has_confidence_threshold(self):
        loader = AgentConfigLoader()
        config = loader.load_config(CONFIGS_DIR / "pi_agent.yaml")
        assert config.confidence_threshold == 0.6

    def test_reviewers_minimal_scope(self):
        loader = AgentConfigLoader()
        config = loader.load_config(CONFIGS_DIR / "reviewers.yaml")
        assert config.memory_scope.read == ["report"]
        assert config.memory_scope.write == ["review"]
        assert config.memory_scope.summarize == {}

    def test_register_agents(self):
        loader = AgentConfigLoader()
        registry = PluginRegistry()
        configs = loader.load_all(CONFIGS_DIR)
        loader.register_all(configs, registry)
        assert registry.has_plugin(PluginType.AGENT, "phd_student")
        assert registry.has_plugin(PluginType.AGENT, "pi_agent")
        assert registry.has_plugin(PluginType.AGENT, "reviewers")

    def test_config_has_system_prompt(self):
        loader = AgentConfigLoader()
        config = loader.load_config(CONFIGS_DIR / "ml_engineer.yaml")
        assert "machine learning engineer" in config.system_prompt.lower()

    def test_config_has_tools(self):
        loader = AgentConfigLoader()
        config = loader.load_config(CONFIGS_DIR / "ml_engineer.yaml")
        assert "code_executor" in config.tools
        assert "github_search" in config.tools
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `cd d:/GitHub/AgentLabX && uv run pytest tests/agents/test_config_loader.py -v`
Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 4: Implement config_loader.py**

```python
# agentlabx/agents/config_loader.py
"""Load agent definitions from YAML config files."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel

from agentlabx.agents.base import MemoryScope
from agentlabx.core.registry import PluginRegistry, PluginType


class AgentConfig(BaseModel):
    """Parsed agent configuration from a YAML file."""

    name: str
    role: str
    system_prompt: str
    tools: list[str] = []
    phases: list[str] = []
    memory_scope: MemoryScope = MemoryScope()
    conversation_history_length: int = 15
    confidence_threshold: float | None = None


class AgentConfigLoader:
    """Loads agent configs from YAML files and registers them with the plugin system."""

    def load_config(self, path: Path) -> AgentConfig:
        """Load a single agent config from a YAML file."""
        with open(path) as f:
            data = yaml.safe_load(f)
        if "memory_scope" in data:
            data["memory_scope"] = MemoryScope(**data["memory_scope"])
        return AgentConfig.model_validate(data)

    def load_all(self, configs_dir: Path) -> list[AgentConfig]:
        """Load all agent configs from a directory."""
        configs: list[AgentConfig] = []
        for path in sorted(configs_dir.glob("*.yaml")):
            configs.append(self.load_config(path))
        return configs

    def register_all(
        self, configs: list[AgentConfig], registry: PluginRegistry
    ) -> None:
        """Register all agent configs in the plugin registry.

        Stores the AgentConfig itself as the plugin value (not a class).
        The ConfigAgent class will instantiate agents from these configs at runtime.
        """
        for config in configs:
            registry.register(PluginType.AGENT, config.name, config, override=True)
```

**Note:** The registry's `register` method accepts `type` but we're passing `AgentConfig` instances. We need to update `PluginRegistry.register` to accept `type | Any` — or use a separate method. For simplicity, change the registry signature to accept `Any` instead of `type`. Update `agentlabx/core/registry.py`:

Change `cls: type` to `cls: Any` in `register()` and `_plugins` type hint:
```python
self._plugins: dict[PluginType, dict[str, Any]] = {}
```

And `resolve()` return type:
```python
def resolve(self, plugin_type: PluginType, name: str) -> Any:
```

And `list_plugins()`:
```python
def list_plugins(self, plugin_type: PluginType) -> dict[str, Any]:
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd d:/GitHub/AgentLabX && uv run pytest tests/agents/test_config_loader.py -v`
Expected: All PASS

- [ ] **Step 6: Verify no regressions**

Run: `cd d:/GitHub/AgentLabX && uv run pytest tests/ -v --tb=short`
Expected: All existing tests still pass

- [ ] **Step 7: Commit**

```bash
git add agentlabx/agents/configs/ agentlabx/agents/config_loader.py tests/agents/test_config_loader.py agentlabx/core/registry.py
git commit -m "feat(agents): add YAML agent configs and config loader for all 7 default agents"
```

---

### Task 3: ConfigAgent — Generic Agent from YAML

**Files:**
- Create: `agentlabx/agents/config_agent.py`
- Create: `tests/agents/test_config_agent.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/agents/test_config_agent.py
from __future__ import annotations

from pathlib import Path

import pytest

from agentlabx.agents.base import AgentContext, MemoryScope
from agentlabx.agents.config_agent import ConfigAgent
from agentlabx.agents.config_loader import AgentConfig


@pytest.fixture()
def phd_config() -> AgentConfig:
    return AgentConfig(
        name="phd_student",
        role="Core researcher",
        system_prompt="You are a PhD student researcher.",
        tools=["arxiv_search"],
        phases=["literature_review", "plan_formulation"],
        memory_scope=MemoryScope(
            read=["literature_review.*", "plan.*"],
            write=["literature_review"],
            summarize={"experiment_code": "approach summary"},
        ),
        conversation_history_length=20,
    )


class TestConfigAgent:
    def test_create_from_config(self, phd_config: AgentConfig):
        agent = ConfigAgent.from_config(phd_config)
        assert agent.name == "phd_student"
        assert agent.role == "Core researcher"
        assert agent.memory_scope.can_read("literature_review.papers")
        assert agent.memory_scope.can_read("plan.methodology")
        assert not agent.memory_scope.can_read("experiment_code.main")

    def test_conversation_history_length(self, phd_config: AgentConfig):
        agent = ConfigAgent.from_config(phd_config)
        assert agent.max_history_length == 20

    async def test_inference_with_mock(self, phd_config: AgentConfig):
        responses = ["I found 3 relevant papers on chain-of-thought prompting."]
        agent = ConfigAgent.from_config(phd_config, mock_responses=responses)
        ctx = AgentContext(phase="literature_review", state={}, working_memory={})
        result = await agent.inference("Search for papers on CoT", ctx)
        assert result == responses[0]

    async def test_inference_appends_to_history(self, phd_config: AgentConfig):
        responses = ["Response 1", "Response 2"]
        agent = ConfigAgent.from_config(phd_config, mock_responses=responses)
        ctx = AgentContext(phase="literature_review", state={}, working_memory={})
        await agent.inference("prompt 1", ctx)
        await agent.inference("prompt 2", ctx)
        assert len(agent.conversation_history) == 4  # 2 user + 2 assistant

    async def test_history_truncation(self, phd_config: AgentConfig):
        phd_config.conversation_history_length = 2
        responses = [f"response {i}" for i in range(5)]
        agent = ConfigAgent.from_config(phd_config, mock_responses=responses)
        ctx = AgentContext(phase="literature_review", state={}, working_memory={})
        for i in range(5):
            await agent.inference(f"prompt {i}", ctx)
        # max_history_length=2 means 2 pairs = 4 entries max
        assert len(agent.conversation_history) <= 4

    def test_reset(self, phd_config: AgentConfig):
        agent = ConfigAgent.from_config(phd_config)
        agent.conversation_history.append({"role": "user", "content": "test"})
        agent.working_memory["key"] = "value"
        agent.reset()
        assert len(agent.conversation_history) == 0
        assert len(agent.working_memory) == 0
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd d:/GitHub/AgentLabX && uv run pytest tests/agents/test_config_agent.py -v`
Expected: FAIL

- [ ] **Step 3: Implement config_agent.py**

```python
# agentlabx/agents/config_agent.py
"""Generic agent instantiated from a YAML config."""

from __future__ import annotations

from collections import deque
from typing import Any

from agentlabx.agents.base import AgentContext, BaseAgent, MemoryScope
from agentlabx.agents.config_loader import AgentConfig


class ConfigAgent(BaseAgent):
    """An agent whose behavior is defined by a YAML config file.

    For Plan 2 (no real LLM), supports mock_responses for testing.
    Plan 3 will add real LLM inference via BaseLLMProvider.
    """

    def __init__(
        self,
        *,
        name: str,
        role: str,
        system_prompt: str,
        tools: list[Any],
        memory_scope: MemoryScope,
        max_history_length: int = 15,
        mock_responses: list[str] | None = None,
    ) -> None:
        super().__init__(
            name=name,
            role=role,
            system_prompt=system_prompt,
            tools=tools,
            memory_scope=memory_scope,
        )
        self.max_history_length = max_history_length
        self._mock_responses: deque[str] = deque(mock_responses or [])

    @classmethod
    def from_config(
        cls,
        config: AgentConfig,
        mock_responses: list[str] | None = None,
    ) -> ConfigAgent:
        """Create a ConfigAgent from an AgentConfig."""
        return cls(
            name=config.name,
            role=config.role,
            system_prompt=config.system_prompt,
            tools=[],  # Tools resolved at runtime from registry
            memory_scope=config.memory_scope,
            max_history_length=config.conversation_history_length,
            mock_responses=mock_responses,
        )

    async def inference(self, prompt: str, context: AgentContext) -> str:
        """Run inference. Uses mock responses if available, otherwise returns a stub."""
        self.conversation_history.append({"role": "user", "content": prompt})

        if self._mock_responses:
            response = self._mock_responses.popleft()
        else:
            response = f"[{self.name}] Mock response to: {prompt[:50]}..."

        self.conversation_history.append({"role": "assistant", "content": response})
        self._truncate_history()
        return response

    def _truncate_history(self) -> None:
        """Keep only the last max_history_length pairs of messages."""
        max_entries = self.max_history_length * 2  # Each turn = user + assistant
        if len(self.conversation_history) > max_entries:
            self.conversation_history = self.conversation_history[-max_entries:]
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd d:/GitHub/AgentLabX && uv run pytest tests/agents/test_config_agent.py -v`
Expected: All PASS

- [ ] **Step 5: Commit**

```bash
git add agentlabx/agents/config_agent.py tests/agents/test_config_agent.py
git commit -m "feat(agents): add ConfigAgent — generic agent instantiated from YAML config"
```

---

### Task 4: Context Assembly

**Files:**
- Create: `agentlabx/agents/context.py`
- Create: `tests/agents/test_context.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/agents/test_context.py
from __future__ import annotations

import pytest

from agentlabx.agents.base import MemoryScope
from agentlabx.agents.context import ContextAssembler
from agentlabx.core.state import (
    CostTracker,
    LitReviewResult,
    ResearchPlan,
    create_initial_state,
)


@pytest.fixture()
def populated_state():
    state = create_initial_state(
        session_id="s1", user_id="u1", research_topic="MATH benchmark"
    )
    state["literature_review"] = [
        LitReviewResult(
            papers=[{"title": "CoT Prompting", "arxiv_id": "2201.11903"}],
            summary="Chain-of-thought prompting improves reasoning in LLMs.",
        )
    ]
    state["plan"] = [
        ResearchPlan(
            goals=["Improve MATH accuracy by >5%"],
            methodology="Use 5-shot CoT prompting with GPT-4",
            hypotheses=["H1: CoT improves MATH accuracy"],
            full_text="Full plan text here...",
        )
    ]
    state["dataset_code"] = ["import datasets; ds = datasets.load('math')"]
    return state


class TestContextAssembler:
    def test_filter_by_read_scope(self, populated_state):
        scope = MemoryScope(read=["literature_review.*", "plan.*"])
        assembler = ContextAssembler()
        context = assembler.assemble(populated_state, scope)
        assert "literature_review" in context
        assert "plan" in context
        assert "dataset_code" not in context
        assert "experiment_results" not in context

    def test_wildcard_read_all(self, populated_state):
        scope = MemoryScope(read=["*"])
        assembler = ContextAssembler()
        context = assembler.assemble(populated_state, scope)
        assert "literature_review" in context
        assert "plan" in context
        assert "dataset_code" in context

    def test_empty_scope_returns_minimal(self, populated_state):
        scope = MemoryScope()
        assembler = ContextAssembler()
        context = assembler.assemble(populated_state, scope)
        # Should still include identity fields
        assert "research_topic" in context
        assert "session_id" not in context  # Session internals excluded

    def test_summarize_scope_marks_as_summary(self, populated_state):
        scope = MemoryScope(
            read=["plan.*"],
            summarize={"literature_review": "abstract"},
        )
        assembler = ContextAssembler()
        context = assembler.assemble(populated_state, scope)
        assert "plan" in context
        # Summarized fields are included with a summary marker
        assert "literature_review" in context
        assert context["literature_review"]["_summarized"] is True

    def test_format_for_prompt(self, populated_state):
        scope = MemoryScope(read=["literature_review.*", "plan.*"])
        assembler = ContextAssembler()
        context = assembler.assemble(populated_state, scope)
        prompt_text = assembler.format_for_prompt(context)
        assert isinstance(prompt_text, str)
        assert "MATH benchmark" in prompt_text
        assert "Chain-of-thought" in prompt_text
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd d:/GitHub/AgentLabX && uv run pytest tests/agents/test_context.py -v`
Expected: FAIL

- [ ] **Step 3: Implement context.py**

```python
# agentlabx/agents/context.py
"""Context assembly — filters pipeline state by agent memory scope."""

from __future__ import annotations

import json
from typing import Any

from pydantic import BaseModel

from agentlabx.agents.base import MemoryScope
from agentlabx.core.state import PipelineState

# State keys that are stage outputs (filterable by memory scope)
STAGE_OUTPUT_KEYS = {
    "literature_review",
    "plan",
    "data_exploration",
    "dataset_code",
    "experiment_results",
    "interpretation",
    "report",
    "review",
}

# State keys that are always available to the agent (context, not data)
ALWAYS_VISIBLE_KEYS = {"research_topic", "hypotheses", "current_stage"}

# State keys that are internal pipeline control (never shown to agents)
INTERNAL_KEYS = {
    "session_id",
    "user_id",
    "stage_config",
    "next_stage",
    "human_override",
    "default_sequence",
    "max_stage_iterations",
    "max_total_iterations",
}


class ContextAssembler:
    """Assembles agent context from pipeline state filtered by memory scope."""

    def assemble(
        self, state: PipelineState, scope: MemoryScope
    ) -> dict[str, Any]:
        """Filter pipeline state by memory scope.

        Returns a dict with:
        - Always-visible keys (research_topic, hypotheses, current_stage)
        - Stage output keys matching scope.read patterns
        - Summarized keys marked with _summarized=True
        """
        context: dict[str, Any] = {}

        # Always include identity/context fields
        for key in ALWAYS_VISIBLE_KEYS:
            if key in state:
                value = state[key]  # type: ignore[literal-required]
                context[key] = self._serialize_value(value)

        # Include stage outputs matching read patterns
        for key in STAGE_OUTPUT_KEYS:
            if scope.can_read(key) or scope.can_read(f"{key}.*"):
                if key in state:
                    value = state[key]  # type: ignore[literal-required]
                    context[key] = self._serialize_value(value)

        # Include metadata keys matching read patterns
        for key in ["transition_log", "review_feedback", "cost_tracker", "errors",
                     "stage_iterations", "completed_stages", "pending_requests"]:
            if scope.can_read(key) or scope.can_read(f"{key}.*"):
                if key in state:
                    value = state[key]  # type: ignore[literal-required]
                    context[key] = self._serialize_value(value)

        # Add summarized fields (marked, not actually summarized yet — Plan 3 adds LLM summarization)
        for key, summary_level in scope.summarize.items():
            base_key = key.split(".")[0]
            if base_key not in context and base_key in state:
                value = state[base_key]  # type: ignore[literal-required]
                context[base_key] = {
                    "_summarized": True,
                    "_summary_level": summary_level,
                    "data": self._serialize_value(value),
                }

        return context

    def format_for_prompt(self, context: dict[str, Any]) -> str:
        """Format assembled context as a text string for an LLM prompt."""
        parts: list[str] = []

        if "research_topic" in context:
            parts.append(f"## Research Topic\n{context['research_topic']}")

        if "hypotheses" in context:
            hypotheses = context["hypotheses"]
            if hypotheses:
                parts.append("## Hypotheses")
                for h in hypotheses:
                    h_data = h if isinstance(h, dict) else h.model_dump() if hasattr(h, "model_dump") else str(h)
                    status = h_data.get("status", "unknown") if isinstance(h_data, dict) else "unknown"
                    stmt = h_data.get("statement", str(h_data)) if isinstance(h_data, dict) else str(h_data)
                    parts.append(f"- [{status}] {stmt}")

        for key, value in context.items():
            if key in ALWAYS_VISIBLE_KEYS:
                continue
            if isinstance(value, dict) and value.get("_summarized"):
                parts.append(f"## {key.replace('_', ' ').title()} (Summary: {value['_summary_level']})")
                parts.append(str(value["data"]))
            else:
                parts.append(f"## {key.replace('_', ' ').title()}")
                if isinstance(value, list) and value:
                    for item in value:
                        if hasattr(item, "model_dump"):
                            parts.append(json.dumps(item.model_dump(), indent=2, default=str))
                        else:
                            parts.append(str(item))
                elif isinstance(value, str):
                    parts.append(value)
                else:
                    parts.append(str(value))

        return "\n\n".join(parts)

    def _serialize_value(self, value: Any) -> Any:
        """Serialize Pydantic models and other types for context."""
        if isinstance(value, list):
            return [self._serialize_value(v) for v in value]
        if hasattr(value, "model_dump"):
            return value.model_dump()
        return value
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd d:/GitHub/AgentLabX && uv run pytest tests/agents/test_context.py -v`
Expected: All PASS

- [ ] **Step 5: Commit**

```bash
git add agentlabx/agents/context.py tests/agents/test_context.py
git commit -m "feat(agents): add context assembler with memory-scope-based state filtering"
```

---

### Task 5: Session Manager

**Files:**
- Create: `agentlabx/core/session.py`
- Create: `tests/core/test_session.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/core/test_session.py
from __future__ import annotations

from typing import Literal

import pytest

from agentlabx.core.session import Session, SessionManager, SessionPreferences, SessionStatus


class TestSessionPreferences:
    def test_defaults(self):
        prefs = SessionPreferences()
        assert prefs.mode == "auto"
        assert prefs.stage_controls == {}
        assert prefs.backtrack_control == "auto"

    def test_get_stage_control(self):
        prefs = SessionPreferences(
            mode="hitl",
            stage_controls={"experimentation": "approve", "review": "edit"},
        )
        assert prefs.get_stage_control("experimentation") == "approve"
        assert prefs.get_stage_control("review") == "edit"
        assert prefs.get_stage_control("literature_review") == "auto"  # default

    def test_update_preferences(self):
        prefs = SessionPreferences(mode="auto")
        updated = prefs.update(mode="hitl", stage_controls={"experiment": "approve"})
        assert updated.mode == "hitl"
        assert updated.stage_controls == {"experiment": "approve"}
        # Original unchanged
        assert prefs.mode == "auto"


class TestSession:
    def test_create_session(self):
        session = Session(
            session_id="sess-001",
            user_id="default",
            research_topic="MATH benchmark",
        )
        assert session.session_id == "sess-001"
        assert session.status == SessionStatus.CREATED
        assert session.preferences.mode == "auto"

    def test_session_status_transitions(self):
        session = Session(
            session_id="sess-001",
            user_id="default",
            research_topic="test",
        )
        assert session.status == SessionStatus.CREATED
        session.start()
        assert session.status == SessionStatus.RUNNING
        session.pause()
        assert session.status == SessionStatus.PAUSED
        session.resume()
        assert session.status == SessionStatus.RUNNING
        session.complete()
        assert session.status == SessionStatus.COMPLETED

    def test_invalid_transition_raises(self):
        session = Session(
            session_id="sess-001",
            user_id="default",
            research_topic="test",
        )
        with pytest.raises(ValueError, match="Cannot pause"):
            session.pause()  # Can't pause from CREATED

    def test_update_preferences_while_running(self):
        session = Session(
            session_id="sess-001",
            user_id="default",
            research_topic="test",
        )
        session.start()
        session.update_preferences(mode="hitl", stage_controls={"experiment": "approve"})
        assert session.preferences.mode == "hitl"


class TestSessionManager:
    def test_create_session(self):
        manager = SessionManager()
        session = manager.create_session(
            user_id="default",
            research_topic="MATH benchmark",
        )
        assert session.status == SessionStatus.CREATED
        assert session.user_id == "default"

    def test_get_session(self):
        manager = SessionManager()
        session = manager.create_session(user_id="default", research_topic="test")
        retrieved = manager.get_session(session.session_id)
        assert retrieved is session

    def test_get_nonexistent_raises(self):
        manager = SessionManager()
        with pytest.raises(KeyError):
            manager.get_session("nonexistent")

    def test_list_sessions(self):
        manager = SessionManager()
        manager.create_session(user_id="default", research_topic="test1")
        manager.create_session(user_id="default", research_topic="test2")
        sessions = manager.list_sessions()
        assert len(sessions) == 2

    def test_list_sessions_by_user(self):
        manager = SessionManager()
        manager.create_session(user_id="user_a", research_topic="test1")
        manager.create_session(user_id="user_b", research_topic="test2")
        manager.create_session(user_id="user_a", research_topic="test3")
        sessions = manager.list_sessions(user_id="user_a")
        assert len(sessions) == 2

    def test_session_ids_are_unique(self):
        manager = SessionManager()
        s1 = manager.create_session(user_id="default", research_topic="test1")
        s2 = manager.create_session(user_id="default", research_topic="test2")
        assert s1.session_id != s2.session_id
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd d:/GitHub/AgentLabX && uv run pytest tests/core/test_session.py -v`
Expected: FAIL

- [ ] **Step 3: Implement session.py**

```python
# agentlabx/core/session.py
"""Session management — lifecycle, preferences, isolation."""

from __future__ import annotations

import uuid
from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel


class SessionStatus(str, Enum):
    CREATED = "created"
    RUNNING = "running"
    PAUSED = "paused"
    COMPLETED = "completed"
    FAILED = "failed"


class SessionPreferences(BaseModel):
    """Runtime preferences for a session — can be changed during execution."""

    mode: Literal["auto", "hitl"] = "auto"
    stage_controls: dict[str, Literal["auto", "notify", "approve", "edit"]] = {}
    backtrack_control: Literal["auto", "notify", "approve"] = "auto"

    def get_stage_control(
        self, stage_name: str
    ) -> Literal["auto", "notify", "approve", "edit"]:
        """Get the control level for a stage. Defaults to 'auto'."""
        return self.stage_controls.get(stage_name, "auto")

    def update(self, **kwargs: Any) -> SessionPreferences:
        """Return a new SessionPreferences with updates applied."""
        data = self.model_dump()
        data.update(kwargs)
        return SessionPreferences.model_validate(data)


# Valid status transitions
_VALID_TRANSITIONS: dict[SessionStatus, set[SessionStatus]] = {
    SessionStatus.CREATED: {SessionStatus.RUNNING, SessionStatus.FAILED},
    SessionStatus.RUNNING: {SessionStatus.PAUSED, SessionStatus.COMPLETED, SessionStatus.FAILED},
    SessionStatus.PAUSED: {SessionStatus.RUNNING, SessionStatus.FAILED},
    SessionStatus.COMPLETED: set(),
    SessionStatus.FAILED: set(),
}


class Session:
    """A single research session with lifecycle management."""

    def __init__(
        self,
        *,
        session_id: str,
        user_id: str,
        research_topic: str,
        config_overrides: dict[str, Any] | None = None,
    ) -> None:
        self.session_id = session_id
        self.user_id = user_id
        self.research_topic = research_topic
        self.config_overrides = config_overrides or {}
        self.status = SessionStatus.CREATED
        self.preferences = SessionPreferences()

    def _transition(self, target: SessionStatus) -> None:
        """Transition to a new status, validating the transition."""
        valid = _VALID_TRANSITIONS.get(self.status, set())
        if target not in valid:
            msg = f"Cannot {target.value} from {self.status.value}"
            raise ValueError(msg)
        self.status = target

    def start(self) -> None:
        self._transition(SessionStatus.RUNNING)

    def pause(self) -> None:
        self._transition(SessionStatus.PAUSED)

    def resume(self) -> None:
        self._transition(SessionStatus.RUNNING)

    def complete(self) -> None:
        self._transition(SessionStatus.COMPLETED)

    def fail(self) -> None:
        self._transition(SessionStatus.FAILED)

    def update_preferences(self, **kwargs: Any) -> None:
        """Update session preferences (live, during execution)."""
        self.preferences = self.preferences.update(**kwargs)


class SessionManager:
    """Manages session lifecycle and isolation."""

    def __init__(self) -> None:
        self._sessions: dict[str, Session] = {}

    def create_session(
        self,
        *,
        user_id: str,
        research_topic: str,
        config_overrides: dict[str, Any] | None = None,
    ) -> Session:
        """Create a new session with a unique ID."""
        session_id = f"sess-{uuid.uuid4().hex[:12]}"
        session = Session(
            session_id=session_id,
            user_id=user_id,
            research_topic=research_topic,
            config_overrides=config_overrides,
        )
        self._sessions[session_id] = session
        return session

    def get_session(self, session_id: str) -> Session:
        """Get a session by ID. Raises KeyError if not found."""
        if session_id not in self._sessions:
            msg = f"Session '{session_id}' not found"
            raise KeyError(msg)
        return self._sessions[session_id]

    def list_sessions(
        self, *, user_id: str | None = None
    ) -> list[Session]:
        """List sessions, optionally filtered by user."""
        sessions = list(self._sessions.values())
        if user_id is not None:
            sessions = [s for s in sessions if s.user_id == user_id]
        return sessions
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd d:/GitHub/AgentLabX && uv run pytest tests/core/test_session.py -v`
Expected: All PASS

- [ ] **Step 5: Commit**

```bash
git add agentlabx/core/session.py tests/core/test_session.py
git commit -m "feat(core): add session manager with lifecycle, preferences, and multi-user support"
```

---

### Task 6: Stage Runner — LangGraph Node Wrapper

**Files:**
- Create: `agentlabx/stages/runner.py`
- Create: `tests/stages/test_runner.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/stages/test_runner.py
from __future__ import annotations

from typing import Any

import pytest

from agentlabx.core.state import PipelineState, create_initial_state
from agentlabx.stages.base import BaseStage, StageContext, StageResult
from agentlabx.stages.runner import StageRunner


class SuccessStage(BaseStage):
    name = "success_stage"
    description = "Always succeeds"
    required_agents = []
    required_tools = []

    async def run(self, state: PipelineState, context: StageContext) -> StageResult:
        return StageResult(output={"key": "value"}, status="done", reason="Success")


class BacktrackStage(BaseStage):
    name = "backtrack_stage"
    description = "Always backtracks"
    required_agents = []
    required_tools = []

    async def run(self, state: PipelineState, context: StageContext) -> StageResult:
        return StageResult(
            output={},
            status="backtrack",
            next_hint="plan_formulation",
            reason="Data quality issues",
            feedback="Need better data",
        )


class FailingStage(BaseStage):
    name = "failing_stage"
    description = "Always fails"
    required_agents = []
    required_tools = []

    async def run(self, state: PipelineState, context: StageContext) -> StageResult:
        raise RuntimeError("Stage crashed")


class TestStageRunner:
    @pytest.fixture()
    def initial_state(self) -> PipelineState:
        return create_initial_state(
            session_id="s1", user_id="u1", research_topic="test"
        )

    async def test_run_successful_stage(self, initial_state: PipelineState):
        runner = StageRunner(SuccessStage())
        result_state = await runner.run(initial_state)
        assert result_state["current_stage"] == "success_stage"
        assert result_state["total_iterations"] == 1
        assert "success_stage" in result_state["stage_iterations"]

    async def test_run_backtrack_stage(self, initial_state: PipelineState):
        runner = StageRunner(BacktrackStage())
        result_state = await runner.run(initial_state)
        assert result_state["next_stage"] == "plan_formulation"

    async def test_run_failing_stage_captures_error(self, initial_state: PipelineState):
        runner = StageRunner(FailingStage())
        result_state = await runner.run(initial_state)
        assert len(result_state["errors"]) == 1
        assert "Stage crashed" in result_state["errors"][0].message

    async def test_stage_iterations_increment(self, initial_state: PipelineState):
        runner = StageRunner(SuccessStage())
        state = await runner.run(initial_state)
        assert state["stage_iterations"]["success_stage"] == 1
        state2 = await runner.run(state)
        assert state2["stage_iterations"]["success_stage"] == 2
        assert state2["total_iterations"] == 2
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd d:/GitHub/AgentLabX && uv run pytest tests/stages/test_runner.py -v`
Expected: FAIL

- [ ] **Step 3: Implement runner.py**

```python
# agentlabx/stages/runner.py
"""Stage runner — wraps a BaseStage as a LangGraph-compatible node."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from agentlabx.core.state import PipelineState, StageError
from agentlabx.stages.base import BaseStage, StageContext, StageResult


class StageRunner:
    """Wraps a BaseStage for execution within the LangGraph pipeline.

    Handles:
    - Setting current_stage
    - Calling on_enter / run / on_exit
    - Updating iteration counters
    - Capturing errors
    - Storing stage result routing hints in state
    """

    def __init__(self, stage: BaseStage, context: StageContext | None = None) -> None:
        self.stage = stage
        self.context = context or StageContext(settings={}, event_bus=None, registry=None)

    async def run(self, state: PipelineState) -> PipelineState:
        """Execute the stage and return updated state."""
        # Update current stage
        state = {**state, "current_stage": self.stage.name}

        # Call on_enter hook
        state = self.stage.on_enter(state)

        # Increment iteration counters
        stage_iters = dict(state.get("stage_iterations", {}))
        stage_iters[self.stage.name] = stage_iters.get(self.stage.name, 0) + 1
        total_iters = state.get("total_iterations", 0) + 1
        state = {**state, "stage_iterations": stage_iters, "total_iterations": total_iters}

        try:
            result = await self.stage.run(state, self.context)

            # Store routing hints from result
            state = {
                **state,
                "next_stage": result.next_hint,
            }

            # Handle cross-stage requests
            if result.requests:
                pending = list(state.get("pending_requests", []))
                pending.extend(result.requests)
                state = {**state, "pending_requests": pending}

        except Exception as e:
            error = StageError(
                stage=self.stage.name,
                error_type=type(e).__name__,
                message=str(e),
                timestamp=datetime.now(timezone.utc),
                recovered=False,
            )
            errors = list(state.get("errors", []))
            errors.append(error)
            state = {**state, "errors": errors}

        # Call on_exit hook
        state = self.stage.on_exit(state)

        return state
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd d:/GitHub/AgentLabX && uv run pytest tests/stages/test_runner.py -v`
Expected: All PASS

- [ ] **Step 5: Commit**

```bash
git add agentlabx/stages/runner.py tests/stages/test_runner.py
git commit -m "feat(stages): add StageRunner — LangGraph node wrapper for BaseStage"
```

---

### Task 7: Transition Handler

**Files:**
- Create: `agentlabx/stages/transition.py`
- Create: `tests/stages/test_transition.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/stages/test_transition.py
from __future__ import annotations

import pytest

from agentlabx.core.session import SessionPreferences
from agentlabx.core.state import CostTracker, create_initial_state
from agentlabx.stages.transition import TransitionDecision, TransitionHandler


@pytest.fixture()
def handler() -> TransitionHandler:
    return TransitionHandler(
        default_sequence=[
            "literature_review",
            "plan_formulation",
            "experimentation",
            "report_writing",
            "peer_review",
        ]
    )


@pytest.fixture()
def base_state():
    return create_initial_state(
        session_id="s1",
        user_id="u1",
        research_topic="test",
        default_sequence=[
            "literature_review",
            "plan_formulation",
            "experimentation",
            "report_writing",
            "peer_review",
        ],
    )


class TestTransitionHandler:
    def test_advance_to_next_in_sequence(self, handler, base_state):
        base_state["current_stage"] = "literature_review"
        base_state["completed_stages"] = ["literature_review"]
        decision = handler.decide(base_state, SessionPreferences())
        assert decision.next_stage == "plan_formulation"
        assert decision.action == "advance"

    def test_human_override_takes_priority(self, handler, base_state):
        base_state["current_stage"] = "literature_review"
        base_state["human_override"] = "experimentation"
        decision = handler.decide(base_state, SessionPreferences())
        assert decision.next_stage == "experimentation"
        assert decision.action == "human_override"

    def test_stage_hint_respected(self, handler, base_state):
        base_state["current_stage"] = "peer_review"
        base_state["next_stage"] = "experimentation"
        base_state["completed_stages"] = [
            "literature_review", "plan_formulation", "experimentation",
            "report_writing", "peer_review",
        ]
        decision = handler.decide(base_state, SessionPreferences())
        assert decision.next_stage == "experimentation"
        assert decision.action == "backtrack"

    def test_end_when_all_stages_complete(self, handler, base_state):
        base_state["current_stage"] = "peer_review"
        base_state["completed_stages"] = [
            "literature_review", "plan_formulation", "experimentation",
            "report_writing", "peer_review",
        ]
        base_state["next_stage"] = None
        decision = handler.decide(base_state, SessionPreferences())
        assert decision.action == "complete"

    def test_max_iterations_forces_advance(self, handler, base_state):
        base_state["current_stage"] = "experimentation"
        base_state["next_stage"] = "experimentation"  # Stage wants to self-loop
        base_state["stage_iterations"] = {"experimentation": 10}
        base_state["max_stage_iterations"] = {"experimentation": 10}
        decision = handler.decide(base_state, SessionPreferences())
        # Should force advance instead of self-loop
        assert decision.next_stage != "experimentation"
        assert decision.action == "forced_advance"

    def test_total_iterations_limit(self, handler, base_state):
        base_state["current_stage"] = "experimentation"
        base_state["total_iterations"] = 50
        base_state["max_total_iterations"] = 50
        decision = handler.decide(base_state, SessionPreferences())
        assert decision.action == "complete"

    def test_hitl_approve_triggers_checkpoint(self, handler, base_state):
        base_state["current_stage"] = "experimentation"
        base_state["completed_stages"] = ["literature_review", "plan_formulation", "experimentation"]
        prefs = SessionPreferences(
            mode="hitl",
            stage_controls={"report_writing": "approve"},
        )
        decision = handler.decide(base_state, prefs)
        assert decision.next_stage == "report_writing"
        assert decision.needs_approval is True

    def test_auto_mode_no_checkpoint(self, handler, base_state):
        base_state["current_stage"] = "literature_review"
        base_state["completed_stages"] = ["literature_review"]
        prefs = SessionPreferences(mode="auto")
        decision = handler.decide(base_state, prefs)
        assert decision.needs_approval is False


class TestTransitionDecision:
    def test_create_decision(self):
        d = TransitionDecision(
            next_stage="experimentation",
            action="advance",
            reason="Default sequence",
            needs_approval=False,
        )
        assert d.next_stage == "experimentation"
        assert d.action == "advance"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd d:/GitHub/AgentLabX && uv run pytest tests/stages/test_transition.py -v`
Expected: FAIL

- [ ] **Step 3: Implement transition.py**

```python
# agentlabx/stages/transition.py
"""Transition handler — decides which stage runs next."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel

from agentlabx.core.session import SessionPreferences
from agentlabx.core.state import PipelineState


class TransitionDecision(BaseModel):
    """The result of a transition decision."""

    next_stage: str | None
    action: Literal[
        "advance",
        "backtrack",
        "human_override",
        "forced_advance",
        "complete",
        "checkpoint",
    ]
    reason: str
    needs_approval: bool = False
    feedback: str | None = None


class TransitionHandler:
    """Rule-based transition handler.

    Decides the next stage based on priority:
    1. Human override
    2. Hard limits (iteration caps, total iterations)
    3. Stage hint (next_stage from StageResult)
    4. Default sequence

    The PI agent (Plan 2, Task 8) wraps this with LLM-powered judgment.
    This handler provides the fallback logic.
    """

    def __init__(self, default_sequence: list[str]) -> None:
        self.default_sequence = default_sequence

    def decide(
        self,
        state: PipelineState,
        preferences: SessionPreferences,
    ) -> TransitionDecision:
        """Decide what happens next after a stage completes."""
        current = state.get("current_stage", "")

        # 1. Human override — highest priority
        human_override = state.get("human_override")
        if human_override:
            return TransitionDecision(
                next_stage=human_override,
                action="human_override",
                reason=f"Human redirected to {human_override}",
            )

        # 2. Total iterations limit — force complete
        total_iters = state.get("total_iterations", 0)
        max_total = state.get("max_total_iterations", 50)
        if total_iters >= max_total:
            return TransitionDecision(
                next_stage=None,
                action="complete",
                reason=f"Total iteration limit reached ({total_iters}/{max_total})",
            )

        # 3. Stage hint (from StageResult.next_hint)
        next_hint = state.get("next_stage")
        if next_hint:
            # Check per-stage iteration limit
            stage_iters = state.get("stage_iterations", {})
            max_stage_iters = state.get("max_stage_iterations", {})
            current_count = stage_iters.get(next_hint, 0)
            max_count = max_stage_iters.get(next_hint, float("inf"))

            if current_count >= max_count:
                # Stage iteration limit — force advance past the hint
                return self._advance_past(
                    current, state, preferences, reason="stage iteration limit"
                )

            # Determine if this is a backtrack
            action: Literal["advance", "backtrack"] = "advance"
            if next_hint in self.default_sequence:
                hint_idx = self.default_sequence.index(next_hint)
                curr_idx = (
                    self.default_sequence.index(current)
                    if current in self.default_sequence
                    else -1
                )
                if hint_idx <= curr_idx:
                    action = "backtrack"

            needs_approval = self._check_approval(next_hint, action, preferences)
            return TransitionDecision(
                next_stage=next_hint,
                action=action,
                reason=f"Stage requested {'backtrack to' if action == 'backtrack' else ''} {next_hint}",
                needs_approval=needs_approval,
            )

        # 4. Default sequence — advance to next stage
        completed = set(state.get("completed_stages", []))
        for stage_name in self.default_sequence:
            if stage_name not in completed:
                needs_approval = self._check_approval(stage_name, "advance", preferences)
                return TransitionDecision(
                    next_stage=stage_name,
                    action="advance",
                    reason="Next in default sequence",
                    needs_approval=needs_approval,
                )

        # All stages complete
        return TransitionDecision(
            next_stage=None,
            action="complete",
            reason="All stages in sequence completed",
        )

    def _advance_past(
        self,
        current: str,
        state: PipelineState,
        preferences: SessionPreferences,
        reason: str,
    ) -> TransitionDecision:
        """Force advance to the next stage after current in the default sequence."""
        if current in self.default_sequence:
            idx = self.default_sequence.index(current)
            if idx + 1 < len(self.default_sequence):
                next_stage = self.default_sequence[idx + 1]
                return TransitionDecision(
                    next_stage=next_stage,
                    action="forced_advance",
                    reason=f"Forced advance: {reason}",
                )
        return TransitionDecision(
            next_stage=None,
            action="complete",
            reason=f"Forced complete: {reason}, no next stage",
        )

    def _check_approval(
        self,
        target_stage: str,
        action: str,
        preferences: SessionPreferences,
    ) -> bool:
        """Check if the transition needs human approval based on preferences."""
        if preferences.mode == "auto":
            return False

        if action == "backtrack":
            return preferences.backtrack_control in ("approve", "edit")

        control = preferences.get_stage_control(target_stage)
        return control in ("approve", "edit")
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd d:/GitHub/AgentLabX && uv run pytest tests/stages/test_transition.py -v`
Expected: All PASS

- [ ] **Step 5: Commit**

```bash
git add agentlabx/stages/transition.py tests/stages/test_transition.py
git commit -m "feat(stages): add transition handler with priority-based routing"
```

---

### Task 8: Skeleton Stage Implementations

**Files:**
- Create: `agentlabx/stages/skeleton.py`
- Create: `tests/stages/test_skeleton_stages.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/stages/test_skeleton_stages.py
from __future__ import annotations

import pytest

from agentlabx.core.registry import PluginRegistry, PluginType
from agentlabx.core.state import create_initial_state
from agentlabx.stages.base import StageContext
from agentlabx.stages.skeleton import (
    DataExplorationStage,
    DataPreparationStage,
    ExperimentationStage,
    LiteratureReviewStage,
    PeerReviewStage,
    PlanFormulationStage,
    ReportWritingStage,
    ResultsInterpretationStage,
    register_default_stages,
)


@pytest.fixture()
def state():
    return create_initial_state(
        session_id="s1", user_id="u1", research_topic="MATH benchmark"
    )


@pytest.fixture()
def context():
    return StageContext(settings={}, event_bus=None, registry=None)


class TestSkeletonStages:
    async def test_literature_review_runs(self, state, context):
        stage = LiteratureReviewStage()
        result = await stage.run(state, context)
        assert result.status == "done"
        assert result.output is not None

    async def test_plan_formulation_runs(self, state, context):
        stage = PlanFormulationStage()
        result = await stage.run(state, context)
        assert result.status == "done"

    async def test_data_exploration_runs(self, state, context):
        stage = DataExplorationStage()
        result = await stage.run(state, context)
        assert result.status == "done"

    async def test_data_preparation_runs(self, state, context):
        stage = DataPreparationStage()
        result = await stage.run(state, context)
        assert result.status == "done"

    async def test_experimentation_runs(self, state, context):
        stage = ExperimentationStage()
        result = await stage.run(state, context)
        assert result.status == "done"

    async def test_results_interpretation_runs(self, state, context):
        stage = ResultsInterpretationStage()
        result = await stage.run(state, context)
        assert result.status == "done"

    async def test_report_writing_runs(self, state, context):
        stage = ReportWritingStage()
        result = await stage.run(state, context)
        assert result.status == "done"

    async def test_peer_review_runs(self, state, context):
        stage = PeerReviewStage()
        result = await stage.run(state, context)
        assert result.status in ("done", "backtrack")

    def test_all_stages_have_unique_names(self):
        stages = [
            LiteratureReviewStage(),
            PlanFormulationStage(),
            DataExplorationStage(),
            DataPreparationStage(),
            ExperimentationStage(),
            ResultsInterpretationStage(),
            ReportWritingStage(),
            PeerReviewStage(),
        ]
        names = [s.name for s in stages]
        assert len(names) == len(set(names))

    def test_register_default_stages(self):
        registry = PluginRegistry()
        register_default_stages(registry)
        for name in [
            "literature_review",
            "plan_formulation",
            "data_exploration",
            "data_preparation",
            "experimentation",
            "results_interpretation",
            "report_writing",
            "peer_review",
        ]:
            assert registry.has_plugin(PluginType.STAGE, name)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd d:/GitHub/AgentLabX && uv run pytest tests/stages/test_skeleton_stages.py -v`
Expected: FAIL

- [ ] **Step 3: Implement skeleton.py**

```python
# agentlabx/stages/skeleton.py
"""Skeleton implementations of all 8 default research stages.

These return mock data for pipeline testing. Real implementations
will be added in Plan 3 when LLM providers and tools are available.
"""

from __future__ import annotations

from typing import Any

from agentlabx.core.registry import PluginRegistry, PluginType
from agentlabx.core.state import PipelineState
from agentlabx.stages.base import BaseStage, StageContext, StageResult


class LiteratureReviewStage(BaseStage):
    name = "literature_review"
    description = "Search and review academic literature relevant to the research topic"
    required_agents = ["phd_student"]
    required_tools = ["arxiv_search", "semantic_scholar"]

    async def run(self, state: PipelineState, context: StageContext) -> StageResult:
        return StageResult(
            output={
                "papers_found": 5,
                "summary": f"Literature review for: {state['research_topic']}",
            },
            status="done",
            reason="Literature review complete (skeleton)",
        )


class PlanFormulationStage(BaseStage):
    name = "plan_formulation"
    description = "Formulate a research plan with hypotheses and methodology"
    required_agents = ["postdoc", "phd_student"]
    required_tools = []

    async def run(self, state: PipelineState, context: StageContext) -> StageResult:
        return StageResult(
            output={
                "goals": ["Improve accuracy by >5%"],
                "methodology": "Use chain-of-thought prompting",
                "hypotheses": ["H1: CoT improves reasoning accuracy"],
            },
            status="done",
            reason="Plan formulated (skeleton)",
        )


class DataExplorationStage(BaseStage):
    name = "data_exploration"
    description = "Exploratory data analysis — understand the dataset before processing"
    required_agents = ["sw_engineer"]
    required_tools = ["code_executor", "hf_dataset_search"]

    async def run(self, state: PipelineState, context: StageContext) -> StageResult:
        return StageResult(
            output={
                "findings": ["Dataset has 12,500 problems", "5 difficulty levels"],
                "quality_issues": [],
                "recommendations": ["Use stratified sampling by difficulty"],
            },
            status="done",
            reason="Data exploration complete (skeleton)",
        )


class DataPreparationStage(BaseStage):
    name = "data_preparation"
    description = "Clean, preprocess, and prepare dataset for experiments"
    required_agents = ["sw_engineer", "ml_engineer"]
    required_tools = ["code_executor", "hf_dataset_search"]

    async def run(self, state: PipelineState, context: StageContext) -> StageResult:
        return StageResult(
            output={"dataset_code": "from datasets import load_dataset; ds = load_dataset('math')"},
            status="done",
            reason="Data preparation complete (skeleton)",
        )


class ExperimentationStage(BaseStage):
    name = "experimentation"
    description = "Run experiments: baselines, main experiments, ablation studies"
    required_agents = ["ml_engineer"]
    required_tools = ["code_executor"]

    async def run(self, state: PipelineState, context: StageContext) -> StageResult:
        return StageResult(
            output={
                "baseline_accuracy": 0.75,
                "main_accuracy": 0.782,
                "ablation_accuracy": 0.761,
                "improvement": "+4.3%",
            },
            status="done",
            reason="Experiments complete (skeleton): baseline, main, ablation",
        )


class ResultsInterpretationStage(BaseStage):
    name = "results_interpretation"
    description = "Analyze and interpret experimental results"
    required_agents = ["postdoc", "phd_student"]
    required_tools = []

    async def run(self, state: PipelineState, context: StageContext) -> StageResult:
        return StageResult(
            output={"interpretation": "CoT prompting improved accuracy by 4.3%"},
            status="done",
            reason="Results interpreted (skeleton)",
        )


class ReportWritingStage(BaseStage):
    name = "report_writing"
    description = "Write the research paper in LaTeX"
    required_agents = ["professor", "phd_student"]
    required_tools = ["latex_compiler"]

    async def run(self, state: PipelineState, context: StageContext) -> StageResult:
        return StageResult(
            output={"latex_source": "\\documentclass{article}\\begin{document}...\\end{document}"},
            status="done",
            reason="Report written (skeleton)",
        )


class PeerReviewStage(BaseStage):
    name = "peer_review"
    description = "Blind peer review of the research paper"
    required_agents = ["reviewers"]
    required_tools = []

    async def run(self, state: PipelineState, context: StageContext) -> StageResult:
        return StageResult(
            output={
                "decision": "accept",
                "scores": {"originality": 3, "quality": 3, "clarity": 3, "significance": 3},
                "overall_score": 7,
            },
            status="done",
            reason="Paper accepted (skeleton)",
        )


def register_default_stages(registry: PluginRegistry) -> None:
    """Register all 8 default skeleton stages in the plugin registry."""
    stages: list[type[BaseStage]] = [
        LiteratureReviewStage,
        PlanFormulationStage,
        DataExplorationStage,
        DataPreparationStage,
        ExperimentationStage,
        ResultsInterpretationStage,
        ReportWritingStage,
        PeerReviewStage,
    ]
    for stage_cls in stages:
        registry.register(PluginType.STAGE, stage_cls.name, stage_cls)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd d:/GitHub/AgentLabX && uv run pytest tests/stages/test_skeleton_stages.py -v`
Expected: All PASS

- [ ] **Step 5: Commit**

```bash
git add agentlabx/stages/skeleton.py tests/stages/test_skeleton_stages.py
git commit -m "feat(stages): add skeleton implementations for all 8 default research stages"
```

---

### Task 9: Pipeline Builder — LangGraph StateGraph Assembly

**Files:**
- Create: `agentlabx/core/pipeline.py`
- Create: `tests/core/test_pipeline.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/core/test_pipeline.py
from __future__ import annotations

import pytest

from agentlabx.core.pipeline import PipelineBuilder
from agentlabx.core.registry import PluginRegistry, PluginType
from agentlabx.core.session import SessionPreferences
from agentlabx.core.state import create_initial_state
from agentlabx.stages.skeleton import register_default_stages


@pytest.fixture()
def registry() -> PluginRegistry:
    reg = PluginRegistry()
    register_default_stages(reg)
    return reg


@pytest.fixture()
def builder(registry: PluginRegistry) -> PipelineBuilder:
    return PipelineBuilder(registry=registry)


class TestPipelineBuilder:
    def test_build_compiles_graph(self, builder: PipelineBuilder):
        graph = builder.build(
            stage_sequence=[
                "literature_review",
                "plan_formulation",
                "experimentation",
            ]
        )
        assert graph is not None

    async def test_run_single_stage(self, builder: PipelineBuilder):
        graph = builder.build(stage_sequence=["literature_review"])
        initial = create_initial_state(
            session_id="s1",
            user_id="u1",
            research_topic="MATH benchmark",
            default_sequence=["literature_review"],
        )
        config = {"configurable": {"thread_id": "test-1"}}
        result = await graph.ainvoke(initial, config=config)
        assert result["current_stage"] == "literature_review"
        assert result["total_iterations"] >= 1

    async def test_run_full_pipeline(self, builder: PipelineBuilder):
        sequence = [
            "literature_review",
            "plan_formulation",
            "data_exploration",
            "data_preparation",
            "experimentation",
            "results_interpretation",
            "report_writing",
            "peer_review",
        ]
        graph = builder.build(stage_sequence=sequence)
        initial = create_initial_state(
            session_id="s1",
            user_id="u1",
            research_topic="MATH benchmark",
            default_sequence=sequence,
        )
        config = {"configurable": {"thread_id": "test-full"}}
        result = await graph.ainvoke(initial, config=config)
        # Pipeline should complete all stages
        assert result["total_iterations"] == len(sequence)

    async def test_stream_produces_events(self, builder: PipelineBuilder):
        graph = builder.build(
            stage_sequence=["literature_review", "plan_formulation"]
        )
        initial = create_initial_state(
            session_id="s1",
            user_id="u1",
            research_topic="test",
            default_sequence=["literature_review", "plan_formulation"],
        )
        config = {"configurable": {"thread_id": "test-stream"}}
        events = []
        async for event in graph.astream(initial, config=config):
            events.append(event)
        assert len(events) >= 2  # At least one event per stage
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd d:/GitHub/AgentLabX && uv run pytest tests/core/test_pipeline.py -v`
Expected: FAIL

- [ ] **Step 3: Implement pipeline.py**

```python
# agentlabx/core/pipeline.py
"""Pipeline builder — assembles a LangGraph StateGraph from registered stages."""

from __future__ import annotations

from typing import Any

from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, START, StateGraph

from agentlabx.core.registry import PluginRegistry, PluginType
from agentlabx.core.session import SessionPreferences
from agentlabx.core.state import PipelineState
from agentlabx.stages.base import BaseStage, StageContext
from agentlabx.stages.runner import StageRunner
from agentlabx.stages.transition import TransitionHandler


class PipelineBuilder:
    """Builds a LangGraph StateGraph from registered stage plugins.

    The graph follows a dynamic routing pattern:
    START → stage_1 → transition → stage_2 → transition → ... → END

    The transition handler decides which stage runs next based on:
    - Stage result hints (backtrack, request)
    - Default sequence order
    - Iteration limits
    """

    def __init__(
        self,
        registry: PluginRegistry,
        preferences: SessionPreferences | None = None,
    ) -> None:
        self.registry = registry
        self.preferences = preferences or SessionPreferences()

    def build(
        self,
        stage_sequence: list[str],
        checkpointer: Any | None = None,
    ) -> Any:
        """Build and compile the pipeline graph.

        Args:
            stage_sequence: Ordered list of stage names to include.
            checkpointer: LangGraph checkpointer. Defaults to MemorySaver.

        Returns:
            Compiled LangGraph graph ready for invoke/stream.
        """
        if checkpointer is None:
            checkpointer = MemorySaver()

        transition_handler = TransitionHandler(default_sequence=stage_sequence)
        graph = StateGraph(PipelineState)

        # Create stage runner nodes
        for stage_name in stage_sequence:
            stage_cls = self.registry.resolve(PluginType.STAGE, stage_name)
            stage_instance: BaseStage = stage_cls()
            runner = StageRunner(stage_instance)

            async def make_node(state: PipelineState, _runner: StageRunner = runner) -> PipelineState:
                return await _runner.run(state)

            graph.add_node(stage_name, make_node)

        # Add transition node
        def transition_node(state: PipelineState) -> PipelineState:
            decision = transition_handler.decide(state, self.preferences)

            # Mark current stage as completed
            completed = list(state.get("completed_stages", []))
            current = state.get("current_stage", "")
            if current and current not in completed:
                completed.append(current)

            return {
                **state,
                "completed_stages": completed,
                "next_stage": None,  # Clear hint after processing
                "human_override": None,  # Clear override after processing
                "_transition_decision": decision.model_dump(),
            }

        graph.add_node("transition", transition_node)

        # Wire edges: START → first_stage
        graph.add_edge(START, stage_sequence[0])

        # Each stage → transition
        for stage_name in stage_sequence:
            graph.add_edge(stage_name, "transition")

        # Transition → next stage or END
        def route_after_transition(state: PipelineState) -> str:
            decision_data = state.get("_transition_decision", {})
            action = decision_data.get("action", "complete")
            next_stage = decision_data.get("next_stage")

            if action == "complete" or next_stage is None:
                return END

            if next_stage in stage_sequence:
                return next_stage

            return END

        graph.add_conditional_edges(
            "transition",
            route_after_transition,
            {stage_name: stage_name for stage_name in stage_sequence} | {END: END},
        )

        return graph.compile(checkpointer=checkpointer)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd d:/GitHub/AgentLabX && uv run pytest tests/core/test_pipeline.py -v`
Expected: All PASS

- [ ] **Step 5: Run full test suite**

Run: `cd d:/GitHub/AgentLabX && uv run pytest tests/ -v --tb=short`
Expected: All tests pass, no regressions

- [ ] **Step 6: Commit**

```bash
git add agentlabx/core/pipeline.py tests/core/test_pipeline.py
git commit -m "feat(core): add PipelineBuilder — LangGraph StateGraph assembly with dynamic routing"
```

---

### Task 10: End-to-End Integration Test

**Files:**
- Create: `tests/integration/__init__.py`
- Create: `tests/integration/test_pipeline_e2e.py`

- [ ] **Step 1: Write integration test**

```python
# tests/integration/test_pipeline_e2e.py
"""End-to-end pipeline test — verifies the full orchestration works."""

from __future__ import annotations

import pytest

from agentlabx.core.pipeline import PipelineBuilder
from agentlabx.core.registry import PluginRegistry
from agentlabx.core.session import Session, SessionManager, SessionPreferences
from agentlabx.core.state import create_initial_state
from agentlabx.stages.skeleton import register_default_stages


@pytest.fixture()
def full_pipeline():
    """Set up a complete pipeline with all default stages."""
    registry = PluginRegistry()
    register_default_stages(registry)
    builder = PipelineBuilder(registry=registry)
    sequence = [
        "literature_review",
        "plan_formulation",
        "data_exploration",
        "data_preparation",
        "experimentation",
        "results_interpretation",
        "report_writing",
        "peer_review",
    ]
    graph = builder.build(stage_sequence=sequence)
    return graph, sequence


class TestPipelineE2E:
    async def test_full_pipeline_completes(self, full_pipeline):
        graph, sequence = full_pipeline
        state = create_initial_state(
            session_id="e2e-001",
            user_id="default",
            research_topic="Improve MATH benchmark accuracy with CoT",
            default_sequence=sequence,
        )
        config = {"configurable": {"thread_id": "e2e-test-1"}}
        result = await graph.ainvoke(state, config=config)

        # All 8 stages should have run
        assert result["total_iterations"] == 8
        assert len(result["completed_stages"]) == 8
        for stage_name in sequence:
            assert stage_name in result["completed_stages"]

    async def test_pipeline_with_session_manager(self, full_pipeline):
        graph, sequence = full_pipeline
        manager = SessionManager()
        session = manager.create_session(
            user_id="researcher_a",
            research_topic="NLP transfer learning",
        )
        session.start()
        assert session.status.value == "running"

        state = create_initial_state(
            session_id=session.session_id,
            user_id=session.user_id,
            research_topic=session.research_topic,
            default_sequence=sequence,
        )
        config = {"configurable": {"thread_id": session.session_id}}
        result = await graph.ainvoke(state, config=config)

        session.complete()
        assert session.status.value == "completed"
        assert result["total_iterations"] == 8

    async def test_pipeline_streaming(self, full_pipeline):
        graph, sequence = full_pipeline
        state = create_initial_state(
            session_id="stream-001",
            user_id="default",
            research_topic="Test streaming",
            default_sequence=sequence,
        )
        config = {"configurable": {"thread_id": "stream-test"}}

        events = []
        async for event in graph.astream(state, config=config):
            events.append(event)

        # Should have events for stages + transitions
        assert len(events) > 0

    async def test_partial_pipeline(self):
        """Test running a subset of stages."""
        registry = PluginRegistry()
        register_default_stages(registry)
        builder = PipelineBuilder(registry=registry)
        short_sequence = ["literature_review", "plan_formulation"]
        graph = builder.build(stage_sequence=short_sequence)

        state = create_initial_state(
            session_id="partial-001",
            user_id="default",
            research_topic="Quick test",
            default_sequence=short_sequence,
        )
        config = {"configurable": {"thread_id": "partial-test"}}
        result = await graph.ainvoke(state, config=config)

        assert result["total_iterations"] == 2
        assert "literature_review" in result["completed_stages"]
        assert "plan_formulation" in result["completed_stages"]
```

- [ ] **Step 2: Create empty init file**

Create empty `tests/integration/__init__.py`.

- [ ] **Step 3: Run integration tests**

Run: `cd d:/GitHub/AgentLabX && uv run pytest tests/integration/ -v`
Expected: All PASS

- [ ] **Step 4: Run full test suite with lint**

Run: `cd d:/GitHub/AgentLabX && uv run ruff check agentlabx/ tests/ && uv run ruff format agentlabx/ tests/ && uv run pytest tests/ -v --tb=short`
Expected: All lint clean, all tests pass

- [ ] **Step 5: Commit**

```bash
git add tests/integration/ agentlabx/ tests/
git commit -m "test(integration): add end-to-end pipeline test — full 8-stage pipeline with session manager"
```

---

## Summary

After completing all 10 tasks, you will have:

- **LangGraph dependency** installed and wired
- **7 agent YAML configs** with differentiated memory scopes (phd_student, postdoc, ml_engineer, sw_engineer, professor, reviewers, pi_agent)
- **AgentConfigLoader** — loads YAML → AgentConfig, registers with plugin system
- **ConfigAgent** — generic agent instantiated from config, with mock inference for testing
- **ContextAssembler** — filters pipeline state by memory scope, formats for prompts
- **SessionManager** — lifecycle (create/start/pause/resume/complete), preferences (auto/HITL, per-stage controls), multi-user ready
- **StageRunner** — wraps BaseStage as a LangGraph-compatible node with error handling and iteration tracking
- **TransitionHandler** — priority-based routing (human override > limits > stage hints > default sequence)
- **8 skeleton stages** — all default research stages with mock outputs, registered via plugin system
- **PipelineBuilder** — assembles LangGraph StateGraph with dynamic routing, compiles with checkpointer
- **End-to-end integration test** — full 8-stage pipeline runs to completion

**What's deferred to Plan 3:** Real LLM inference (LiteLLM), real stage implementations, tool plugins, execution backends, storage backends.

---

## Addendum: Review Fixes (apply during execution)

### Fix A: StageRunner Must Return Reducer-Compatible State

**Applies to: Task 6 (StageRunner)**

`PipelineState` now uses `Annotated[list[X], operator.add]` reducers. When a node returns state with list fields, LangGraph will **append** those values. So StageRunner must NOT spread-copy accumulating fields — it should only return the fields it changes.

**Fix:** In `runner.py`, instead of `{**state, "errors": errors}`, return only the delta:
```python
# WRONG (clobbers accumulating fields):
return {**state, "errors": [error], "stage_iterations": stage_iters}

# RIGHT (return only changed fields — LangGraph merges via reducers):
return {"current_stage": self.stage.name, "stage_iterations": stage_iters,
        "total_iterations": total_iters, "errors": [error]}
```

The node should return a **partial dict** with only the keys it wants to update. LangGraph handles merging via reducer annotations.

### Fix B: Pipeline Builder Uses Command Pattern

**Applies to: Task 9 (PipelineBuilder)**

Replace the `_transition_decision` state hack with LangGraph's `Command(goto=...)` pattern. Each stage node returns a `Command` that routes to the transition node, and the transition node returns a `Command` that routes to the next stage or END.

**Key change in pipeline.py:**
```python
from langgraph.types import Command

# Stage node returns Command to go to transition
async def make_stage_node(state: PipelineState, _runner=runner) -> Command:
    updated = await _runner.run(state)
    return Command(update=updated, goto="transition")

# Transition node returns Command to go to next stage or END
def transition_node(state: PipelineState) -> Command:
    decision = transition_handler.decide(state, self.preferences)
    completed = list(state.get("completed_stages", []))
    current = state.get("current_stage", "")
    if current and current not in completed:
        completed.append(current)

    if decision.action == "complete" or decision.next_stage is None:
        return Command(
            update={"completed_stages": [current] if current else [],
                    "next_stage": None, "human_override": None},
            goto=END,
        )
    return Command(
        update={"completed_stages": [current] if current else [],
                "next_stage": None, "human_override": None},
        goto=decision.next_stage,
    )
```

This eliminates the undeclared `_transition_decision` key and is idiomatic LangGraph 0.4+.

---

### Task 11: Skeleton PI Agent

**Files:**
- Create: `agentlabx/agents/pi_agent.py`
- Create: `tests/agents/test_pi_agent.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/agents/test_pi_agent.py
from __future__ import annotations

import pytest

from agentlabx.agents.pi_agent import PIAgent, PIDecision
from agentlabx.core.session import SessionPreferences
from agentlabx.core.state import create_initial_state
from agentlabx.stages.transition import TransitionHandler


@pytest.fixture()
def pi_agent() -> PIAgent:
    handler = TransitionHandler(
        default_sequence=[
            "literature_review",
            "plan_formulation",
            "experimentation",
            "report_writing",
            "peer_review",
        ]
    )
    return PIAgent(
        transition_handler=handler,
        confidence_threshold=0.6,
    )


@pytest.fixture()
def base_state():
    return create_initial_state(
        session_id="s1",
        user_id="u1",
        research_topic="test",
        default_sequence=[
            "literature_review",
            "plan_formulation",
            "experimentation",
            "report_writing",
            "peer_review",
        ],
    )


class TestPIAgent:
    async def test_advance_with_high_confidence(self, pi_agent, base_state):
        base_state["current_stage"] = "literature_review"
        base_state["completed_stages"] = ["literature_review"]
        decision = await pi_agent.decide(base_state, SessionPreferences())
        assert decision.next_stage == "plan_formulation"
        assert decision.confidence >= 0.6

    async def test_fallback_on_low_confidence(self, pi_agent, base_state):
        """When PI is uncertain, fall back to default sequence."""
        base_state["current_stage"] = "literature_review"
        base_state["completed_stages"] = ["literature_review"]
        # With mock, confidence is always high — this tests the threshold mechanism
        pi_agent.confidence_threshold = 1.1  # Force fallback
        decision = await pi_agent.decide(base_state, SessionPreferences())
        # Should still work — falls back to TransitionHandler
        assert decision.next_stage is not None

    async def test_tracks_decision_history(self, pi_agent, base_state):
        base_state["current_stage"] = "literature_review"
        base_state["completed_stages"] = ["literature_review"]
        await pi_agent.decide(base_state, SessionPreferences())
        assert len(pi_agent.decision_history) == 1

    async def test_budget_warning_biases_completion(self, pi_agent, base_state):
        base_state["current_stage"] = "experimentation"
        base_state["completed_stages"] = [
            "literature_review", "plan_formulation", "experimentation",
        ]
        base_state["cost_tracker"].total_cost = 8.0  # 80% of default 10.0 ceiling
        decision = await pi_agent.decide(
            base_state,
            SessionPreferences(),
            budget_warning=True,
        )
        assert decision.next_stage is not None
        assert decision.budget_note is not None


class TestPIDecision:
    def test_create_decision(self):
        d = PIDecision(
            next_stage="experimentation",
            action="advance",
            reason="Research progressing well",
            confidence=0.85,
        )
        assert d.confidence == 0.85
        assert d.budget_note is None
        assert d.used_fallback is False
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd d:/GitHub/AgentLabX && uv run pytest tests/agents/test_pi_agent.py -v`
Expected: FAIL

- [ ] **Step 3: Implement pi_agent.py**

```python
# agentlabx/agents/pi_agent.py
"""PI Agent — intelligent transition handler with confidence scoring.

Skeleton implementation for Plan 2: uses rule-based TransitionHandler
as the decision engine, wraps it with confidence scoring and budget awareness.
Plan 3 replaces the mock LLM judgment with real inference.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel

from agentlabx.core.session import SessionPreferences
from agentlabx.core.state import PipelineState
from agentlabx.stages.transition import TransitionHandler


class PIDecision(BaseModel):
    """Decision made by the PI agent."""

    next_stage: str | None
    action: str
    reason: str
    confidence: float
    budget_note: str | None = None
    used_fallback: bool = False


class PIAgent:
    """Principal Investigator agent — makes transition decisions.

    Wraps TransitionHandler with:
    - Confidence scoring (mock in Plan 2, LLM-based in Plan 3)
    - Budget awareness (bias toward completion when budget is tight)
    - Decision history tracking for observability
    """

    def __init__(
        self,
        transition_handler: TransitionHandler,
        confidence_threshold: float = 0.6,
    ) -> None:
        self.transition_handler = transition_handler
        self.confidence_threshold = confidence_threshold
        self.decision_history: list[PIDecision] = []

    async def decide(
        self,
        state: PipelineState,
        preferences: SessionPreferences,
        budget_warning: bool = False,
    ) -> PIDecision:
        """Make a transition decision.

        In Plan 2 (mock), this wraps the rule-based TransitionHandler
        and adds a fixed confidence score. Plan 3 will add LLM-based
        judgment where the PI agent actually reasons about the research.
        """
        # Get rule-based decision
        rule_decision = self.transition_handler.decide(state, preferences)

        # Mock confidence (Plan 3: LLM evaluates and provides real confidence)
        confidence = 0.85

        # Budget awareness
        budget_note = None
        if budget_warning:
            budget_note = "Budget warning active — biasing toward completion"
            # In a real implementation, this would influence the LLM prompt

        # Check confidence threshold
        used_fallback = False
        if confidence < self.confidence_threshold:
            # Low confidence — fall back to default sequence
            used_fallback = True
            # The rule-based handler IS the fallback, so we use its decision as-is

        decision = PIDecision(
            next_stage=rule_decision.next_stage,
            action=rule_decision.action,
            reason=rule_decision.reason,
            confidence=confidence,
            budget_note=budget_note,
            used_fallback=used_fallback,
        )

        self.decision_history.append(decision)
        return decision
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd d:/GitHub/AgentLabX && uv run pytest tests/agents/test_pi_agent.py -v`
Expected: All PASS

- [ ] **Step 5: Commit**

```bash
git add agentlabx/agents/pi_agent.py tests/agents/test_pi_agent.py
git commit -m "feat(agents): add skeleton PI agent with confidence scoring and budget awareness"
```

---

### Task 12: Skeleton Lab Meeting Subgraph

**Files:**
- Create: `agentlabx/stages/lab_meeting.py`
- Create: `tests/stages/test_lab_meeting.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/stages/test_lab_meeting.py
from __future__ import annotations

import pytest

from agentlabx.core.state import StageError, create_initial_state
from agentlabx.stages.base import StageContext
from agentlabx.stages.lab_meeting import LabMeeting, LabMeetingTrigger


@pytest.fixture()
def state():
    return create_initial_state(
        session_id="s1", user_id="u1", research_topic="MATH benchmark"
    )


@pytest.fixture()
def context():
    return StageContext(settings={}, event_bus=None, registry=None)


class TestLabMeetingTrigger:
    def test_no_trigger_on_fresh_state(self, state):
        trigger = LabMeetingTrigger(consecutive_failures=3, score_plateau_rounds=2)
        assert trigger.should_trigger(state) is False

    def test_triggers_on_consecutive_failures(self, state):
        trigger = LabMeetingTrigger(consecutive_failures=3, score_plateau_rounds=2)
        from datetime import datetime, timezone

        for i in range(3):
            state["errors"] = list(state["errors"]) + [
                StageError(
                    stage="experimentation",
                    error_type="RuntimeError",
                    message=f"Failure {i}",
                    timestamp=datetime.now(timezone.utc),
                )
            ]
        assert trigger.should_trigger(state) is True

    def test_does_not_trigger_below_threshold(self, state):
        trigger = LabMeetingTrigger(consecutive_failures=3, score_plateau_rounds=2)
        from datetime import datetime, timezone

        state["errors"] = [
            StageError(
                stage="experimentation",
                error_type="RuntimeError",
                message="Failure",
                timestamp=datetime.now(timezone.utc),
            )
        ]
        assert trigger.should_trigger(state) is False


class TestLabMeeting:
    async def test_lab_meeting_runs(self, state, context):
        meeting = LabMeeting()
        result = await meeting.run(state, context)
        assert result.status == "done"
        assert "action_items" in result.output

    async def test_lab_meeting_returns_action_items(self, state, context):
        meeting = LabMeeting()
        result = await meeting.run(state, context)
        assert isinstance(result.output["action_items"], list)
        assert len(result.output["action_items"]) > 0
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd d:/GitHub/AgentLabX && uv run pytest tests/stages/test_lab_meeting.py -v`
Expected: FAIL

- [ ] **Step 3: Implement lab_meeting.py**

```python
# agentlabx/stages/lab_meeting.py
"""Lab meeting — cross-zone collaboration subgraph.

Skeleton implementation for Plan 2: returns mock discussion results.
Plan 3 replaces with multi-agent LLM dialogue.
"""

from __future__ import annotations

from agentlabx.core.state import PipelineState
from agentlabx.stages.base import BaseStage, StageContext, StageResult


class LabMeetingTrigger:
    """Determines whether a lab meeting should be triggered."""

    def __init__(
        self,
        consecutive_failures: int = 3,
        score_plateau_rounds: int = 2,
    ) -> None:
        self.consecutive_failures = consecutive_failures
        self.score_plateau_rounds = score_plateau_rounds

    def should_trigger(self, state: PipelineState) -> bool:
        """Check if a lab meeting should be triggered based on current state."""
        errors = state.get("errors", [])
        if len(errors) >= self.consecutive_failures:
            # Check if recent errors are consecutive (from the same stage)
            recent = errors[-self.consecutive_failures :]
            if all(e.stage == recent[0].stage for e in recent):
                return True
        return False


class LabMeeting(BaseStage):
    """Lab meeting — multi-agent discussion when a stage is stuck.

    Skeleton implementation: returns mock action items.
    Plan 3 will implement real multi-agent dialogue where:
    1. Stuck agent presents the problem
    2. Other agents contribute from their perspectives
    3. PI agent synthesizes action items
    4. Meeting summary distributed to agents' working memory
    """

    name = "lab_meeting"
    description = "Cross-zone collaboration meeting when a stage is stuck"
    required_agents = []  # Dynamically determined based on participants
    required_tools = []

    async def run(self, state: PipelineState, context: StageContext) -> StageResult:
        current_stage = state.get("current_stage", "unknown")
        topic = state.get("research_topic", "the research")

        return StageResult(
            output={
                "action_items": [
                    f"Review approach for {current_stage}",
                    "Consider alternative methodology",
                    "Check if data quality is sufficient",
                ],
                "discussion_summary": (
                    f"Lab meeting held to discuss challenges in {current_stage} "
                    f"for '{topic}'. Team suggested reviewing approach and "
                    f"considering alternatives."
                ),
                "participants": ["pi_agent", "postdoc", "phd_student", "ml_engineer"],
            },
            status="done",
            reason=f"Lab meeting complete — 3 action items for {current_stage}",
        )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd d:/GitHub/AgentLabX && uv run pytest tests/stages/test_lab_meeting.py -v`
Expected: All PASS

- [ ] **Step 5: Commit**

```bash
git add agentlabx/stages/lab_meeting.py tests/stages/test_lab_meeting.py
git commit -m "feat(stages): add skeleton lab meeting with trigger detection"
```

---

## Updated Summary

After completing all 12 tasks, you will have:

- **LangGraph dependency** installed and wired
- **7 agent YAML configs** with differentiated memory scopes
- **AgentConfigLoader** + **ConfigAgent** — YAML → agent instances with mock inference
- **ContextAssembler** — memory-scope-based state filtering
- **SessionManager** — lifecycle, preferences, per-stage HITL controls
- **StageRunner** — LangGraph-compatible node wrapper (reducer-aware)
- **TransitionHandler** — priority-based rule engine (human > limits > hints > sequence)
- **Skeleton PI Agent** — wraps TransitionHandler with confidence scoring and budget awareness
- **8 skeleton stages** + **lab meeting subgraph** — all registered via plugin system
- **PipelineBuilder** — LangGraph StateGraph using `Command` pattern for routing
- **End-to-end integration test** — full pipeline runs to completion

**What's deferred to Plan 3:** Real LLM inference via LiteLLM, PI agent with actual LLM judgment, real stage implementations with agent dialogue, real lab meeting multi-agent discussion, tool plugins, execution backends, storage backends.
