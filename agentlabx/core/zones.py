"""Single source of zone resolution for stages.

Stages declare `zone` as a ClassVar on BaseStage subclasses. This module
resolves a stage name to its zone, preferring the class attribute (via the
registry) but falling back to a hardcoded map for registry-less callers
(tests, /graph fixtures, any code that can't easily plumb a registry).
"""
from __future__ import annotations

from typing import TYPE_CHECKING, Literal

if TYPE_CHECKING:
    from agentlabx.core.registry import PluginRegistry

ZoneName = Literal["discovery", "implementation", "synthesis"]

_FALLBACK_ZONES: dict[str, ZoneName | None] = {
    "literature_review": "discovery",
    "plan_formulation": "discovery",
    "data_exploration": "implementation",
    "data_preparation": "implementation",
    "experimentation": "implementation",
    "results_interpretation": "synthesis",
    "report_writing": "synthesis",
    "peer_review": "synthesis",
    "lab_meeting": None,
}


def zone_for(stage_name: str, registry: PluginRegistry | None = None) -> ZoneName | None:
    """Return the zone declared by `stage_name`, or None for special/unknown."""
    if registry is not None:
        try:
            from agentlabx.core.registry import PluginType

            cls = registry.resolve(PluginType.STAGE, stage_name)
            return getattr(cls, "zone", None)
        except KeyError:
            pass
    return _FALLBACK_ZONES.get(stage_name)


def cross_zone(origin: str, target: str, registry: PluginRegistry | None = None) -> bool:
    """True iff origin and target declare different non-null zones, OR either is None."""
    a = zone_for(origin, registry)
    b = zone_for(target, registry)
    if a is None or b is None:
        return True
    return a != b
