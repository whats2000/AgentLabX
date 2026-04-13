import { Card, Typography } from "antd";
import { AgentTurn } from "./AgentTurn";
import type { AgentTurnRow } from "../../types/domain";

const { Text } = Typography;

function prettyStage(s: string): string {
  return s.split("_").map((w) => w[0].toUpperCase() + w.slice(1)).join(" ");
}

export function StageGroup({
  stage,
  turns,
  mode,
}: {
  stage: string;
  turns: AgentTurnRow[];
  mode: "clean" | "lab_scene";
}) {
  // Group turns by turn_id within this stage
  const byTurn: Record<string, AgentTurnRow[]> = {};
  for (const t of turns) {
    (byTurn[t.turn_id] ??= []).push(t);
  }

  return (
    <Card size="small" style={{ marginBottom: 12 }}>
      <Text strong>{prettyStage(stage)}</Text>
      <Text type="secondary" style={{ marginLeft: 8, fontSize: 11 }}>
        {Object.keys(byTurn).length} turns
      </Text>
      <div style={{ marginTop: 8 }}>
        {Object.entries(byTurn).map(([turnId, rows]) => (
          <AgentTurn key={turnId} turnId={turnId} rows={rows} mode={mode} />
        ))}
      </div>
    </Card>
  );
}
