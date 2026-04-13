import { List, Tag, Typography } from "antd";
import { useAgentHistory } from "../../hooks/useAgentHistory";

const { Text } = Typography;

export function AgentHistoryCard({ sessionId, agent }: { sessionId: string; agent: string }) {
  const { data } = useAgentHistory(sessionId, agent, { limit: 50 });
  const turns = data?.turns ?? [];
  if (turns.length === 0) return <Text type="secondary">no turns yet</Text>;
  return (
    <List
      size="small"
      dataSource={turns}
      renderItem={(t) => (
        <List.Item style={{ fontSize: 11 }}>
          <Tag>{t.kind}</Tag>
          <span>{t.stage}</span>
          <span style={{ marginLeft: 8, color: "#999" }}>{t.ts.slice(11, 19)}</span>
        </List.Item>
      )}
    />
  );
}
