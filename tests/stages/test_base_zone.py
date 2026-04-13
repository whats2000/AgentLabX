"""Every registered stage must declare a valid zone."""
import pytest
from agentlabx.core.registry import PluginRegistry, PluginType
from agentlabx.plugins._builtin import register_builtin_plugins

STAGE_ZONE_EXPECTATIONS = {
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


@pytest.fixture
def registry() -> PluginRegistry:
    r = PluginRegistry()
    register_builtin_plugins(r)
    return r


def test_every_registered_stage_declares_expected_zone(registry: PluginRegistry):
    for name, expected in STAGE_ZONE_EXPECTATIONS.items():
        cls = registry.resolve(PluginType.STAGE, name)
        assert cls.zone == expected, (
            f"{name}.zone={cls.zone!r} expected {expected!r}"
        )
