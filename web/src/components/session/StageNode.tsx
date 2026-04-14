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
  isSweeping?: boolean;
  onStageClick?: (stageId: string) => void;
}

export function StageNode({ node, control, onControlChange, isActive, isSweeping, onStageClick }: Props) {
  const opacity = node.skipped ? 0.4 : 1.0;
  const clickable = isActive && onStageClick !== undefined;

  return (
    <div
      data-testid={`stage-node-${node.id}`}
      data-status={node.status}
      role={clickable ? "button" : undefined}
      tabIndex={clickable ? 0 : undefined}
      onClick={clickable ? () => onStageClick(node.id) : undefined}
      onKeyDown={
        clickable
          ? (e) => {
              if (e.key === "Enter" || e.key === " ") {
                e.preventDefault();
                onStageClick(node.id);
              }
            }
          : undefined
      }
      aria-label={clickable ? `Toggle subgraph panel for ${node.label ?? node.id}` : undefined}
      className={[
        isActive ? "stage-node-active" : "",
        isSweeping ? "cursor-reverse-sweep" : "",
      ].filter(Boolean).join(" ") || undefined}
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
      {/* Dedicated handles for backtrack arcs to avoid overlap with forward spine */}
      <Handle
        id="bt-target-top"
        type="target"
        position={Position.Top}
        style={{ background: "#d97706", width: 8, height: 8, opacity: 0 }}
      />
      <Handle
        id="bt-source-top"
        type="source"
        position={Position.Top}
        style={{ background: "#d97706", width: 8, height: 8, opacity: 0 }}
      />
      <Handle
        id="bt-target-bottom"
        type="target"
        position={Position.Bottom}
        style={{ background: "#d97706", width: 8, height: 8, opacity: 0 }}
      />
      <Handle
        id="bt-source-bottom"
        type="source"
        position={Position.Bottom}
        style={{ background: "#d97706", width: 8, height: 8, opacity: 0 }}
      />

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
