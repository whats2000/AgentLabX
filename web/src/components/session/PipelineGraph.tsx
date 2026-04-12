import { useMemo, useState } from "react";
import {
  Background,
  Position,
  ReactFlow,
  ReactFlowProvider,
  type Edge,
  type Node,
} from "@xyflow/react";
import "@xyflow/react/dist/style.css";
import { Space, Switch, Typography } from "antd";
import { useSession } from "../../hooks/useSession";
import { useTransitions } from "../../hooks/useTransitions";
import {
  STAGE_LABELS,
  STAGE_SEQUENCE,
  ZONE_X,
  stagePositions,
  type Stage,
} from "../../lib/pipelineStages";

const { Text } = Typography;

const MAX_BACKTRACKS_DEFAULT = 3;

type StageStatus = "pending" | "active" | "completed" | "failed";

function stageStatus(
  stage: Stage,
  currentStage: string,
  completed: string[],
  errors: string[],
): StageStatus {
  if (errors.includes(stage)) return "failed";
  if (stage === currentStage) return "active";
  if (completed.includes(stage)) return "completed";
  return "pending";
}

function stageStyle(status: StageStatus): Node["style"] {
  const base: Node["style"] = {
    padding: "10px 16px",
    borderRadius: 8,
    fontSize: 13,
    fontWeight: 500,
    width: 220,
    textAlign: "center",
    boxShadow: "none",
  };
  switch (status) {
    case "completed":
      return {
        ...base,
        background: "#f0fdf4",
        border: "1px solid #86efac",
        color: "#166534",
      };
    case "active":
      return {
        ...base,
        background: "#ecfdf5",
        border: "2px solid #10a37f",
        color: "#065f46",
        boxShadow: "0 0 0 4px rgba(16,163,127,0.12)",
      };
    case "failed":
      return {
        ...base,
        background: "#fef2f2",
        border: "1px solid #fca5a5",
        color: "#991b1b",
      };
    default:
      return {
        ...base,
        background: "#ffffff",
        border: "1px solid #efefef",
        color: "#6b7280",
      };
  }
}

interface Props {
  sessionId: string;
}

// SessionDetail in the generated schema does not yet expose current_stage /
// completed_stages fields (backend schema gap — see Task 16). We read them
// via a narrowed interface so the hook stays typed.
interface SessionWithStageInfo {
  current_stage?: string;
  completed_stages?: string[];
  errors?: Array<{ stage?: string } | string>;
}

function PipelineGraphInner({ sessionId }: Props) {
  const { data: session } = useSession(sessionId);
  const { data: transitions } = useTransitions(sessionId);
  const [showAllBacktracks, setShowAllBacktracks] = useState(false);

  const sessionExtra = (session ?? {}) as SessionWithStageInfo;
  const currentStage = sessionExtra.current_stage ?? "";
  const completed = sessionExtra.completed_stages ?? [];
  const errors: string[] = (sessionExtra.errors ?? [])
    .map((e) => (typeof e === "string" ? e : (e?.stage ?? "")))
    .filter((s): s is string => !!s);

  const positions = useMemo(() => stagePositions(), []);

  const nodes: Node[] = useMemo(() => {
    return STAGE_SEQUENCE.map((stage) => {
      const status = stageStatus(stage, currentStage, completed, errors);
      return {
        id: stage,
        position: positions[stage],
        data: { label: STAGE_LABELS[stage] },
        style: stageStyle(status),
        sourcePosition: Position.Right,
        targetPosition: Position.Left,
        draggable: false,
      };
    });
  }, [currentStage, completed, errors, positions]);

  // Default sequential edges
  const sequentialEdges: Edge[] = useMemo(
    () =>
      STAGE_SEQUENCE.slice(0, -1).map((from, i) => ({
        id: `seq-${from}-${STAGE_SEQUENCE[i + 1]}`,
        source: from,
        target: STAGE_SEQUENCE[i + 1],
        type: "smoothstep",
        style: { stroke: "#d4d4d8", strokeWidth: 1.5 },
      })),
    [],
  );

  // Backtrack edges from transitions. A backtrack is any transition where
  // target_stage appears earlier in STAGE_SEQUENCE than from_stage.
  const backtrackEdges: Edge[] = useMemo(() => {
    if (!transitions) return [];
    const stageIndex = new Map<string, number>(
      STAGE_SEQUENCE.map((s, i) => [s as string, i]),
    );
    const allBacktracks = transitions
      .filter((t) => {
        const fi = stageIndex.get(t.from_stage) ?? -1;
        const ti = stageIndex.get(t.to_stage) ?? -1;
        return fi >= 0 && ti >= 0 && ti < fi;
      })
      // Most recent first
      .slice()
      .reverse();
    const visible = showAllBacktracks
      ? allBacktracks
      : allBacktracks.slice(0, MAX_BACKTRACKS_DEFAULT);
    return visible.map((t, idx) => {
      const isRecent = idx < MAX_BACKTRACKS_DEFAULT;
      return {
        id: `bt-${t.from_stage}-${t.to_stage}-${idx}`,
        source: t.from_stage,
        target: t.to_stage,
        type: "smoothstep",
        style: {
          stroke: "#f59e0b",
          strokeWidth: 1.5,
          strokeDasharray: "6 4",
          opacity: isRecent ? 1 : 0.2,
        },
      };
    });
  }, [transitions, showAllBacktracks]);

  const edges = [...sequentialEdges, ...backtrackEdges];

  const backtrackCount = useMemo(() => {
    if (!transitions) return 0;
    const stageIndex = new Map<string, number>(
      STAGE_SEQUENCE.map((s, i) => [s as string, i]),
    );
    return transitions.filter((t) => {
      const fi = stageIndex.get(t.from_stage) ?? -1;
      const ti = stageIndex.get(t.to_stage) ?? -1;
      return fi >= 0 && ti >= 0 && ti < fi;
    }).length;
  }, [transitions]);

  return (
    <div>
      {/* Toolbar */}
      <div
        style={{
          display: "flex",
          justifyContent: "space-between",
          alignItems: "center",
          padding: "4px 4px 12px",
        }}
      >
        <Space size={24}>
          {(Object.keys(ZONE_X) as Array<keyof typeof ZONE_X>).map((zone) => (
            <Text
              key={zone}
              type="secondary"
              style={{ fontSize: 11, fontWeight: 600, letterSpacing: 0.5 }}
            >
              {zone.toUpperCase()}
            </Text>
          ))}
        </Space>
        {backtrackCount > MAX_BACKTRACKS_DEFAULT ? (
          <Space size={8}>
            <Text type="secondary" style={{ fontSize: 12 }}>
              Show all backtracks ({backtrackCount})
            </Text>
            <Switch
              size="small"
              checked={showAllBacktracks}
              onChange={setShowAllBacktracks}
            />
          </Space>
        ) : null}
      </div>

      <div
        style={{
          width: "100%",
          height: 520,
          border: "1px solid #efefef",
          borderRadius: 12,
          background: "#fafafa",
          overflow: "hidden",
        }}
      >
        <ReactFlow
          nodes={nodes}
          edges={edges}
          fitView
          fitViewOptions={{ padding: 0.2 }}
          nodesConnectable={false}
          nodesDraggable={false}
          edgesFocusable={false}
          proOptions={{ hideAttribution: true }}
        >
          <Background color="#e5e7eb" gap={24} />
        </ReactFlow>
      </div>

      {/* Legend */}
      <div
        style={{
          display: "flex",
          gap: 16,
          marginTop: 12,
          fontSize: 12,
          color: "#6b7280",
        }}
      >
        <LegendSwatch color="#10a37f" label="Active" />
        <LegendSwatch color="#86efac" label="Completed" />
        <LegendSwatch color="#f59e0b" label="Backtrack" dashed />
      </div>
    </div>
  );
}

function LegendSwatch({
  color,
  label,
  dashed,
}: {
  color: string;
  label: string;
  dashed?: boolean;
}) {
  return (
    <span style={{ display: "inline-flex", alignItems: "center", gap: 6 }}>
      <span
        style={{
          width: 18,
          height: 0,
          borderTop: `2px ${dashed ? "dashed" : "solid"} ${color}`,
          display: "inline-block",
        }}
      />
      {label}
    </span>
  );
}

export function PipelineGraph({ sessionId }: Props) {
  return (
    <ReactFlowProvider>
      <PipelineGraphInner sessionId={sessionId} />
    </ReactFlowProvider>
  );
}
