import { Empty, Typography } from "antd";
import { useAgentMemory } from "../../hooks/useAgentMemory";

const { Text } = Typography;

export function AgentMemoryCard({ sessionId, agent }: { sessionId: string; agent: string }) {
  const { data } = useAgentMemory(sessionId, agent);
  if (!data) return null;
  if (data.notes.length === 0 && Object.keys(data.working_memory).length === 0) {
    return <Empty description="Empty scratchpad" image={Empty.PRESENTED_IMAGE_SIMPLE} />;
  }
  return (
    <div style={{ fontSize: 12 }}>
      {data.notes.length > 0 && (
        <div>
          <Text type="secondary">notes:</Text>
          <ul style={{ margin: "4px 0 0 0", paddingLeft: 16 }}>
            {data.notes.map((n, i) => <li key={i}>{n}</li>)}
          </ul>
        </div>
      )}
      {Object.keys(data.working_memory).length > 0 && (
        <pre style={{ fontSize: 11, marginTop: 8 }}>
{JSON.stringify(data.working_memory, null, 2)}
        </pre>
      )}
    </div>
  );
}
