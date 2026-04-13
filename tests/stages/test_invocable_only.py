"""invocable_only stages are in the registry but excluded from top-level wiring."""
from __future__ import annotations

import pytest

from agentlabx.core.pipeline import PipelineBuilder
from agentlabx.core.registry import PluginRegistry, PluginType
from agentlabx.core.session import SessionPreferences
from agentlabx.plugins._builtin import register_builtin_plugins
from agentlabx.stages.base import BaseStage
from agentlabx.stages.lab_meeting import LabMeeting


@pytest.fixture
def registry():
    r = PluginRegistry()
    register_builtin_plugins(r)
    return r


def test_basestage_default_invocable_only_is_false():
    assert BaseStage.invocable_only is False


def test_labmeeting_is_invocable_only():
    assert LabMeeting.invocable_only is True


def test_pipelinebuilder_skips_invocable_only_stages(registry):
    """Lab_meeting is registered but must not appear as a node in the top-level graph."""
    builder = PipelineBuilder(
        registry=registry, preferences=SessionPreferences()
    )
    seq = [
        "literature_review",
        "plan_formulation",
        "lab_meeting",
        "experimentation",
    ]
    graph = builder.build(stage_sequence=seq)
    node_ids = {n for n in graph.get_graph().nodes}
    assert "lab_meeting" not in node_ids
    assert "experimentation" in node_ids


def test_pipelinebuilder_does_not_skip_stages_with_invocable_only_false(registry):
    builder = PipelineBuilder(
        registry=registry, preferences=SessionPreferences()
    )
    seq = ["literature_review", "plan_formulation"]
    graph = builder.build(stage_sequence=seq)
    node_ids = {n for n in graph.get_graph().nodes}
    assert "literature_review" in node_ids
    assert "plan_formulation" in node_ids


def test_graph_mapper_surfaces_invocable_only_stages(registry):
    """Invocable-only stages appear in topology.subgraphs, not in topology.nodes."""
    from agentlabx.core.graph_mapper import build_topology

    builder = PipelineBuilder(
        registry=registry, preferences=SessionPreferences()
    )
    compiled = builder.build(stage_sequence=["literature_review", "plan_formulation"])
    state = {}  # topology shape with empty state

    topology = build_topology(compiled, state, registry=registry)
    node_ids = {n["id"] for n in topology["nodes"]}
    subgraph_ids = {s["id"] for s in topology["subgraphs"]}

    assert "lab_meeting" not in node_ids
    assert "lab_meeting" in subgraph_ids
    lm = next(s for s in topology["subgraphs"] if s["id"] == "lab_meeting")
    assert lm["kind"] == "invocable_only"
