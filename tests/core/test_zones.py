"""zone_for() and cross_zone(): single source of zone resolution."""
import pytest
from agentlabx.core.registry import PluginRegistry
from agentlabx.core.zones import cross_zone, zone_for
from agentlabx.plugins._builtin import register_builtin_plugins


@pytest.fixture
def registry() -> PluginRegistry:
    r = PluginRegistry()
    register_builtin_plugins(r)
    return r


def test_zone_for_reads_class_attribute_when_registry_given(registry):
    assert zone_for("literature_review", registry) == "discovery"
    assert zone_for("experimentation", registry) == "implementation"
    assert zone_for("peer_review", registry) == "synthesis"
    assert zone_for("lab_meeting", registry) is None


def test_zone_for_falls_back_to_hardcoded_map_when_registry_none():
    assert zone_for("literature_review", None) == "discovery"
    assert zone_for("experimentation", None) == "implementation"
    assert zone_for("peer_review", None) == "synthesis"


def test_zone_for_returns_none_on_unknown_stage():
    assert zone_for("not_a_stage", None) is None


def test_cross_zone_same_zone_is_false():
    assert cross_zone("literature_review", "plan_formulation") is False
    assert cross_zone("data_exploration", "experimentation") is False


def test_cross_zone_different_zones_is_true():
    assert cross_zone("literature_review", "experimentation") is True
    assert cross_zone("experimentation", "report_writing") is True


def test_cross_zone_none_zone_is_conservative_true():
    # lab_meeting has zone=None → always cross-zone so HITL can gate it
    assert cross_zone("lab_meeting", "experimentation") is True
    assert cross_zone("experimentation", "lab_meeting") is True


def test_cross_zone_unknown_stage_is_true():
    # Conservative: unknown origin/target is treated as cross-zone
    assert cross_zone("unknown", "literature_review") is True


def test_fallback_zones_match_every_registered_stage(registry):
    """Adding a new stage and forgetting to update _FALLBACK_ZONES would
    silently produce None for registry-less callers. This test catches it."""
    from agentlabx.core.registry import PluginType
    from agentlabx.core.zones import _FALLBACK_ZONES

    for name, expected in _FALLBACK_ZONES.items():
        cls = registry.resolve(PluginType.STAGE, name)
        assert cls.zone == expected, (
            f"class {cls.__name__}.zone={cls.zone!r} but "
            f"_FALLBACK_ZONES[{name!r}]={expected!r}"
        )


def test_fallback_zones_covers_every_registered_stage(registry):
    """Every registered stage must have an entry in _FALLBACK_ZONES."""
    from agentlabx.core.registry import PluginType
    from agentlabx.core.zones import _FALLBACK_ZONES
    from agentlabx.plugins._builtin import _BUILTIN_STAGES

    for cls in _BUILTIN_STAGES:
        assert cls.name in _FALLBACK_ZONES, (
            f"registered stage {cls.name!r} missing from _FALLBACK_ZONES"
        )
