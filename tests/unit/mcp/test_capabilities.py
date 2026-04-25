"""Unit tests for the capability taxonomy."""

from __future__ import annotations

from agentlabx.mcp.capabilities import (
    SEED_CAPABILITIES,
    CapabilitySet,
)


def test_capability_set_membership() -> None:
    cs = CapabilitySet.of("paper_search", "paper_fetch")
    assert "paper_search" in cs
    assert "paper_fetch" in cs
    assert "code_exec" not in cs
    assert len(cs) == 2


def test_capability_set_union_returns_new_set() -> None:
    a = CapabilitySet.of("paper_search")
    b = CapabilitySet.of("paper_fetch", "paper_search")
    merged = a.union(b)
    assert merged == CapabilitySet.of("paper_search", "paper_fetch")
    # originals unchanged
    assert a == CapabilitySet.of("paper_search")
    assert b == CapabilitySet.of("paper_fetch", "paper_search")


def test_capability_set_intersection() -> None:
    a = CapabilitySet.of("paper_search", "code_exec")
    b = CapabilitySet.of("paper_search", "web_fetch")
    assert a.intersection(b) == CapabilitySet.of("paper_search")


def test_capability_set_equality_and_hashable() -> None:
    a = CapabilitySet.of("paper_search", "code_exec")
    b = CapabilitySet.of("code_exec", "paper_search")
    assert a == b
    # hashable -> usable as dict key / set member
    bag: set[CapabilitySet] = {a, b}
    assert len(bag) == 1


def test_capability_set_is_satisfied_by() -> None:
    required = CapabilitySet.of("paper_search", "paper_fetch")
    assert required.is_satisfied_by(["paper_search", "paper_fetch", "extra"])
    assert not required.is_satisfied_by(["paper_search"])
    assert CapabilitySet().is_satisfied_by([])  # empty trivially satisfied


def test_seed_taxonomy_has_unique_members() -> None:
    assert len(SEED_CAPABILITIES) == len(set(SEED_CAPABILITIES))


def test_seed_taxonomy_contains_expected_members() -> None:
    expected = {
        "paper_search",
        "paper_fetch",
        "code_exec",
        "web_fetch",
        "web_browse",
        "fs_read",
        "fs_write",
        "memory_read",
        "memory_write",
    }
    assert set(SEED_CAPABILITIES) == expected
