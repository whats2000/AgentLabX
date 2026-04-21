"""Static capability-coverage assertion across all A3 bundles.

Iterates the *spec-declared* capabilities of every bundle module and asserts
that every member of ``SEED_CAPABILITIES - KNOWN_UNCOVERED_CAPABILITIES`` is
provided by at least one bundle.

This is intentionally a unit-style test: it never launches subprocesses, never
opens a DB, and never depends on Docker / npx / uvx being installed. The
runtime-wiring smoke checks live alongside in
``tests/integration/mcp/test_bundled_smoke.py``.
"""

from __future__ import annotations

from agentlabx.mcp.bundles import (
    arxiv,
    browser,
    code_execution,
    filesystem,
    memory_server,
    semantic_scholar,
)
from agentlabx.mcp.capabilities import (
    KNOWN_UNCOVERED_CAPABILITIES,
    SEED_CAPABILITIES,
)


def test_seed_capabilities_covered_by_bundle_specs() -> None:
    """Every seeded capability (minus the documented uncovered set) is declared
    by at least one bundle's launch spec.

    Failing this means either (a) a bundle regressed its declared capabilities,
    or (b) someone added a seed capability without a backing bundle and
    without recording it in ``KNOWN_UNCOVERED_CAPABILITIES``.
    """

    bundles = [
        arxiv,
        browser,
        code_execution,
        filesystem,
        memory_server,
        semantic_scholar,
    ]
    declared: set[str] = set()
    for module in bundles:
        declared.update(module.spec().declared_capabilities)

    expected = set(SEED_CAPABILITIES) - set(KNOWN_UNCOVERED_CAPABILITIES)
    missing = expected - declared
    assert not missing, f"capabilities not covered by any bundle: {sorted(missing)}"


def test_known_uncovered_capabilities_are_actually_uncovered() -> None:
    """Sanity guard: the 'uncovered' set must not silently contain a capability
    that some bundle now provides — that would mask a real coverage signal.
    """

    bundles = [
        arxiv,
        browser,
        code_execution,
        filesystem,
        memory_server,
        semantic_scholar,
    ]
    declared: set[str] = set()
    for module in bundles:
        declared.update(module.spec().declared_capabilities)

    overlap = set(KNOWN_UNCOVERED_CAPABILITIES) & declared
    assert not overlap, (
        f"capabilities listed as uncovered are actually provided by a bundle: {sorted(overlap)}"
    )
