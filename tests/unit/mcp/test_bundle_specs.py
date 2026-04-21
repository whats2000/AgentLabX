"""Contract tests for the six A3 launch-spec bundles.

Each bundle ships a ``spec()`` callable returning an :class:`MCPServerSpec`.
This module pins the structural identity of each spec so accidental drift
(e.g. renaming a capability, dropping an env-slot ref, flipping the scope)
fails loudly at unit-test time rather than at boot.
"""

from __future__ import annotations

from types import ModuleType

import pytest

from agentlabx.mcp.bundles import (
    arxiv,
    browser,
    code_execution,
    filesystem,
    memory_server,
    semantic_scholar,
)
from agentlabx.mcp.capabilities import SEED_CAPABILITIES
from agentlabx.mcp.protocol import MCPServerSpec

_SEED_SET: frozenset[str] = frozenset(SEED_CAPABILITIES)


_EXPECTED: tuple[tuple[ModuleType, str, str, str, tuple[str, ...]], ...] = (
    (filesystem, "filesystem", "admin", "stdio", ("fs_read", "fs_write")),
    (arxiv, "arxiv", "admin", "stdio", ("paper_search", "paper_fetch")),
    (semantic_scholar, "semantic_scholar", "admin", "stdio", ("paper_search",)),
    (browser, "browser", "admin", "stdio", ("web_fetch",)),
    (code_execution, "code_execution", "admin", "stdio", ("code_exec",)),
    (memory_server, "memory", "admin", "inprocess", ("memory_read", "memory_write")),
)


@pytest.mark.parametrize(
    ("module", "expected_name", "expected_scope", "expected_transport", "expected_caps"),
    _EXPECTED,
    ids=[entry[1] for entry in _EXPECTED],
)
def test_bundle_spec_contract(
    module: ModuleType,
    expected_name: str,
    expected_scope: str,
    expected_transport: str,
    expected_caps: tuple[str, ...],
) -> None:
    spec = module.spec()
    assert isinstance(spec, MCPServerSpec)
    assert spec.name == expected_name
    assert spec.scope == expected_scope
    assert spec.transport == expected_transport
    assert spec.declared_capabilities == expected_caps
    # Declared capabilities must be a non-empty subset of the seed taxonomy.
    assert len(spec.declared_capabilities) > 0
    assert set(spec.declared_capabilities).issubset(_SEED_SET)


def test_semantic_scholar_declares_api_key_slot() -> None:
    spec = semantic_scholar.spec()
    assert spec.env_slot_refs == ("semantic_scholar_api_key",)


def test_memory_bundle_inprocess_key_matches_factory_registry() -> None:
    """The seed loop wires factories by ``inprocess_key``; pin the value."""

    spec = memory_server.spec()
    assert spec.inprocess_key == "memory_server"
    assert spec.transport == "inprocess"
    assert spec.command is None


@pytest.mark.parametrize(
    ("module", "env_var", "override"),
    [
        (filesystem, "AGENTLABX_BUNDLE_FILESYSTEM_COMMAND", "my-fs --root /tmp"),
        (arxiv, "AGENTLABX_BUNDLE_ARXIV_COMMAND", "my-arxiv-cmd --port 9000"),
        (
            semantic_scholar,
            "AGENTLABX_BUNDLE_SEMANTIC_SCHOLAR_COMMAND",
            "uvx my-fork-mcp-semanticscholar",
        ),
        (
            browser,
            "AGENTLABX_BUNDLE_BROWSER_COMMAND",
            "uvx --from mcp-server-fetch python -m mcp_server_fetch",
        ),
        (
            code_execution,
            "AGENTLABX_BUNDLE_CODE_EXECUTION_COMMAND",
            "python -m alt.code_executor",
        ),
    ],
    ids=["filesystem", "arxiv", "semantic_scholar", "browser", "code_execution"],
)
def test_command_override_env_takes_effect(
    module: ModuleType,
    env_var: str,
    override: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(env_var, override)
    spec = module.spec()
    assert spec.command == tuple(override.split())
