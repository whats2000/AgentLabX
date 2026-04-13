import { Tag } from "antd";
import type { GraphNode } from "../../types/domain";

const STATUS_COLOR: Record<GraphNode["status"], string> = {
  pending: "default",
  active: "processing",
  complete: "success",
  failed: "error",
  skipped: "default",
  meta: "default",
};

interface Props {
  node: GraphNode;
}

export function StageNode({ node }: Props) {
  const opacity = node.skipped ? 0.4 : 1.0;
  return (
    <div
      data-testid={`stage-node-${node.id}`}
      data-status={node.status}
      style={{
        padding: 10,
        borderRadius: 8,
        background: "#fff",
        border: "1px solid #e0e0e0",
        minWidth: 180,
        opacity,
      }}
    >
      <div style={{ fontSize: 12, fontWeight: 600 }}>{node.label}</div>
      <div style={{ fontSize: 11, color: "#6b7280", marginTop: 4 }}>
        <Tag color={STATUS_COLOR[node.status]} bordered={false}>
          {node.status}
        </Tag>
        {node.iteration_count > 0 && <span>· iter {node.iteration_count}</span>}
      </div>
    </div>
  );
}
