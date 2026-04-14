/**
 * Topological sort via Kahn's algorithm. Falls back to insertion order if
 * the graph has cycles (shouldn't happen for acyclic stage/meeting subgraphs
 * per spec §3.2.1).
 */
export function topoSort(
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
  if (sorted.length < ids.size) {
    for (const n of nodes) if (!sorted.includes(n.id)) sorted.push(n.id);
  }
  return sorted;
}
