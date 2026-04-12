import { Typography } from "antd";

// TODO(Task 9): Replace this stub with the left-nav pipeline progress
// (one row per stage with status icon + current-stage highlight).

interface Props {
  sessionId: string;
}

export function PipelineTracker({ sessionId }: Props) {
  return (
    <div style={{ padding: 12 }}>
      <Typography.Text type="secondary" style={{ fontSize: 12 }}>
        PipelineTracker stub — Task 9 fills this in.
      </Typography.Text>
      <Typography.Paragraph
        style={{ fontSize: 11, marginTop: 4, color: "#9ca3af" }}
      >
        Session: {sessionId}
      </Typography.Paragraph>
    </div>
  );
}
