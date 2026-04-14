import { Card, Tag, Typography } from "antd";
import type { StagePlan, StagePlanStatus } from "../../types/domain";

interface Props {
  plan: StagePlan | null;
}

const STATUS_COLORS: Record<StagePlanStatus, string> = {
  done: "green",
  edit: "orange",
  todo: "blue",
  removed: "default",
};

export function StagePlanCard({ plan }: Props) {
  if (!plan) return null;

  return (
    <Card size="small" title="Stage Plan">
      <Typography.Paragraph
        type="secondary"
        style={{ fontSize: 12, marginBottom: 8 }}
      >
        {plan.rationale}
      </Typography.Paragraph>
      <ul style={{ listStyle: "none", padding: 0, margin: 0 }}>
        {plan.items.map((item) => (
          <li
            key={item.id}
            style={{
              padding: "6px 0",
              display: "flex",
              alignItems: "flex-start",
              gap: 8,
              borderBottom: "1px solid #f0f0f0",
            }}
          >
            <Tag color={STATUS_COLORS[item.status]} style={{ margin: 0 }}>
              {item.status}
            </Tag>
            <div style={{ flex: 1, minWidth: 0 }}>
              <div style={{ fontSize: 13 }}>{item.description}</div>
              {item.edit_note && (
                <Typography.Text
                  type="secondary"
                  style={{ fontSize: 11, display: "block" }}
                >
                  Edit: {item.edit_note}
                </Typography.Text>
              )}
              {item.removed_reason && (
                <Typography.Text
                  type="secondary"
                  style={{ fontSize: 11, display: "block" }}
                >
                  Removed: {item.removed_reason}
                </Typography.Text>
              )}
            </div>
          </li>
        ))}
      </ul>
    </Card>
  );
}
