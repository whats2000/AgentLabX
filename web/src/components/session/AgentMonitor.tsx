import { useState } from "react";
import { Tabs, Skeleton, Empty, Collapse } from "antd";
import { useAgents } from "../../hooks/useAgents";
import { useStagePlans } from "../../hooks/useStagePlans";
import { AgentScopeCard } from "./AgentScopeCard";
import { AgentContextPreview } from "./AgentContextPreview";
import { AgentMemoryCard } from "./AgentMemoryCard";
import { StagePlanCard } from "./StagePlanCard";

interface Props {
  sessionId: string;
  activeStage?: string | null;
}

function StagePlanSection({ sessionId, stage }: { sessionId: string; stage: string }) {
  const { data } = useStagePlans(sessionId, stage);
  const latest = data?.plans[data.plans.length - 1] ?? null;
  return <StagePlanCard plan={latest} />;
}

export function AgentMonitor({ sessionId, activeStage }: Props) {
  const { data: agents, isLoading } = useAgents(sessionId);
  const [active, setActive] = useState<string | undefined>();
  if (isLoading) return <Skeleton active />;
  if (!agents || agents.length === 0) return <Empty description="No agents yet" />;

  const key = active ?? agents[0].name;
  const focusedAgent = agents.find((a) => a.name === key);
  const showPlan =
    activeStage &&
    focusedAgent &&
    focusedAgent.last_active_stage === activeStage;

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
              defaultActiveKey={["scope", "context", "memory"]}
              ghost
              items={[
                {
                  key: "scope",
                  label: "Scope",
                  children: (
                    <AgentScopeCard sessionId={sessionId} agent={a.name} />
                  ),
                },
                {
                  key: "context",
                  label: "Context",
                  children: (
                    <AgentContextPreview sessionId={sessionId} agent={a.name} />
                  ),
                },
                {
                  key: "memory",
                  label: "Memory",
                  children: (
                    <AgentMemoryCard sessionId={sessionId} agent={a.name} />
                  ),
                },
                ...(showPlan && a.name === key
                  ? [
                      {
                        key: "plan",
                        label: "Stage Plan",
                        children: (
                          <StagePlanSection
                            sessionId={sessionId}
                            stage={activeStage}
                          />
                        ),
                      },
                    ]
                  : []),
              ]}
            />
          ),
        }))}
      />
    </div>
  );
}
