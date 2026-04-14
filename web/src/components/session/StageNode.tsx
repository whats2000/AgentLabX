import { Tag, Select } from "antd";
import { Handle, Position } from "@xyflow/react";
import type { GraphNode } from "../../types/domain";
import type { ControlLevel } from "../../hooks/useUpdateStagePreference";

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
  control?: ControlLevel;
  onControlChange?: (level: ControlLevel) => void;
  isActive?: boolean;
  onStageClick?: (stageId: string) => void;
}

export function StageNode({ node, control, onControlChange, isActive, onStageClick }: Props) {
  const opacity = node.skipped ? 0.4 : 1.0;
  const clickable = isActive && onStageClick !== undefined;

  return (
    <div
      data-testid={`stage-node-${node.id}`}
      data-status={node.status}
      onClick={clickable ? () => onStageClick(node.id) : undefined}
      className={isActive ? "stage-node-active" : undefined}
      style={{
        padding: 10,
        borderRadius: 8,
        background: isActive ? "#e0f2fe" : "#fff",
        border: isActive ? "2px solid #0284c7" : "1px solid #e0e0e0",
        minWidth: 180,
        opacity,
        position: "relative",
        cursor: clickable ? "pointer" : "default",
      }}
    >
      {/* React Flow edge attachment points */}
      <Handle type="target" position={Position.Left} style={{ background: "#999" }} />
      <Handle type="source" position={Position.Right} style={{ background: "#999" }} />

      <div style={{ fontSize: 12, fontWeight: 600 }}>
        {node.label}
        {isActive && <span aria-hidden="true"> ▾</span>}
      </div>
      <div style={{ fontSize: 11, color: "#6b7280", marginTop: 4 }}>
        <Tag color={STATUS_COLOR[node.status]} bordered={false}>
          {node.status}
        </Tag>
        {node.iteration_count > 0 && <span>· iter {node.iteration_count}</span>}
      </div>

      {/* Per-stage control level — only for real stage nodes */}
      {node.type === "stage" && onControlChange && (
        <Select
          size="small"
          value={control ?? "auto"}
          onChange={(v) => onControlChange(v as ControlLevel)}
          options={[
            { value: "auto", label: "auto" },
            { value: "notify", label: "notify" },
            { value: "approve", label: "approve" },
            { value: "edit", label: "edit" },
          ]}
          style={{ width: "100%", marginTop: 8 }}
          onClick={(e) => e.stopPropagation()}
          styles={{ popup: { root: { zIndex: 1000 } } }}
        />
      )}
    </div>
  );
}
