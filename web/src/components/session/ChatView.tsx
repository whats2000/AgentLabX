import { useMemo } from "react";
import { Skeleton, Empty } from "antd";
import { useQueries } from "@tanstack/react-query";
import { api } from "../../api/client";
import { useAgents } from "../../hooks/useAgents";
import { AgentTurnBubble } from "./AgentTurnBubble";
import type { AgentTurnRow } from "../../types/domain";

// TODO: Implement useInfiniteQuery-based lazy load once a server-side
// aggregated /turns endpoint is available. For now, fetch a flat list
// (limit=50 per agent) and merge by ts. This is sufficient for the
// mock-LLM walkthrough.
const PAGE_SIZE = 50;

interface Props {
  sessionId: string;
}

export function ChatView({ sessionId }: Props) {
  const { data: agents, isLoading } = useAgents(sessionId);

  const histories = useQueries({
    queries: (agents ?? []).map((a) => ({
      queryKey: ["agent-history", sessionId, a.name, PAGE_SIZE] as const,
      queryFn: () => api.getAgentHistory(sessionId, a.name, { limit: PAGE_SIZE }),
      enabled: !!sessionId && !!a.name,
    })),
  });

  const allTurns = useMemo(() => {
    const flat: AgentTurnRow[] = histories.flatMap((q) => q.data?.turns ?? []);
    return flat.sort((a, b) => a.ts.localeCompare(b.ts));
  }, [histories]);

  if (isLoading) return <Skeleton active />;

  if (!agents || agents.length === 0) {
    return (
      <div style={{ padding: 16 }}>
        <Empty description="No agent turns yet" />
      </div>
    );
  }

  if (allTurns.length === 0) {
    return (
      <div style={{ padding: 16 }}>
        <Empty description="No agent turns yet" />
      </div>
    );
  }

  // Group by stage, preserving insertion order (ts-sorted above)
  const byStage: Record<string, AgentTurnRow[]> = {};
  for (const t of allTurns) {
    (byStage[t.stage] ??= []).push(t);
  }

  return (
    <div
      style={{
        padding: "8px 12px",
        display: "flex",
        flexDirection: "column",
        gap: 16,
      }}
    >
      {Object.entries(byStage).map(([stage, turns]) => (
        <StageSection key={stage} stage={stage} turns={turns} />
      ))}
    </div>
  );
}

function prettyStage(s: string): string {
  return s
    .split("_")
    .map((w) => w[0].toUpperCase() + w.slice(1))
    .join(" ");
}

function StageSection({
  stage,
  turns,
}: {
  stage: string;
  turns: AgentTurnRow[];
}) {
  const byTurn: Record<string, AgentTurnRow[]> = {};
  for (const t of turns) {
    (byTurn[t.turn_id] ??= []).push(t);
  }
  const orderedTurnIds = Array.from(new Set(turns.map((t) => t.turn_id)));

  return (
    <div>
      <div
        style={{
          position: "sticky",
          top: 0,
          zIndex: 1,
          background: "#fafafa",
          padding: "4px 8px",
          borderRadius: 4,
          marginBottom: 6,
          fontSize: 11,
          fontWeight: 600,
          color: "#6b7280",
          textTransform: "uppercase",
          letterSpacing: "0.05em",
        }}
      >
        {prettyStage(stage)}
      </div>
      <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
        {orderedTurnIds.map((tid) => (
          <AgentTurnBubble key={tid} rows={byTurn[tid]} />
        ))}
      </div>
    </div>
  );
}
