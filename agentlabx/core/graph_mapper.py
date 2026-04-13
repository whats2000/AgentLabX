"""LangGraph compiled graph + PipelineState → owned topology mapper.

Produces the `{nodes, edges, cursor, subgraphs}` shape that the web UI consumes
via `/api/sessions/{id}/graph`. Insulates the frontend from LangGraph's internal
graph structure and overlays runtime state (completed stages, current cursor,
skipped stages, iteration counts, backtrack transitions).
"""

from __future__ import annotations

from typing import Any

STAGE_ZONES = {
    "literature_review": "discovery",
    "plan_formulation": "discovery",
    "data_exploration": "implementation",
    "data_preparation": "implementation",
    "experimentation": "implementation",
    "results_interpretation": "synthesis",
    "report_writing": "synthesis",
    "peer_review": "synthesis",
}

META_NODE_IDS = ("__start__", "__end__", "transition")


def build_topology(compiled_graph, state: dict) -> dict[str, Any]:
    """Return the owned graph topology shape for the given state.

    Args:
        compiled_graph: a LangGraph compiled graph. Must have .get_graph()
            returning an object with .nodes (iterable of node ids) and
            .edges() returning iterable of edge objects with .source/.target.
        state: the current pipeline state dict.

    Returns:
        dict with keys: nodes, edges, cursor, subgraphs.
    """
    g = compiled_graph.get_graph()
    skip = set((state.get("stage_config") or {}).get("skip_stages") or [])
    completed = set(state.get("completed_stages") or [])
    current = state.get("current_stage")
    iters = state.get("stage_iterations") or {}

    def _status(node_id: str) -> str:
        if node_id in skip:
            return "skipped"
        if node_id in completed:
            return "complete"
        if node_id == current:
            return "active"
        return "pending"

    nodes: list[dict[str, Any]] = []
    for nid in g.nodes:
        if nid in META_NODE_IDS:
            nodes.append(
                {
                    "id": nid,
                    "type": "transition",
                    "label": nid,
                    "zone": None,
                    "status": "meta",
                    "iteration_count": 0,
                    "skipped": False,
                }
            )
            continue
        nodes.append(
            {
                "id": nid,
                "type": "stage",
                "label": _pretty(nid),
                "zone": STAGE_ZONES.get(nid),
                "status": _status(nid),
                "iteration_count": int(iters.get(nid, 0)),
                "skipped": nid in skip,
            }
        )

    # LangGraph's get_graph() returns a Graph whose .edges is a plain list;
    # unit-test mocks may expose it as a callable. Support both.
    raw_edges = g.edges() if callable(g.edges) else g.edges
    edges: list[dict[str, Any]] = [
        {"from": e.source, "to": e.target, "kind": "sequential", "reason": None} for e in raw_edges
    ]

    # Overlay backtracks from transition_log when they're not already edges.
    for t in state.get("transition_log") or []:
        s = t.get("from_stage")
        d = t.get("to_stage")
        if not s or not d:
            continue
        if _edge_idx(edges, s, d) == -1:
            edges.append(
                {
                    "from": s,
                    "to": d,
                    "kind": "backtrack",
                    "reason": t.get("reason"),
                }
            )

    cursor: dict[str, Any] | None = None
    if current:
        cursor = {"node_id": current, "agent": None, "started_at": None}

    return {"nodes": nodes, "edges": edges, "cursor": cursor, "subgraphs": []}


def _pretty(node_id: str) -> str:
    """literature_review → Literature Review."""
    return node_id.replace("_", " ").title()


def _edge_idx(edges: list[dict], source: str, target: str) -> int:
    for i, e in enumerate(edges):
        if e["from"] == source and e["to"] == target:
            return i
    return -1
