import { useEffect, useCallback, useRef, useState } from "react";
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
import ELK from "elkjs/lib/elk.bundled.js";
import type { ElkNode } from "elkjs/lib/elk-api";
import { Skeleton, Empty } from "antd";
import { useGraph } from "../../hooks/useGraph";
import { useSession } from "../../hooks/useSession";
import { useUpdateStagePreference } from "../../hooks/useUpdateStagePreference";
import { StageNode } from "./StageNode";
import { ZoneNode } from "./ZoneNode";
import type { GraphNode, GraphEdge, GraphTopology as Topo } from "../../types/domain";
import type { ControlLevel } from "../../hooks/useUpdateStagePreference";

const elk = new ELK();

const DEMOTE_THRESHOLD = 8;

type StageNodeData = {
  node: GraphNode;
  control?: ControlLevel;
  onControlChange?: (level: ControlLevel) => void;
  isActive?: boolean;
  isSweeping?: boolean;
  onStageClick?: (stageId: string) => void;
};

type ZoneNodeData = { zone: string };

const nodeTypes = {
  stage: (p: { data: StageNodeData }) => (
    <StageNode
      node={p.data.node}
      control={p.data.control}
      onControlChange={p.data.onControlChange}
      isActive={p.data.isActive}
      isSweeping={p.data.isSweeping}
      onStageClick={p.data.onStageClick}
    />
  ),
  zone: (p: { data: ZoneNodeData }) => <ZoneNode data={p.data} />,
};

const ZONE_ORDER = ["discovery", "implementation", "synthesis"] as const;
const META_IDS = new Set(["__start__", "__end__", "transition"]);

/**
 * Compact edges for the production-line graph.
 *
 * The backend already classifies sequential vs backtrack edges. The frontend
 * should render that topology faithfully, but we still drop transition/meta
 * nodes from the top canvas to keep the production line readable.
 */
function compactEdges(rawEdges: GraphEdge[]): GraphEdge[] {
  return rawEdges.filter((e) => !META_IDS.has(e.from) && !META_IDS.has(e.to));
}

function buildRfEdges(edges: GraphEdge[]): Edge[] {
  const backtrackEdges = edges.filter((e) => e.kind === "backtrack");
  const demoteLabels = backtrackEdges.length > DEMOTE_THRESHOLD;
  const backtrackLaneByPair = new Map<string, number>();
  let nextLane = 0;

  return edges.map((e, i) => {
    const isBacktrack = e.kind === "backtrack";
    let backtrackOffset = 0;
    let sourceHandle: string | undefined;
    let targetHandle: string | undefined;
    if (isBacktrack) {
      const pairKey = `${e.from}->${e.to}`;
      let lane = backtrackLaneByPair.get(pairKey);
      if (lane === undefined) {
        lane = nextLane;
        nextLane += 1;
        backtrackLaneByPair.set(pairKey, lane);
      }
      const useTopLane = lane % 2 === 0;
      const tier = Math.floor(lane / 2);
      sourceHandle = useTopLane ? "bt-source-top" : "bt-source-bottom";
      targetHandle = useTopLane ? "bt-target-top" : "bt-target-bottom";
      backtrackOffset = 56 + tier * 28;
    }
    return {
      id: `e${i}`,
      source: e.from,
      target: e.to,
      type: isBacktrack ? "smoothstep" : "default",
      sourceHandle,
      targetHandle,
      pathOptions: isBacktrack
        ? { offset: backtrackOffset, borderRadius: 28 }
        : undefined,
      animated: false,
      style: isBacktrack
        ? { stroke: "#d97706", strokeDasharray: "6 4", strokeWidth: 1.5 }
        : { stroke: "#64748b", strokeWidth: 1.5 },
      label: isBacktrack && !demoteLabels ? `↩ ${e.attempts ?? ""}` : undefined,
      labelStyle: isBacktrack
        ? { fontSize: 10, fill: "#d97706", fontWeight: 600 }
        : undefined,
      labelBgStyle: isBacktrack ? { fill: "#fff", fillOpacity: 0.9 } : undefined,
      data: {
        tooltip: isBacktrack
          ? `Backtrack: ${e.attempts} attempt(s) from ${e.from} to ${e.to}`
          : undefined,
      },
    } as Edge;
  });
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
  const elkChildren: ElkNode[] = [];

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

  // Build ELK edges using only sequential edges for layout hints.
  const forwardEdges = compacted.filter((e) => e.kind !== "backtrack");
  const elkEdges = forwardEdges.map((e, i) => ({
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
  /** When provided, bypasses the useGraph hook and uses this topology directly. */
  topology?: Topo;
  /** Called when the user clicks the active stage node. */
  onStageClick?: (stageId: string) => void;
}

export function GraphTopology({ sessionId, topology: topoProp, onStageClick }: Props) {
  const { data: topoFromHook, isLoading } = useGraph(sessionId);
  const { data: session } = useSession(sessionId);
  const updateMut = useUpdateStagePreference(sessionId);
  const [nodes, setNodes, onNodesChange] = useNodesState<Node<StageNodeData | ZoneNodeData>>([]);
  const [edges, setEdges, onEdgesChange] = useEdgesState<Edge>([]);

  // Use prop topology if provided (e.g. in tests), otherwise use hook data
  const topo = topoProp ?? topoFromHook;

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

  // Reverse-sweep animation: orange glow on intermediate stages when cursor jumps backward.
  const previousCursorRef = useRef<string | null>(null);
  const [sweepingNodes, setSweepingNodes] = useState<Set<string>>(new Set());

  const currentCursor = topo?.cursor?.node_id ?? null;
  const defaultSequence = (topo?.nodes ?? [])
    .filter((n) => n.type === "stage")
    .map((n) => n.id);

  useEffect(() => {
    const prev = previousCursorRef.current;
    const curr = currentCursor;
    if (!prev || !curr || prev === curr) {
      previousCursorRef.current = curr;
      return;
    }
    const prevIdx = defaultSequence.indexOf(prev);
    const currIdx = defaultSequence.indexOf(curr);
    if (prevIdx > currIdx && currIdx >= 0) {
      // Backward jump — sweep the stages between new cursor and old cursor (inclusive of old pos)
      const intermediateIds = defaultSequence.slice(currIdx + 1, prevIdx + 1);
      setSweepingNodes(new Set(intermediateIds));
      const timer = setTimeout(() => setSweepingNodes(new Set()), 600);
      previousCursorRef.current = curr;
      return () => clearTimeout(timer);
    }
    previousCursorRef.current = curr;
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [currentCursor, defaultSequence.join("|")]);

  useEffect(() => {
    if (!topo) return;

    const compacted = compactEdges(topo.edges);

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
            const relX = elkChild?.x ?? 0;
            const relY = elkChild?.y ?? 0;
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
                isActive: topo.cursor?.node_id === n.id,
                isSweeping: sweepingNodes.has(n.id),
                onStageClick,
              } as StageNodeData,
            } as Node<StageNodeData>);
          }
        }

        // Meta nodes suppressed — used for layout hints only.

        setNodes(newNodes);
        setEdges(buildRfEdges(compacted));
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
              isActive: topo.cursor?.node_id === n.id,
              isSweeping: sweepingNodes.has(n.id),
              onStageClick,
            },
          })),
        );
        setEdges(buildRfEdges(compacted));
      });
  }, [topo, stageControls, handleControlChange, setNodes, setEdges, onStageClick, sweepingNodes]);

  if (!topoProp && isLoading) return <Skeleton active />;
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
