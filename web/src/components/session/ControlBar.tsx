import { Typography } from "antd";

// TODO(Task 12): Replace this stub with the real ControlBar (start/pause/
// resume/redirect/mode toggle bound to the session WS + REST actions).

interface Props {
  sessionId: string;
}

export function ControlBar({ sessionId }: Props) {
  return (
    <div style={{ padding: 12 }}>
      <Typography.Text type="secondary" style={{ fontSize: 12 }}>
        ControlBar stub — Task 12 fills this in.
      </Typography.Text>
      <Typography.Paragraph
        style={{ fontSize: 11, marginTop: 4, color: "#9ca3af" }}
      >
        Session: {sessionId}
      </Typography.Paragraph>
    </div>
  );
}
