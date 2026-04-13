import { Empty, List, Tag, Typography } from "antd";
import { useCrossStageRequests } from "../../hooks/useCrossStageRequests";
import type { CrossStageRequestRecord } from "../../types/domain";

const { Text } = Typography;

const STATUS_COLOR: Record<string, string> = {
  pending: "processing",
  in_progress: "processing",
  completed: "success",
  cancelled: "default",
};

interface Props {
  sessionId: string;
}

export function CrossStageRequestsPanel({ sessionId }: Props) {
  const { data } = useCrossStageRequests(sessionId);
  const pending = data?.pending ?? [];
  const completed = data?.completed ?? [];
  const all = [...pending, ...completed];

  if (all.length === 0) {
    return (
      <Empty
        description={
          <Text type="secondary" style={{ fontSize: 11 }}>
            No cross-stage requests
          </Text>
        }
        image={Empty.PRESENTED_IMAGE_SIMPLE}
      />
    );
  }

  return (
    <List
      size="small"
      dataSource={all}
      renderItem={(r: CrossStageRequestRecord) => (
        <List.Item style={{ padding: "6px 12px" }}>
          <div style={{ width: "100%", fontSize: 11 }}>
            <div style={{ marginBottom: 2 }}>
              <Tag color={STATUS_COLOR[r.status] ?? "default"} bordered={false}>
                {r.status}
              </Tag>
              <Text type="secondary">
                {r.from_stage} → {r.to_stage}
              </Text>
            </div>
            <Text style={{ fontSize: 11 }}>{r.description}</Text>
          </div>
        </List.Item>
      )}
    />
  );
}
