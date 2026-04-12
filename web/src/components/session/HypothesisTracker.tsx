import { Typography } from "antd";

// TODO(Task 11): Replace this stub with the hypothesis tracker
// (list of confirmed/rejected/pending hypotheses from api.getHypotheses,
// with edit/add affordances when HITL is on).

interface Props {
  sessionId: string;
}

export function HypothesisTracker({ sessionId }: Props) {
  return (
    <div style={{ padding: 12 }}>
      <Typography.Text type="secondary" style={{ fontSize: 12 }}>
        HypothesisTracker stub — Task 11 fills this in.
      </Typography.Text>
      <Typography.Paragraph
        style={{ fontSize: 11, marginTop: 4, color: "#9ca3af" }}
      >
        Session: {sessionId}
      </Typography.Paragraph>
    </div>
  );
}
