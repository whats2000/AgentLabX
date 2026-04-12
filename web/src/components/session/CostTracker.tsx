import { useMemo } from "react";
import { Card, Empty, Space, Statistic, Typography } from "antd";
import { DollarOutlined, FireOutlined } from "@ant-design/icons";
import { useCost } from "../../hooks/useCost";
import { useWSStore } from "../../stores/wsStore";
import { useSession } from "../../hooks/useSession";
import { CostGauge } from "./CostGauge";
import { CostLine } from "./CostLine";
import type { PipelineEvent } from "../../types/events";

const { Text } = Typography;
const EMPTY: PipelineEvent[] = [];

interface Props {
  sessionId: string;
  compact?: boolean;
}

interface CostUpdatePayload {
  total_cost?: number;
  total_tokens_in?: number;
  total_tokens_out?: number;
}

/** Pull cost_update events out of the session buffer with stable refs. */
function useCostEvents(
  sessionId: string,
): PipelineEvent<CostUpdatePayload>[] {
  const events = useWSStore((s) => s.events[sessionId] ?? EMPTY);
  return useMemo(
    () =>
      events.filter(
        (e) => e.type === "cost_update",
      ) as PipelineEvent<CostUpdatePayload>[],
    [events],
  );
}

function gaugeColor(v: number): string {
  if (v < 0.7) return "#10a37f";
  if (v < 0.9) return "#f59e0b";
  return "#ef4444";
}

interface CostSummary {
  total_tokens_in: number;
  total_tokens_out: number;
  total_cost: number;
}

export function CostTracker({ sessionId, compact = false }: Props) {
  const { data } = useCost(sessionId);
  const costEvents = useCostEvents(sessionId);
  const { data: session } = useSession(sessionId);

  // Generated OpenAPI schema types the response as `unknown` (the backend
  // returns raw dict today). The server contract is documented as
  // {total_tokens_in, total_tokens_out, total_cost}.
  const current: CostSummary = (data as CostSummary | undefined) ?? {
    total_tokens_in: 0,
    total_tokens_out: 0,
    total_cost: 0,
  };

  // Cost ceiling lives in config_overrides.llm.cost_ceiling if present.
  const ceiling = (() => {
    const cfg = (session?.config_overrides as Record<string, unknown>) ?? {};
    const llm = cfg.llm as Record<string, unknown> | undefined;
    const c = llm?.cost_ceiling;
    return typeof c === "number" && c > 0 ? c : null;
  })();

  const utilisation =
    ceiling !== null ? Math.min(1, current.total_cost / ceiling) : null;

  if (compact) {
    return (
      <div style={{ padding: "0 16px 16px" }}>
        <Space direction="vertical" size={2} style={{ width: "100%" }}>
          <Text type="secondary" style={{ fontSize: 11 }}>
            Total cost
          </Text>
          <div style={{ fontSize: 22, fontWeight: 600 }}>
            ${current.total_cost.toFixed(4)}
          </div>
          <Text type="secondary" style={{ fontSize: 11 }}>
            {(
              current.total_tokens_in + current.total_tokens_out
            ).toLocaleString()}{" "}
            tokens total
          </Text>
          {ceiling !== null && utilisation !== null ? (
            <Text type="secondary" style={{ fontSize: 11 }}>
              {(utilisation * 100).toFixed(1)}% of ${ceiling.toFixed(2)} ceiling
            </Text>
          ) : null}
        </Space>
      </div>
    );
  }

  const lineData = costEvents.map((e, idx) => ({
    t: e.timestamp ?? `${idx}`,
    cost: e.data?.total_cost ?? 0,
  }));

  return (
    <div>
      <div
        style={{
          display: "grid",
          gridTemplateColumns: "repeat(auto-fit, minmax(180px, 1fr))",
          gap: 16,
          marginBottom: 24,
        }}
      >
        <Card variant="borderless" style={{ background: "#fafafa" }}>
          <Statistic
            title="Tokens in"
            value={current.total_tokens_in}
            prefix={<FireOutlined />}
          />
        </Card>
        <Card variant="borderless" style={{ background: "#fafafa" }}>
          <Statistic
            title="Tokens out"
            value={current.total_tokens_out}
            prefix={<FireOutlined />}
          />
        </Card>
        <Card variant="borderless" style={{ background: "#fafafa" }}>
          <Statistic
            title="Total cost"
            value={current.total_cost}
            precision={4}
            prefix={<DollarOutlined />}
          />
        </Card>
      </div>

      {ceiling !== null && utilisation !== null ? (
        <Card
          variant="borderless"
          title="Budget utilisation"
          style={{ marginBottom: 24 }}
        >
          <CostGauge
            current={current.total_cost}
            ceiling={ceiling}
            color={gaugeColor(utilisation)}
          />
          <Text type="secondary" style={{ fontSize: 12 }}>
            ${current.total_cost.toFixed(4)} of ${ceiling.toFixed(2)} (
            {(utilisation * 100).toFixed(1)}%)
          </Text>
        </Card>
      ) : (
        <Card variant="borderless" style={{ marginBottom: 24 }}>
          <Text type="secondary">
            No cost ceiling configured. Set one in the create wizard or
            preferences to see utilisation.
          </Text>
        </Card>
      )}

      <Card variant="borderless" title="Cost over time">
        {lineData.length === 0 ? (
          <Empty
            image={Empty.PRESENTED_IMAGE_SIMPLE}
            description={
              <Text type="secondary" style={{ fontSize: 12 }}>
                Waiting for cost_update events...
              </Text>
            }
          />
        ) : (
          <CostLine data={lineData} />
        )}
      </Card>
    </div>
  );
}
