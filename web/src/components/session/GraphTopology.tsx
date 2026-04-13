import { useEffect, useCallback } from "react";
import {
  ReactFlow,
  Background,
  Controls,
  useNodesState,
  useEdgesState,
  type Node,
  type Edge,
} from "@xyflow/react";
import "@xyflow/react/dist/style.css";
import ELK, { type ElkNode } from "elkjs/lib/elk.bundled.js";
import { Skeleton, Empty } from "antd";
import { useGraph } from "../../hooks/useGraph";
import { useSession } from "../../hooks/useSession";
import { useUpdateStagePreference } from "../../hooks/useUpdateStagePreference";
import { StageNode } from "./StageNode";
import { ZoneNode } from "./ZoneNode";
import type { GraphNode, GraphEdge, GraphTopology as Topo } from "../../types/domain";
import type { ControlLevel } from "../../hooks/useUpdateStagePreference";

const elk = new ELK();

type StageNodeData = {
  node: GraphNode;
  control?: ControlLevel;
  onControlChange?: (level: ControlLevel) => void;
};

type ZoneNodeData = { zone: string };

const nodeTypes = {
  stage: (p: { data: StageNodeData }) => (
    <StageNode
      node={p.data.node}
      control={p.data.control}
      onControlChange={p.data.onControlChange}
    />
  ),
  zone: (p: { data: ZoneNodeData }) => <ZoneNode data={p.data} />,
};

const ZONE_ORDER = ["discovery", "implementation", "synthesis"] as const;
const META_IDS = new Set(["__start__", "__end__", "transition"]);

/**
 * Compact edges: remove the transition hub by building direct stage→stage edges.
 * Any edge through `transition` is expanded to a direct from→to.
 * Edges involving __start__/__end__ are dropped entirely.
 */
function compactEdges(rawEdges: GraphEdge[]): GraphEdge[] {
  const direct = rawEdges.filter(
    (e) =>
      e.from !== "transition" &&
      e.to !== "transition" &&
      e.from !== "__start__" &&
      e.to !== "__end__" &&
      e.from !== "__end__" &&
      e.to !== "__start__",
  );

  const intoTransition = rawEdges.filter((e) => e.to === "transition");
  const outOfTransition = rawEdges.filter((e) => e.from === "transition");

  for (const inE of intoTransition) {
    for (const outE of outOfTransition) {
      if (inE.from !== outE.to) {
        // Avoid duplicates already in direct
        const already = direct.some(
          (e) => e.from === inE.from && e.to === outE.to,
        );
        if (!already) {
          direct.push({
            from: inE.from,
            to: outE.to,
            kind: "sequential",
            reason: null,
          });
        }
      }
    }
  }

  return direct;
}

async function layoutWithElk(topo: Topo) {
  const stageNodes = topo.nodes.filter((n) => !META_IDS.has(n.id) && n.zone !== null);
  const metaNodes = topo.nodes.filter((n) => META_IDS.has(n.id));

  // Group stage nodes by zone
  const byZone: Record<string, GraphNode[]> = {};
  for (const n of stageNodes) {
    const z = n.zone!;
    (byZone[z] ??= []).push(n);
  }

  const compacted = compactEdges(topo.edges);

  // Build ELK children: zone group parents + meta nodes at top level
  const elkChildren: object[] = [];

  for (const zone of ZONE_ORDER) {
    const members = byZone[zone];
    if (!members || members.length === 0) continue;
    elkChildren.push({
      id: `_${zone}_group`,
      layoutOptions: {
        "elk.algorithm": "layered",
        "elk.direction": "DOWN",
        "elk.padding": "[top=28,left=16,right=16,bottom=16]",
        "elk.spacing.nodeNode": "20",
      },
      children: members.map((n) => ({ id: n.id, width: 200, height: 70 })),
    });
  }

  for (const m of metaNodes) {
    elkChildren.push({ id: m.id, width: 100, height: 40 });
  }

  // Build ELK edges using compacted set (skip edges to/from suppressed meta nodes at this level)
  const elkEdges = compacted.map((e, i) => ({
    id: `e${i}`,
    sources: [e.from],
    targets: [e.to],
  }));

  const res = await elk.layout({
    id: "root",
    layoutOptions: {
      "elk.algorithm": "layered",
      "elk.direction": "RIGHT",
      "elk.hierarchyHandling": "INCLUDE_CHILDREN",
      "elk.padding": "[top=30,left=20,right=20,bottom=20]",
      "elk.spacing.nodeNode": "30",
      "elk.layered.spacing.nodeNodeBetweenLayers": "60",
    },
    children: elkChildren,
    edges: elkEdges,
  });

  return res;
}

interface Props {
  sessionId: string;
}

export function GraphTopology({ sessionId }: Props) {
  const { data: topo, isLoading } = useGraph(sessionId);
  const { data: session } = useSession(sessionId);
  const updateMut = useUpdateStagePreference(sessionId);
  const [nodes, setNodes, onNodesChange] = useNodesState<Node<StageNodeData | ZoneNodeData>>([]);
  const [edges, setEdges, onEdgesChange] = useEdgesState<Edge>([]);

  const stageControls = (
    (session?.preferences as Record<string, unknown> | undefined)
      ?.stage_controls ?? {}
  ) as Record<string, ControlLevel>;

  const handleControlChange = useCallback(
    (stageId: string, level: ControlLevel) => {
      updateMut.mutate({ stage: stageId, level });
    },
    [updateMut],
  );

  useEffect(() => {
    if (!topo) return;

    layoutWithElk(topo)
      .then((laid) => {
        const newNodes: Node<StageNodeData | ZoneNodeData>[] = [];

        // Add zone group nodes
        for (const zone of ZONE_ORDER) {
          const groupId = `_${zone}_group`;
          const elkGroup = laid.children?.find((c) => c.id === groupId);
          if (!elkGroup) continue;

          newNodes.push({
            id: groupId,
            type: "zone",
            position: { x: elkGroup.x ?? 0, y: elkGroup.y ?? 0 },
            style: {
              width: elkGroup.width ?? 240,
              height: elkGroup.height ?? 120,
            },
            data: { zone } as ZoneNodeData,
            selectable: false,
            draggable: false,
          } as Node<ZoneNodeData>);

          // Add stage nodes inside zone, with relative positions
          const zoneMembers = topo.nodes.filter((n) => n.zone === zone);
          for (const n of zoneMembers) {
            const elkChild = elkGroup.children?.find((c) => c.id === n.id);
            const relX = (elkChild?.x ?? 0) - 0; // ELK already returns relative coords for children
            const relY = (elkChild?.y ?? 0) - 0;
            newNodes.push({
              id: n.id,
              type: "stage",
              parentId: groupId,
              extent: "parent" as const,
              position: { x: relX, y: relY },
              data: {
                node: n,
                control: stageControls[n.id],
                onControlChange:
                  n.type === "stage"
                    ? (level: ControlLevel) => handleControlChange(n.id, level)
                    : undefined,
              } as StageNodeData,
            } as Node<StageNodeData>);
          }
        }

        // Add meta nodes (suppressed — render tiny and faded)
        // Actually skip __start__, __end__, transition from rendering
        // to avoid the "hairball" look. They're used for layout hints only.

        setNodes(newNodes);

        const compacted = compactEdges(topo.edges);
        setEdges(
          compacted.map((e, i) => ({
            id: `e${i}`,
            source: e.from,
            target: e.to,
            animated: e.kind === "backtrack",
            style: e.kind === "backtrack" ? { stroke: "#faad14" } : undefined,
            label: e.reason ?? undefined,
          })),
        );
      })
      .catch(() => {
        // Fallback: flat layout without zone grouping
        const allNonMeta = topo.nodes.filter((n) => !META_IDS.has(n.id));
        setNodes(
          allNonMeta.map((n, i) => ({
            id: n.id,
            type: "stage",
            position: { x: i * 220, y: 0 },
            data: {
              node: n,
              control: stageControls[n.id],
              onControlChange:
                n.type === "stage"
                  ? (level: ControlLevel) => handleControlChange(n.id, level)
                  : undefined,
            },
          })),
        );
        const compacted = compactEdges(topo.edges);
        setEdges(
          compacted.map((e, i) => ({
            id: `e${i}`,
            source: e.from,
            target: e.to,
            animated: e.kind === "backtrack",
            style: e.kind === "backtrack" ? { stroke: "#faad14" } : undefined,
          })),
        );
      });
  }, [topo, stageControls, handleControlChange, setNodes, setEdges]);

  if (isLoading) return <Skeleton active />;
  if (!topo) return <Empty description="No topology" />;

  return (
    <div
      style={{
        height: 320,
        border: "1px solid #efefef",
        borderRadius: 8,
      }}
    >
      <ReactFlow
        nodes={nodes}
        edges={edges}
        nodeTypes={nodeTypes}
        onNodesChange={onNodesChange}
        onEdgesChange={onEdgesChange}
        fitView
      >
        <Background />
        <Controls />
      </ReactFlow>
    </div>
  );
}
