import { Typography } from "antd";

// TODO(Task 10): Replace this stub with the live agent activity feed
// (rendering the wsStore ring buffer with agent_thinking / agent_tool_call /
// agent_dialogue / stage_* events, grouped by agent + timeline).

interface Props {
  sessionId: string;
}

export function AgentActivityFeed({ sessionId }: Props) {
  return (
    <div style={{ padding: 12 }}>
      <Typography.Text type="secondary" style={{ fontSize: 12 }}>
        AgentActivityFeed stub — Task 10 fills this in.
      </Typography.Text>
      <Typography.Paragraph
        style={{ fontSize: 11, marginTop: 4, color: "#9ca3af" }}
      >
        Session: {sessionId}
      </Typography.Paragraph>
    </div>
  );
}
