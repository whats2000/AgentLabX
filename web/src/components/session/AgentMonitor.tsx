import { useState } from "react";
import { Tabs, Skeleton, Empty, Collapse } from "antd";
import { useAgents } from "../../hooks/useAgents";
import { AgentScopeCard } from "./AgentScopeCard";
import { AgentContextPreview } from "./AgentContextPreview";
import { AgentMemoryCard } from "./AgentMemoryCard";
import { AgentHistoryCard } from "./AgentHistoryCard";

interface Props { sessionId: string; }

export function AgentMonitor({ sessionId }: Props) {
  const { data: agents, isLoading } = useAgents(sessionId);
  const [active, setActive] = useState<string | undefined>();
  if (isLoading) return <Skeleton active />;
  if (!agents || agents.length === 0) return <Empty description="No agents yet" />;

  const key = active ?? agents[0].name;
  return (
    <div style={{ padding: "8px 12px" }}>
      <Tabs
        size="small"
        activeKey={key}
        onChange={setActive}
        items={agents.map((a) => ({
          key: a.name,
          label: a.name,
          children: (
            <Collapse
              defaultActiveKey={["scope", "context", "memory", "history"]}
              ghost
              items={[
                { key: "scope", label: "Scope",
                  children: <AgentScopeCard sessionId={sessionId} agent={a.name} /> },
                { key: "context", label: "Context",
                  children: <AgentContextPreview sessionId={sessionId} agent={a.name} /> },
                { key: "memory", label: "Memory",
                  children: <AgentMemoryCard sessionId={sessionId} agent={a.name} /> },
                { key: "history", label: `History (${a.turn_count} turns)`,
                  children: <AgentHistoryCard sessionId={sessionId} agent={a.name} /> },
              ]}
            />
          ),
        }))}
      />
    </div>
  );
}
