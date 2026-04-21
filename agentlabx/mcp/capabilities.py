"""Capability taxonomy + resolver.

Capabilities are the abstract permissions a stage declares it needs (e.g.
``paper_search``, ``code_exec``). Each MCP tool, at registration time, is
tagged with the capabilities it provides. The dispatcher uses
:class:`CapabilityResolver` to look up which capabilities a given
``(server, tool)`` pair offers, and the gate compares that against the
stage's allow-list.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field

from agentlabx.mcp.protocol import ToolNotFound

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


class CapabilityResolver:
    """Lookup table from ``(server, tool)`` to the tool's capability set.

    Built at server-registration time from each
    :class:`agentlabx.mcp.protocol.ToolDescriptor` 's ``capabilities`` tuple.
    """

    def __init__(self, mapping: Mapping[tuple[str, str], CapabilitySet] | None = None) -> None:
        self._mapping: dict[tuple[str, str], CapabilitySet] = (
            dict(mapping) if mapping is not None else {}
        )

    def register(self, server: str, tool: str, capabilities: CapabilitySet) -> None:
        """Add or replace the capability set for one ``(server, tool)`` pair."""

        self._mapping[(server, tool)] = capabilities

    def for_tool(self, server: str, tool: str) -> CapabilitySet:
        """Return the capability set declared for ``(server, tool)``.

        Raises :class:`ToolNotFound` if no entry has been registered.
        """

        try:
            return self._mapping[(server, tool)]
        except KeyError as exc:
            raise ToolNotFound(server, tool) from exc

    def __len__(self) -> int:
        return len(self._mapping)

    def __contains__(self, key: object) -> bool:
        return key in self._mapping


__all__ = [
    "SEED_CAPABILITIES",
    "CapabilityResolver",
    "CapabilitySet",
]
