import { Skeleton, Empty } from "antd";
import { useQueries } from "@tanstack/react-query";
import { api } from "../../api/client";
import { useAgents } from "../../hooks/useAgents";
import { StageGroup } from "./StageGroup";
import type { AgentTurnRow } from "../../types/domain";

interface Props {
  sessionId: string;
  mode?: "clean" | "lab_scene";
}

export function ChatView({ sessionId, mode = "clean" }: Props) {
  const { data: agents, isLoading } = useAgents(sessionId);
  if (isLoading) return <Skeleton active />;
  if (!agents || agents.length === 0) {
    return <Empty description="No agent turns yet" />;
  }
  return (
    <div>
      <GroupedByStage
        sessionId={sessionId}
        agentNames={agents.map((a) => a.name)}
        mode={mode}
      />
    </div>
  );
}

function GroupedByStage({
  sessionId,
  agentNames,
  mode,
}: {
  sessionId: string;
  agentNames: string[];
  mode: "clean" | "lab_scene";
}) {
  // useQueries satisfies Rules of Hooks — one hook call with a dynamic list of
  // query descriptors, rather than calling useQuery in a loop.
  const histories = useQueries({
    queries: agentNames.map((n) => ({
      queryKey: ["agent-history", sessionId, n] as const,
      queryFn: () => api.getAgentHistory(sessionId, n),
      enabled: !!sessionId && !!n,
    })),
  });

  const all: AgentTurnRow[] = histories.flatMap((h) => h.data?.turns ?? []);
  const byStage = groupByStage(all);

  if (Object.keys(byStage).length === 0) {
    return <Empty description="No agent turns yet" />;
  }

  return (
    <div>
      {Object.entries(byStage).map(([stage, turns]) => (
        <StageGroup key={stage} stage={stage} turns={turns} mode={mode} />
      ))}
    </div>
  );
}

function groupByStage(turns: AgentTurnRow[]): Record<string, AgentTurnRow[]> {
  return turns.reduce<Record<string, AgentTurnRow[]>>((acc, t) => {
    (acc[t.stage] ??= []).push(t);
    return acc;
  }, {});
}
