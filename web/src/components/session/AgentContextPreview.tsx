import { useAgentContext } from "../../hooks/useAgentContext";

export function AgentContextPreview({ sessionId, agent }: { sessionId: string; agent: string }) {
  const { data } = useAgentContext(sessionId, agent);
  if (!data) return null;
  return (
    <pre style={{
      fontSize: 11,
      maxHeight: 200,
      overflow: "auto",
      background: "#fafafa",
      padding: 8,
      borderRadius: 4,
    }}>
{JSON.stringify(data.preview, null, 2)}
    </pre>
  );
}
