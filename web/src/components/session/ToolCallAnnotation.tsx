import { Typography } from "antd";
import type { AgentTurnRow } from "../../types/domain";

const { Text } = Typography;

export function ToolCallAnnotation({
  call,
  result,
}: {
  call: AgentTurnRow;
  result: AgentTurnRow | undefined;
}) {
  const success = result ? (result.payload.success as boolean) : undefined;
  const indicator = success === true ? "✓" : success === false ? "✗" : "…";
  const color =
    success === true ? "#52c41a" : success === false ? "#f5222d" : "#999";

  return (
    <div style={{ marginTop: 2 }}>
      <Text style={{ fontSize: 11, color: "#6b7280" }}>
        <span style={{ color, marginRight: 4 }}>{indicator}</span>
        via{" "}
        <Text code style={{ fontSize: 11 }}>
          {String(call.payload.tool)}
        </Text>
      </Text>
    </div>
  );
}
