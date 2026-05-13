"""Capability taxonomy.

Capabilities are the abstract permissions a stage declares it needs (e.g.
``paper_search``, ``code_exec``). Each MCP tool, at registration time, is
tagged with the capabilities it provides. The dispatcher reads the tool's
own ``capabilities`` tuple at invoke time to cross-check the caller's
declared capability — there is no separate resolver indirection.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field

SEED_CAPABILITIES: tuple[str, ...] = (
    "paper_search",
    "paper_fetch",
    "code_exec",
    "web_fetch",
    "web_browse",
    "fs_read",
    "fs_write",
    "memory_read",
    "memory_write",
)
"""Frozen seed taxonomy of capabilities recognised at A3 launch.

This list is intentionally small; later stages may extend it. Tools may
declare capabilities outside this set, but doing so should produce a
warning in the host (handled in Task 4) — at the protocol layer, the seed
is purely a reference.
"""

KNOWN_UNCOVERED_CAPABILITIES: frozenset[str] = frozenset({"web_browse"})
"""Capabilities in :data:`SEED_CAPABILITIES` that are intentionally NOT served
by any A3 bundle.

A3's browser bundle ships only ``web_fetch`` (HTTP GET); full headless-browser
interaction (``web_browse``) is deferred to a future Playwright/Puppeteer-based
bundle per the plan's "Out of scope" section. The bundled-server smoke test
asserts that every other seeded capability is provided by at least one
*started* bundle, so a silent regression in coverage fails CI loudly.
"""


@dataclass(frozen=True, slots=True)
class CapabilitySet:
    """Immutable, hashable set of capability names.

    Thin wrapper around :class:`frozenset` so callers can treat capability
    bundles as first-class values (use them as dict keys, compare for
    equality, etc.) without exposing mutable set semantics.
    """

    members: frozenset[str] = field(default_factory=frozenset)

    @classmethod
    def of(cls, *names: str) -> CapabilitySet:
        """Construct a set from positional capability names."""

        return cls(frozenset(names))

    @classmethod
    def from_iterable(cls, names: Iterable[str]) -> CapabilitySet:
        """Construct a set from any iterable of capability names."""

        return cls(frozenset(names))

    def __contains__(self, name: object) -> bool:
        return name in self.members

    def __iter__(self) -> Iterable[str]:
        return iter(self.members)

    def __len__(self) -> int:
        return len(self.members)

    def union(self, other: CapabilitySet) -> CapabilitySet:
        """Return a new set containing capabilities from both."""

        return CapabilitySet(self.members | other.members)

    def intersection(self, other: CapabilitySet) -> CapabilitySet:
        """Return a new set with only the capabilities present in both."""

        return CapabilitySet(self.members & other.members)

    def is_satisfied_by(self, declared: Iterable[str]) -> bool:
        """Return True iff every capability in this set appears in ``declared``."""

        declared_set = frozenset(declared)
        return self.members.issubset(declared_set)


__all__ = [
    "KNOWN_UNCOVERED_CAPABILITIES",
    "SEED_CAPABILITIES",
    "CapabilitySet",
]
