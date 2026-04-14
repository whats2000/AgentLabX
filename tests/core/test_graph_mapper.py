# tests/core/test_graph_mapper.py
from datetime import UTC, datetime

import pytest
from agentlabx.core.graph_mapper import build_topology


class _N:
    def __init__(self, id): self.id = id


class _E:
    def __init__(self, s, t):
        self.source, self.target = s, t


class _G:
    def __init__(self):
        self.nodes = {
            n: _N(n) for n in ["literature_review", "plan_formulation", "__end__"]
        }

    def edges(self):
        return [
            _E("literature_review", "plan_formulation"),
            _E("plan_formulation", "__end__"),
        ]


class _C:
    def get_graph(self, xray=0):
        return _G()


def test_topology_reflects_skip_stages_and_current_cursor():
    state = {
        "current_stage": "plan_formulation",
        "completed_stages": ["literature_review"],
        "stage_iterations": {"plan_formulation": 2},
        "stage_config": {"skip_stages": ["peer_review"]},
    }
    topo = build_topology(_C(), state)

    assert "nodes" in topo and "edges" in topo and "cursor" in topo and "subgraphs" in topo

    ids = {n["id"] for n in topo["nodes"]}
    assert "plan_formulation" in ids

    pf = next(n for n in topo["nodes"] if n["id"] == "plan_formulation")
    assert pf["status"] == "active"
    assert pf["iteration_count"] == 2
    assert pf["skipped"] is False

    lr = next(n for n in topo["nodes"] if n["id"] == "literature_review")
    assert lr["status"] == "complete"

    # __end__ is a meta node
    end = next(n for n in topo["nodes"] if n["id"] == "__end__")
    assert end["type"] == "transition" or end["status"] == "meta"

    # Cursor on current stage
    assert topo["cursor"]["node_id"] == "plan_formulation"

    # At least the sequential edges we provided are in the output
    edge_pairs = {(e["from"], e["to"]) for e in topo["edges"]}
    assert ("literature_review", "plan_formulation") in edge_pairs


def test_topology_marks_skipped_node_when_in_state_config():
    """When a stage is in skip_stages AND is also a node in the graph,
    mark it skipped=True with status='skipped'."""

    class _GWithPeer:
        def __init__(self):
            self.nodes = {n: _N(n) for n in ["plan_formulation", "peer_review", "__end__"]}

        def edges(self):
            return [_E("plan_formulation", "peer_review"), _E("peer_review", "__end__")]

    class _CWithPeer:
        def get_graph(self, xray=0):
            return _GWithPeer()

    state = {
        "current_stage": "plan_formulation",
        "completed_stages": [],
        "stage_iterations": {},
        "stage_config": {"skip_stages": ["peer_review"]},
    }
    topo = build_topology(_CWithPeer(), state)
    pr = next(n for n in topo["nodes"] if n["id"] == "peer_review")
    assert pr["status"] == "skipped"
    assert pr["skipped"] is True


def test_topology_cursor_none_when_no_current_stage():
    state = {
        "current_stage": None,
        "completed_stages": [],
        "stage_iterations": {},
        "stage_config": {},
    }
    topo = build_topology(_C(), state)
    assert topo["cursor"] is None


def test_topology_overlays_backtrack_from_transition_log():
    """A transition in transition_log with no matching sequential edge should
    appear in edges with kind='backtrack'."""
    state = {
        "current_stage": "plan_formulation",
        "completed_stages": ["literature_review", "plan_formulation"],
        "stage_iterations": {},
        "stage_config": {},
        "transition_log": [
            {"from_stage": "plan_formulation", "to_stage": "literature_review",
             "reason": "need more papers"}
        ],
    }
    topo = build_topology(_C(), state)
    backtrack = [e for e in topo["edges"] if e["kind"] == "backtrack"]
    assert len(backtrack) == 1
    assert backtrack[0]["from"] == "plan_formulation"
    assert backtrack[0]["to"] == "literature_review"
    assert "more papers" in (backtrack[0].get("reason") or "")


def test_topology_overlays_backtrack_from_transition_model():
    """Transition model entries in transition_log are accepted."""
    from agentlabx.core.state import Transition

    state = {
        "current_stage": "plan_formulation",
        "completed_stages": ["literature_review", "plan_formulation"],
        "stage_iterations": {},
        "stage_config": {},
        "transition_log": [
            Transition(
                from_stage="plan_formulation",
                to_stage="literature_review",
                reason="need more papers",
                triggered_by="agent",
                timestamp=datetime.now(UTC),
            )
        ],
    }
    topo = build_topology(_C(), state)
    backtrack = [e for e in topo["edges"] if e["kind"] == "backtrack"]
    assert len(backtrack) == 1
    assert backtrack[0]["from"] == "plan_formulation"
    assert backtrack[0]["to"] == "literature_review"
    assert "more papers" in (backtrack[0].get("reason") or "")


@pytest.fixture
def compiled_graph_fixture():
    from agentlabx.core.pipeline import PipelineBuilder
    from agentlabx.core.registry import PluginRegistry
    from agentlabx.plugins._builtin import register_builtin_plugins
    r = PluginRegistry()
    register_builtin_plugins(r)
    return PipelineBuilder(registry=r).build(
        stage_sequence=["literature_review", "plan_formulation", "experimentation"]
    )


def test_graph_mapper_surfaces_backtrack_attempts_on_edges(
    compiled_graph_fixture,
):
    from agentlabx.core.state import create_initial_state

    state = create_initial_state(
        session_id="s1", user_id="u1", research_topic="t"
    )
    state["backtrack_attempts"] = {"experimentation->literature_review": 2}

    topo = build_topology(compiled_graph_fixture, state)

    backtrack_edges = [
        e for e in topo["edges"]
        if e.get("from") == "experimentation"
        and e.get("to") == "literature_review"
    ]
    assert backtrack_edges, "expected a backtrack edge to be surfaced"
    assert backtrack_edges[0].get("attempts") == 2
    assert backtrack_edges[0].get("kind") == "backtrack"


@pytest.fixture
def registry_fixture():
    from agentlabx.core.registry import PluginRegistry
    from agentlabx.plugins._builtin import register_builtin_plugins
    r = PluginRegistry()
    register_builtin_plugins(r)
    return r


def test_graph_mapper_includes_cursor_internal_node(compiled_graph_fixture):
    """cursor.internal_node populated from state."""
    from agentlabx.core.state import create_initial_state

    state = create_initial_state(session_id="s1", user_id="u1", research_topic="t")
    state["current_stage"] = "literature_review"
    state["current_stage_internal_node"] = "work"
    topology = build_topology(compiled_graph_fixture, state)
    assert topology["cursor"]["internal_node"] == "work"
    assert topology["cursor"]["meeting_node"] is None


def test_graph_mapper_synthesizes_backtrack_edges(compiled_graph_fixture):
    """state['backtrack_attempts'] → edges with kind=backtrack."""
    from agentlabx.core.state import create_initial_state

    state = create_initial_state(session_id="s1", user_id="u1", research_topic="t")
    state["backtrack_attempts"] = {
        "experimentation->literature_review": 2,
        "plan_formulation->experimentation": 1,
    }
    topology = build_topology(compiled_graph_fixture, state)
    bt_edges = [e for e in topology["edges"] if e.get("kind") == "backtrack"]
    assert len(bt_edges) == 2
    assert {(e["from"], e["to"], e["attempts"]) for e in bt_edges} == {
        ("experimentation", "literature_review", 2),
        ("plan_formulation", "experimentation", 1),
    }


def test_graph_mapper_extracts_active_stage_subgraph(
    compiled_graph_fixture, registry_fixture
):
    """subgraphs[] includes active stage's compiled subgraph when registry given."""
    from agentlabx.core.state import create_initial_state

    state = create_initial_state(session_id="s1", user_id="u1", research_topic="t")
    state["current_stage"] = "literature_review"
    topology = build_topology(compiled_graph_fixture, state, registry=registry_fixture)
    stage_sub = next(
        (s for s in topology["subgraphs"] if s["id"] == "literature_review"),
        None,
    )
    assert stage_sub is not None
    assert stage_sub["kind"] == "stage_subgraph"
    assert len(stage_sub["nodes"]) >= 5  # enter, stage_plan, work, evaluate, decide
