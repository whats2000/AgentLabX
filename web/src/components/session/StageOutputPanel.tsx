import { Typography } from "antd";

// TODO(Task 11): Replace this stub with the stage artifact viewer
// (markdown/code/plot rendering pulled from api.getArtifacts, with a
// condensed `compact` mode for the right sidebar summary).

interface Props {
  sessionId: string;
  compact?: boolean;
}

export function StageOutputPanel({ sessionId, compact }: Props) {
  return (
    <div style={{ padding: compact ? 0 : 12 }}>
      <Typography.Text type="secondary" style={{ fontSize: 12 }}>
        StageOutputPanel stub{compact ? " (compact)" : ""} — Task 11 fills this
        in.
      </Typography.Text>
      <Typography.Paragraph
        style={{ fontSize: 11, marginTop: 4, color: "#9ca3af" }}
      >
        Session: {sessionId}
      </Typography.Paragraph>
    </div>
  );
}
