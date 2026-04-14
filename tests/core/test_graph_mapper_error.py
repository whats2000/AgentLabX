"""Subgraph extraction errors surface via an `error` field + logger warning."""
from __future__ import annotations

import logging

import pytest

from agentlabx.core.graph_mapper import build_topology
from agentlabx.core.registry import PluginRegistry
from agentlabx.core.state import create_initial_state
from agentlabx.plugins._builtin import register_builtin_plugins


@pytest.fixture
def registry():
    r = PluginRegistry()
    register_builtin_plugins(r)
    return r


class _MockCompiledGraph:
    """Minimal fake for build_topology — provides get_graph()."""
    class _G:
        def __init__(self):
            self.nodes = {"__start__": None, "__end__": None, "literature_review": None}
            self._edges = []
        def edges(self):
            return self._edges
    def get_graph(self):
        return self._G()


def test_graph_mapper_surfaces_subgraph_extraction_error(registry, monkeypatch, caplog):
    """When subgraph extraction raises, the subgraph entry carries an `error` field."""
    # Force StageSubgraphBuilder.compile to raise
    def raising_compile(self, stage):
        raise RuntimeError("synthetic compile failure")

    monkeypatch.setattr(
        "agentlabx.stages.subgraph.StageSubgraphBuilder.compile", raising_compile
    )

    state = create_initial_state(session_id="s1", user_id="u1", research_topic="t")
    state["current_stage"] = "literature_review"

    with caplog.at_level(logging.WARNING):
        topology = build_topology(_MockCompiledGraph(), state, registry=registry)

    # Find the active-stage subgraph entry in the response
    active_subgraph = next(
        (s for s in topology["subgraphs"] if s["id"] == "literature_review"),
        None,
    )
    assert active_subgraph is not None, (
        f"Expected subgraph entry for active stage; got: {topology['subgraphs']}"
    )
    assert active_subgraph.get("error") is not None
    assert "synthetic compile failure" in active_subgraph["error"]

    # Logger captured a warning
    warnings = [
        r for r in caplog.records
        if r.levelname == "WARNING" and "subgraph extraction" in r.message.lower()
    ]
    assert warnings, (
        f"Expected at least one WARNING log about subgraph extraction; got "
        f"{[(r.levelname, r.message) for r in caplog.records]}"
    )


def test_graph_mapper_no_error_field_on_successful_extraction(registry):
    """Normal extraction path produces a subgraph entry with NO error field."""
    state = create_initial_state(session_id="s1", user_id="u1", research_topic="t")
    state["current_stage"] = "literature_review"
    topology = build_topology(_MockCompiledGraph(), state, registry=registry)
    active = next(
        (s for s in topology["subgraphs"] if s["id"] == "literature_review"),
        None,
    )
    if active is not None:
        # Successful extraction — no error key
        assert "error" not in active or active["error"] is None
