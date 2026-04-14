import { useState, useEffect } from "react";
import { Collapse } from "antd";
import { StageGroup } from "./StageGroup";

// Fixed stage ordering — matches the production pipeline sequence.
// A future plan will derive this from the graph topology's node list.
export const DEFAULT_STAGE_ORDER = [
  "literature_review",
  "plan_formulation",
  "data_exploration",
  "data_preparation",
  "experimentation",
  "results_interpretation",
  "report_writing",
  "peer_review",
];

interface Props {
  sessionId: string;
  activeStage: string | null;
}

export function ChatView({ sessionId, activeStage }: Props) {
  // activeKey tracks which panels are expanded (Antd Collapse multi-open).
  // Default: expand only the activeStage section.
  const [activeKey, setActiveKey] = useState<string[]>(() =>
    activeStage ? [activeStage] : [],
  );

  // When activeStage changes (stage transition), auto-expand the new active
  // section WITHOUT collapsing already-expanded panels (user's manual opens stick).
  useEffect(() => {
    if (activeStage && !activeKey.includes(activeStage)) {
      setActiveKey((prev) => [...prev, activeStage]);
    }
  }, [activeStage]); // eslint-disable-line react-hooks/exhaustive-deps

  const items = DEFAULT_STAGE_ORDER.map((stageName) => {
    const isExpanded = activeKey.includes(stageName);
    const isActive = activeStage === stageName;
    return {
      key: stageName,
      label: (
        <span
          style={{ textTransform: "capitalize", fontWeight: isActive ? 600 : 400 }}
        >
          {stageName.replace(/_/g, " ")}
          {isActive && " ▶"}
        </span>
      ),
      // Render children only when expanded — this is the lazy-load gate.
      // Once StageGroup mounts, useAgentHistory fires its query (enabled=true).
      children: isExpanded ? (
        <StageGroup
          sessionId={sessionId}
          stageName={stageName}
          isExpanded={isExpanded}
        />
      ) : null,
    };
  });

  return (
    <Collapse
      activeKey={activeKey}
      onChange={(keys) => setActiveKey(Array.isArray(keys) ? keys : [keys])}
      items={items}
      size="small"
      ghost
    />
  );
}
