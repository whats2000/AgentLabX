"""LangGraph compiled graph + PipelineState → owned topology mapper.

Produces the `{nodes, edges, cursor, subgraphs}` shape that the web UI consumes
via `/api/sessions/{id}/graph`. Insulates the frontend from LangGraph's internal
graph structure and overlays runtime state (completed stages, current cursor,
skipped stages, iteration counts, backtrack transitions).
"""

from __future__ import annotations

import logging
from typing import Any

from agentlabx.core.zones import zone_for

logger = logging.getLogger(__name__)

META_NODE_IDS = ("__start__", "__end__", "transition")


def _iter_registered_stages(registry):
    """Yield (name, class) for every stage in the registry.

    Uses PluginRegistry.list_plugins(PluginType.STAGE) which returns a
    dict[str, Any] snapshot of registered stage classes.
    """
    from agentlabx.core.registry import PluginType

    yield from registry.list_plugins(PluginType.STAGE).items()


def build_topology(compiled_graph, state: dict, registry=None) -> dict[str, Any]:
    """Return the owned graph topology shape for the given state.

    Args:
        compiled_graph: a LangGraph compiled graph. Must have .get_graph()
            returning an object with .nodes (iterable of node ids) and
            .edges() returning iterable of edge objects with .source/.target.
        state: the current pipeline state dict.
        registry: optional PluginRegistry for zone resolution. When provided,
            zones are read from the stage class attribute; otherwise the
            hardcoded fallback map in zones.py is used.

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
                "zone": zone_for(nid, registry),
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

    # Overlay backtrack attempt counters from state["backtrack_attempts"].
    # Each key is "src->dst"; annotate matching edge or append a new one.
    attempts_map = state.get("backtrack_attempts") or {}
    for edge_key, count in attempts_map.items():
        try:
            src, dst = edge_key.split("->")
        except ValueError:
            continue
        existing = next(
            (e for e in edges if e.get("from") == src and e.get("to") == dst),
            None,
        )
        if existing is not None:
            existing["attempts"] = count
            existing["kind"] = "backtrack"
        else:
            edges.append({
                "from": src,
                "to": dst,
                "kind": "backtrack",
                "attempts": count,
                "reason": None,
            })

    cursor: dict[str, Any] | None = None
    if current:
        cursor = {
            "node_id": current,
            "internal_node": state.get("current_stage_internal_node"),
            "meeting_node": state.get("current_meeting_node"),
            "agent": None,  # reserved for future use
            "started_at": None,
        }

    # Invocable-only stages (e.g., lab_meeting, §5.5) are registered but not
    # wired into the top-level graph. Surface them here so the frontend can
    # discover them for the recursive subgraph drawer (spec §8.2). The
    # nodes/edges arrays stay empty in Plan 7B; Plan 7D renders the subgraph
    # internals from the compiled stage's get_graph() at runtime.
    subgraphs: list[dict[str, object]] = []
    if registry is not None:
        for name, cls in _iter_registered_stages(registry):
            if getattr(cls, "invocable_only", False):
                subgraphs.append({
                    "id": name,
                    "kind": "invocable_only",
                    "label": getattr(cls, "description", name),
                    "nodes": [],
                    "edges": [],
                })

    # Enrich subgraphs[] with the active stage's compiled subgraph topology.
    # Only for non-invocable stages (invocable_only stages have their own entry
    # above). Fail-soft: missing subgraph data is survivable.
    if registry is not None and current:
        try:
            from agentlabx.core.registry import PluginType
            cls = registry.resolve(PluginType.STAGE, current)
            if not getattr(cls, "invocable_only", False):
                from agentlabx.stages.subgraph import StageSubgraphBuilder

                stage_instance = cls()
                compiled = StageSubgraphBuilder().compile(stage_instance)
                sub_g = compiled.get_graph()
                # sub_g.nodes is a dict; keys are node id strings
                sub_nodes = [
                    {"id": nid, "type": "internal"}
                    for nid in sub_g.nodes
                ]
                # sub_g.edges is a plain list of Edge namedtuples with .source / .target
                sub_edges = [
                    {"from": e.source, "to": e.target}
                    for e in sub_g.edges
                    if hasattr(e, "source") and hasattr(e, "target")
                ]
                subgraphs.append({
                    "id": current,
                    "kind": "stage_subgraph",
                    "label": current,
                    "nodes": sub_nodes,
                    "edges": sub_edges,
                })
        except Exception as exc:
            logger.warning(
                "Subgraph extraction failed for stage %s: %s",
                current, exc, exc_info=True,
            )
            subgraphs.append({
                "id": current,
                "kind": "stage_subgraph",
                "label": current,
                "nodes": [],
                "edges": [],
                "error": f"Subgraph extraction failed: {exc}",
            })

    return {"nodes": nodes, "edges": edges, "cursor": cursor, "subgraphs": subgraphs}


def _pretty(node_id: str) -> str:
    """literature_review → Literature Review."""
    return node_id.replace("_", " ").title()


def _edge_idx(edges: list[dict], source: str, target: str) -> int:
    for i, e in enumerate(edges):
        if e["from"] == source and e["to"] == target:
            return i
    return -1
