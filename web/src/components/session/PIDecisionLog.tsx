import { List, Tag, Typography, Empty } from "antd";
import { usePIHistory } from "../../hooks/usePIHistory";
import type { PIDecisionRecord } from "../../types/domain";

const { Text } = Typography;

export function PIDecisionLog({
  sessionId,
  limit = 3,
}: {
  sessionId: string;
  limit?: number;
}) {
  const { data } = usePIHistory(sessionId);
  const recent = (data as PIDecisionRecord[] | undefined)?.slice(-limit).reverse() ?? [];
  if (recent.length === 0) {
    return (
      <Empty
        description="No PI decisions yet"
        image={Empty.PRESENTED_IMAGE_SIMPLE}
      />
    );
  }
  return (
    <List
      size="small"
      dataSource={recent}
      renderItem={(d) => (
        <List.Item>
          <div style={{ width: "100%" }}>
            <div>
              <Tag color={d.used_fallback ? "warning" : "success"}>{d.action}</Tag>
              <Text type="secondary" style={{ fontSize: 11 }}>
                {d.confidence.toFixed(2)}
                {d.next_stage ? ` → ${d.next_stage}` : ""}
              </Text>
            </div>
            <Text type="secondary" style={{ fontSize: 11 }}>
              {d.reasoning}
            </Text>
          </div>
        </List.Item>
      )}
    />
  );
}
