import { useEffect } from "react";
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
import { StageNode } from "./StageNode";
import type { GraphNode, GraphTopology as Topo } from "../../types/domain";

const elk = new ELK();

type StageNodeData = { node: GraphNode };

const nodeTypes = {
  stage: (p: { data: StageNodeData }) => <StageNode node={p.data.node} />,
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
  onNodeOpen?: (nodeId: string) => void;
}

export function GraphTopology({ sessionId, onNodeOpen: _onNodeOpen }: Props) {
  const { data: topo, isLoading } = useGraph(sessionId);
  const [nodes, setNodes, onNodesChange] = useNodesState<Node<StageNodeData>>([]);
  const [edges, setEdges, onEdgesChange] = useEdgesState<Edge>([]);

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
            data: { node: n },
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
  }, [topo, setNodes, setEdges]);

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
