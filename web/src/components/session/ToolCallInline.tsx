import { Collapse, Tag, Typography } from "antd";
import type { AgentTurnRow } from "../../types/domain";

const { Text } = Typography;

export function ToolCallInline({
  call,
  result,
}: {
  call: AgentTurnRow;
  result: AgentTurnRow | undefined;
}) {
  const success = result ? (result.payload.success as boolean) : false;
  return (
    <Collapse
      ghost
      items={[{
        key: "t",
        label: (
          <span>
            <Tag color={success ? "green" : result ? "red" : "default"}>tool</Tag>
            <Text strong style={{ fontSize: 12 }}>
              {String(call.payload.tool)}
            </Text>
          </span>
        ),
        children: (
          <pre style={{
            fontSize: 11,
            background: "#fafafa",
            padding: 8,
            borderRadius: 4,
          }}>
{JSON.stringify({
  args: call.payload.args,
  result: result?.payload?.result_preview,
}, null, 2)}
          </pre>
        ),
      }]}
    />
  );
}
