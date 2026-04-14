import { Empty, Spin } from "antd";
import { useAgentHistory } from "../../hooks/useAgentHistory";
import { AgentTurnBubble } from "./AgentTurnBubble";
// TODO(T9): deduplicate AgentTurn vs AgentTurnBubble — using AgentTurnBubble here
// as it renders better in the Collapse.Panel context (avatar + bubble layout).

interface Props {
  sessionId: string;
  stageName: string;
  isExpanded: boolean;
}

export function StageGroup({ sessionId, stageName, isExpanded }: Props) {
  // Only fetch when expanded — `enabled` flag gates the query.
  const { data, isLoading } = useAgentHistory(sessionId, {
    stage: stageName,
    enabled: isExpanded,
  });

  // Belt + suspenders: ChatView also gates children via conditional render,
  // but guard here too in case StageGroup is used standalone.
  if (!isExpanded) return null;

  if (isLoading) return <Spin size="small" />;

  const turns = data?.turns ?? [];

  if (turns.length === 0) {
    return <Empty description="No turns yet" image={Empty.PRESENTED_IMAGE_SIMPLE} />;
  }

  // Group rows by turn_id so AgentTurnBubble gets all rows for one turn.
  const byTurn: Record<string, typeof turns> = {};
  for (const t of turns) {
    (byTurn[t.turn_id] ??= []).push(t);
  }
  const orderedTurnIds = Array.from(new Set(turns.map((t) => t.turn_id)));

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
      {orderedTurnIds.map((tid) => (
        <AgentTurnBubble key={tid} rows={byTurn[tid]} />
      ))}
    </div>
  );
}
