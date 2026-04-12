import { Typography } from "antd";

// TODO(Task 13): Replace this stub with the cost gauge
// (per-provider spend, budget cap, and a compact progress-ring view for
// the right sidebar plus a fuller breakdown for the Cost tab).

interface Props {
  sessionId: string;
  compact?: boolean;
}

export function CostTracker({ sessionId, compact }: Props) {
  return (
    <div style={{ padding: compact ? 12 : 12 }}>
      <Typography.Text type="secondary" style={{ fontSize: 12 }}>
        CostTracker stub{compact ? " (compact)" : ""} — Task 13 fills this in.
      </Typography.Text>
      <Typography.Paragraph
        style={{ fontSize: 11, marginTop: 4, color: "#9ca3af" }}
      >
        Session: {sessionId}
      </Typography.Paragraph>
    </div>
  );
}
