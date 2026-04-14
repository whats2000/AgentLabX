import React, { useMemo } from "react";
import { Card } from "antd";
import type { GraphSubgraph } from "../../types/domain";

interface Props {
  subgraph: GraphSubgraph | null;
  cursorMeetingNode: string | null;
}

const PSEUDO_NODES = new Set(["__start__", "__end__"]);

/**
 * Topological sort of subgraph nodes using Kahn's algorithm.
 * Falls back to insertion order if the graph has cycles (shouldn't happen
 * for acyclic meeting subgraphs).
 */
function topoSort(
  nodes: { id: string }[],
  edges: { from: string; to: string }[],
): string[] {
  const ids = new Set(nodes.map((n) => n.id));
  const inDegree: Record<string, number> = {};
  const adj: Record<string, string[]> = {};
  for (const id of ids) {
    inDegree[id] = 0;
    adj[id] = [];
  }
  for (const e of edges) {
    if (!ids.has(e.from) || !ids.has(e.to)) continue;
    adj[e.from].push(e.to);
    inDegree[e.to] += 1;
  }
  const queue: string[] = [];
  for (const id of ids) if (inDegree[id] === 0) queue.push(id);
  const sorted: string[] = [];
  while (queue.length) {
    const id = queue.shift()!;
    sorted.push(id);
    for (const next of adj[id]) {
      inDegree[next] -= 1;
      if (inDegree[next] === 0) queue.push(next);
    }
  }
  // If cycle, append any remaining nodes in original order (shouldn't happen)
  if (sorted.length < ids.size) {
    for (const n of nodes) if (!sorted.includes(n.id)) sorted.push(n.id);
  }
  return sorted;
}

export function LabMeetingOverlay({ subgraph, cursorMeetingNode }: Props) {
  const orderedVisibleNodes = useMemo(() => {
    if (!subgraph) return [] as string[];
    return topoSort(subgraph.nodes, subgraph.edges).filter(
      (id) => !PSEUDO_NODES.has(id),
    );
  }, [subgraph]);

  if (!subgraph) return null;

  return (
    <Card
      size="small"
      title="Lab Meeting"
      style={{ marginTop: 12, borderColor: "#d97706" }}
      styles={{
        header: { background: "#fef3c7", color: "#92400e" },
      }}
    >
      <div
        style={{
          display: "flex",
          gap: 16,
          alignItems: "center",
          padding: "8px 16px",
          flexWrap: "wrap",
        }}
      >
        {orderedVisibleNodes.map((id, idx) => {
          const isActive = cursorMeetingNode === id;
          return (
            <React.Fragment key={id}>
              <div
                data-meeting-node={id}
                className={isActive ? "active" : ""}
                style={{
                  padding: "6px 14px",
                  borderRadius: 6,
                  border: "1px solid",
                  borderColor: isActive ? "#0284c7" : "#d9d9d9",
                  background: isActive ? "#e0f2fe" : "#fffbeb",
                  fontWeight: isActive ? 600 : 400,
                  fontSize: 12,
                  textTransform: "uppercase",
                  letterSpacing: "0.02em",
                  boxShadow: isActive
                    ? "0 0 0 2px rgba(2, 132, 199, 0.25)"
                    : undefined,
                }}
              >
                {id}
              </div>
              {idx < orderedVisibleNodes.length - 1 && (
                <span style={{ color: "#bfbfbf", fontSize: 14 }}>→</span>
              )}
            </React.Fragment>
          );
        })}
      </div>
    </Card>
  );
}
