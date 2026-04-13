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
import ELK from "elkjs/lib/elk.bundled.js";
import { Skeleton, Empty } from "antd";
import { useGraph } from "../../hooks/useGraph";
import { useSession } from "../../hooks/useSession";
import { useUpdateStagePreference } from "../../hooks/useUpdateStagePreference";
import { StageNode } from "./StageNode";
import type { GraphNode, GraphTopology as Topo } from "../../types/domain";
import type { ControlLevel } from "../../hooks/useUpdateStagePreference";

const elk = new ELK();

type StageNodeData = {
  node: GraphNode;
  control?: ControlLevel;
  onControlChange?: (level: ControlLevel) => void;
};

const nodeTypes = {
  stage: (p: { data: StageNodeData }) => (
    <StageNode
      node={p.data.node}
      control={p.data.control}
      onControlChange={p.data.onControlChange}
    />
  ),
};

async function layoutWithElk(topo: Topo) {
  const res = await elk.layout({
    id: "root",
    layoutOptions: {
      "elk.algorithm": "layered",
      "elk.direction": "RIGHT",
      "elk.spacing.nodeNode": "40",
      "elk.layered.spacing.nodeNodeBetweenLayers": "80",
    },
    children: topo.nodes.map((n) => ({ id: n.id, width: 200, height: 70 })),
    edges: topo.edges.map((e, i) => ({
      id: `e${i}`,
      sources: [e.from],
      targets: [e.to],
    })),
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
  const [nodes, setNodes, onNodesChange] = useNodesState<Node<StageNodeData>>([]);
  const [edges, setEdges, onEdgesChange] = useEdgesState<Edge>([]);

  // Extract stage_controls from session preferences (shallow map of stage id → ControlLevel)
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
    layoutWithElk(topo).then((laid) => {
      setNodes(
        topo.nodes.map((n, i) => {
          const pos = laid.children?.find((c) => c.id === n.id);
          return {
            id: n.id,
            type: "stage",
            position: { x: pos?.x ?? i * 220, y: pos?.y ?? 0 },
            data: {
              node: n,
              control: stageControls[n.id],
              onControlChange:
                n.type === "stage"
                  ? (level: ControlLevel) => handleControlChange(n.id, level)
                  : undefined,
            },
          };
        })
      );
      setEdges(
        topo.edges.map((e, i) => ({
          id: `e${i}`,
          source: e.from,
          target: e.to,
          animated: e.kind === "backtrack",
          style: e.kind === "backtrack" ? { stroke: "#faad14" } : undefined,
          label: e.reason ?? undefined,
        }))
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
