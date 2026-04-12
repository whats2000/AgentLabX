import { Card, Empty, Space, Tag, Typography } from "antd";
import { useHypotheses } from "../../hooks/useHypotheses";
import type { Hypothesis } from "../../types/artifacts";

const { Text, Paragraph } = Typography;

const STATUS_COLORS: Record<Hypothesis["status"], string> = {
  active: "blue",
  supported: "green",
  refuted: "red",
  abandoned: "default",
};

interface Props {
  sessionId: string;
}

export function HypothesisTracker({ sessionId }: Props) {
  const { data } = useHypotheses(sessionId);
  // useHypotheses flattens the backend's {hypotheses, total_records} envelope.
  const hypotheses = data ?? [];

  if (hypotheses.length === 0) {
    return (
      <div style={{ padding: "0 16px 16px" }}>
        <Empty
          image={Empty.PRESENTED_IMAGE_SIMPLE}
          description={
            <Text type="secondary" style={{ fontSize: 12 }}>
              No hypotheses yet.
            </Text>
          }
        />
      </div>
    );
  }

  return (
    <div style={{ padding: "0 16px 16px" }}>
      <Space direction="vertical" size={8} style={{ width: "100%" }}>
        {hypotheses.map((h) => {
          const forCount = h.evidence_for?.length ?? 0;
          const againstCount = h.evidence_against?.length ?? 0;
          return (
            <Card
              key={h.id}
              size="small"
              variant="borderless"
              style={{ background: "#fafafa" }}
              styles={{ body: { padding: 12 } }}
            >
              <Space size={6} style={{ marginBottom: 6 }}>
                <Tag color={STATUS_COLORS[h.status]} bordered={false}>
                  {h.status}
                </Tag>
                <Text type="secondary" style={{ fontSize: 11 }}>
                  {h.id}
                </Text>
              </Space>
              <Paragraph style={{ margin: 0, fontSize: 13 }}>
                {h.statement}
              </Paragraph>
              {(forCount > 0 || againstCount > 0) && (
                <Text
                  type="secondary"
                  style={{ fontSize: 11, marginTop: 4, display: "block" }}
                >
                  {forCount} supporting · {againstCount} against
                </Text>
              )}
            </Card>
          );
        })}
      </Space>
    </div>
  );
}
