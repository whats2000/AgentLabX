"""Dependency injection container for the FastAPI server.

Holds singletons shared across requests:
- PluginRegistry (with all default agents, stages, tools registered)
- SessionManager (session lifecycle)
- Storage backend (SQLite by default)
- LLM provider
- PipelineExecutor (attached later in Task 6; None in Task 4)
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from agentlabx.agents.config_loader import AgentConfigLoader
from agentlabx.core.config import Settings
from agentlabx.core.registry import PluginRegistry, PluginType
from agentlabx.core.session import SessionManager
from agentlabx.providers.execution.subprocess_backend import SubprocessBackend
from agentlabx.providers.llm.base import BaseLLMProvider
from agentlabx.providers.llm.litellm_provider import LiteLLMProvider
from agentlabx.providers.llm.mock_provider import MockLLMProvider
from agentlabx.providers.storage.sqlite_backend import SQLiteBackend
from agentlabx.stages.skeleton import register_default_stages
from agentlabx.tools.arxiv_search import ArxivSearch
from agentlabx.tools.code_executor import CodeExecutor
from agentlabx.tools.github_search import GitHubSearch
from agentlabx.tools.hf_dataset_search import HFDatasetSearch
from agentlabx.tools.latex_compiler import LaTeXCompiler
from agentlabx.tools.semantic_scholar import SemanticScholarSearch

AGENT_CONFIGS_DIR = Path(__file__).parent.parent / "agents" / "configs"


class AppContext:
    """Shared runtime context for the FastAPI app. Lives for the app's lifetime."""

    def __init__(
        self,
        *,
        settings: Settings,
        registry: PluginRegistry,
        session_manager: SessionManager,
        storage: SQLiteBackend,
        llm_provider: BaseLLMProvider,
    ) -> None:
        self.settings = settings
        self.registry = registry
        self.session_manager = session_manager
        self.storage = storage
        self.llm_provider = llm_provider
        self.executor: Any = None  # Set in Task 6 (PipelineExecutor)


def build_default_registry() -> PluginRegistry:
    """Register all default plugins: agents, stages, stateless tools.

    Tools requiring backend injection (code_executor) are registered in
    build_app_context after their backend is constructed.
    """
    registry = PluginRegistry()

    # Agents from YAML
    loader = AgentConfigLoader()
    configs = loader.load_all(AGENT_CONFIGS_DIR)
    loader.register_all(configs, registry)

    # Stages (real + skeleton)
    register_default_stages(registry)

    # Stateless tools (instantiated on demand by _helpers.resolve_tool)
    registry.register(PluginType.TOOL, "arxiv_search", ArxivSearch)
    registry.register(PluginType.TOOL, "semantic_scholar", SemanticScholarSearch)
    registry.register(PluginType.TOOL, "hf_dataset_search", HFDatasetSearch)
    registry.register(PluginType.TOOL, "github_search", GitHubSearch)
    registry.register(PluginType.TOOL, "latex_compiler", LaTeXCompiler)

    return registry


async def build_app_context(
    *,
    settings: Settings | None = None,
    use_mock_llm: bool = False,
) -> AppContext:
    """Initialize all singletons for the app. Call once at startup."""
    if settings is None:
        settings = Settings()

    registry = build_default_registry()

    # Storage — ensure aiosqlite driver prefix
    db_url = settings.storage.database_url
    if db_url.startswith("sqlite:///") and "aiosqlite" not in db_url:
        db_url = db_url.replace("sqlite:///", "sqlite+aiosqlite:///", 1)

    storage = SQLiteBackend(
        database_url=db_url,
        artifacts_path=Path(settings.storage.artifacts_path),
    )
    await storage.initialize()

    # SessionManager wired to storage (persistence methods land in Task 10)
    session_manager = SessionManager(storage=storage)

    # Backend-dependent tools — construct now that execution backend exists
    execution_backend = SubprocessBackend()
    code_executor = CodeExecutor(backend=execution_backend)
    # Register as instance (resolve_tool handles both class and instance)
    registry.register(PluginType.TOOL, "code_executor", code_executor)

    # LLM provider: mock for CI/local dev, LiteLLM for production
    llm_provider: BaseLLMProvider = MockLLMProvider() if use_mock_llm else LiteLLMProvider()

    context = AppContext(
        settings=settings,
        registry=registry,
        session_manager=session_manager,
        storage=storage,
        llm_provider=llm_provider,
    )

    # PipelineExecutor (Task 6) — checkpoint DB sits next to artifacts_path
    from agentlabx.server.executor import PipelineExecutor

    checkpoint_db_path = Path(settings.storage.artifacts_path).parent / "checkpoints.db"
    executor = PipelineExecutor(
        registry=registry,
        session_manager=session_manager,
        llm_provider=llm_provider,
        checkpoint_db_path=str(checkpoint_db_path),
    )
    await executor.initialize()
    context.executor = executor

    return context
