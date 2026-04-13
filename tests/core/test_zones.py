"""zone_for(): single source of zone resolution."""
import pytest
from agentlabx.core.registry import PluginRegistry
from agentlabx.core.zones import zone_for
from agentlabx.plugins import _builtin


@pytest.fixture
def registry() -> PluginRegistry:
    r = PluginRegistry()
    _builtin.register_builtin_plugins(r)
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
