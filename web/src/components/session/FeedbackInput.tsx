import { Typography } from "antd";

// TODO(Task 12): Replace this stub with the sticky feedback input
// (textarea + send/approve/edit controls feeding inject_feedback /
// approve / edit actions over the session WS).

interface Props {
  sessionId: string;
}

export function FeedbackInput({ sessionId }: Props) {
  return (
    <div>
      <Typography.Text type="secondary" style={{ fontSize: 12 }}>
        FeedbackInput stub — Task 12 fills this in.
      </Typography.Text>
      <Typography.Paragraph
        style={{ fontSize: 11, marginTop: 4, marginBottom: 0, color: "#9ca3af" }}
      >
        Session: {sessionId}
      </Typography.Paragraph>
    </div>
  );
}
