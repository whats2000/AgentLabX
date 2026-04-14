import React, { useMemo } from "react";
import { Alert, Card } from "antd";
import type { GraphSubgraph } from "../../types/domain";
import { topoSort } from "../../utils/topoSort";

interface Props {
  activeStage: string | null;
  subgraph: GraphSubgraph | null;
  cursorInternalNode: string | null;
  meetingActive: boolean;
  onWorkClick: () => void;
}

const PSEUDO_NODES = new Set(["__start__", "__end__"]);

export function StageSubgraphDrawer({
  activeStage,
  subgraph,
  cursorInternalNode,
  meetingActive,
  onWorkClick,
}: Props) {
  const orderedVisibleNodes = useMemo(() => {
    if (!subgraph) return [] as string[];
    return topoSort(subgraph.nodes, subgraph.edges).filter(
      (id) => !PSEUDO_NODES.has(id),
    );
  }, [subgraph]);

  if (!activeStage || !subgraph) return null;

  if (subgraph.error) {
    return (
      <Card
        size="small"
        title={`Inside ${subgraph.label ?? activeStage}`}
        style={{ marginTop: 12 }}
      >
        <Alert
          type="warning"
          showIcon
          message="Subgraph unavailable"
          description={subgraph.error}
        />
      </Card>
    );
  }

  return (
    <Card
      size="small"
      title={`Inside ${subgraph.label ?? activeStage}`}
      style={{ marginTop: 12 }}
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
          const isActive = cursorInternalNode === id;
          const isWork = id === "work";
          const clickable = isWork && meetingActive;
          return (
            <React.Fragment key={id}>
              <div
                data-internal-node={id}
                className={isActive ? "active" : ""}
                role={clickable ? "button" : undefined}
                tabIndex={clickable ? 0 : undefined}
                onClick={clickable ? onWorkClick : undefined}
                onKeyDown={
                  clickable
                    ? (e) => {
                        if (e.key === "Enter" || e.key === " ") {
                          e.preventDefault();
                          onWorkClick();
                        }
                      }
                    : undefined
                }
                aria-label={clickable ? "Toggle work subgraph (meeting)" : undefined}
                style={{
                  padding: "6px 14px",
                  borderRadius: 6,
                  border: "1px solid",
                  borderColor: isActive ? "#0284c7" : "#d9d9d9",
                  background: isActive ? "#e0f2fe" : "#fafafa",
                  fontWeight: isActive ? 600 : 400,
                  fontSize: 12,
                  cursor: clickable ? "pointer" : "default",
                  textTransform: "uppercase",
                  letterSpacing: "0.02em",
                  boxShadow: isActive
                    ? "0 0 0 2px rgba(2, 132, 199, 0.25)"
                    : undefined,
                }}
              >
                {id}
                {clickable ? " ▾" : ""}
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
