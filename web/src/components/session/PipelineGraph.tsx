import { Typography } from "antd";

// TODO(Task 9): Replace this stub with the React Flow DAG visualization
// (nodes per stage, edges per transition, zoom/pan controls).

interface Props {
  sessionId: string;
}

export function PipelineGraph({ sessionId }: Props) {
  return (
    <div style={{ padding: 12 }}>
      <Typography.Text type="secondary" style={{ fontSize: 12 }}>
        PipelineGraph stub — Task 9 fills this in.
      </Typography.Text>
      <Typography.Paragraph
        style={{ fontSize: 11, marginTop: 4, color: "#9ca3af" }}
      >
        Session: {sessionId}
      </Typography.Paragraph>
    </div>
  );
}
