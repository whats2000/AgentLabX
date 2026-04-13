import { Tag, Typography } from "antd";
import { useAgentContext } from "../../hooks/useAgentContext";

const { Text } = Typography;

export function AgentScopeCard({ sessionId, agent }: { sessionId: string; agent: string }) {
  const { data } = useAgentContext(sessionId, agent);
  if (!data) return null;
  const scope = data.scope;
  return (
    <div style={{ fontSize: 12 }}>
      <div>
        <Text type="secondary">read:</Text>{" "}
        {scope.read.map((k) => <Tag key={k} bordered={false}>{k}</Tag>)}
      </div>
      <div>
        <Text type="secondary">summarize:</Text>{" "}
        {Object.keys(scope.summarize).map((k) => (
          <Tag key={k} bordered={false}>{k}&rarr;{scope.summarize[k]}</Tag>
        ))}
      </div>
      <div>
        <Text type="secondary">write:</Text>{" "}
        {scope.write.map((k) => <Tag key={k} color="blue" bordered={false}>{k}</Tag>)}
      </div>
    </div>
  );
}
