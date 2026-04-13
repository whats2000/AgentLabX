import { Collapse, Tag, Typography } from "antd";
import { ToolCallInline } from "./ToolCallInline";
import type { AgentTurnRow } from "../../types/domain";

const { Text, Paragraph } = Typography;

export function AgentTurn({
  turnId: _turnId,
  rows,
  mode: _mode,
}: {
  turnId: string;
  rows: AgentTurnRow[];
  mode: "clean" | "lab_scene";
}) {
  const first = rows[0];
  const req = rows.find((r) => r.kind === "llm_request");
  const resp = rows.find((r) => r.kind === "llm_response");
  const toolPairs = collectToolPairs(rows);

  return (
    <div style={{ padding: "8px 0", borderBottom: "1px solid #f0f0f0" }}>
      <Text strong>{first.agent}</Text>
      {first.is_mock && (
        <Tag style={{ marginLeft: 8 }} color="cyan">mock</Tag>
      )}
      {resp?.cost_usd != null && (
        <Text type="secondary" style={{ marginLeft: 8, fontSize: 11 }}>
          ${resp.cost_usd.toFixed(4)}
        </Text>
      )}
      {req && (
        <Collapse
          ghost
          items={[{
            key: "sp",
            label: "system prompt",
            children: (
              <Paragraph style={{ fontSize: 12, margin: 0 }}>
                {String(req.payload.system_prompt ?? "")}
              </Paragraph>
            ),
          }]}
        />
      )}
      {req && (
        <Paragraph style={{
          fontSize: 13,
          background: "#fafafa",
          padding: 8,
          borderRadius: 4,
          margin: "4px 0",
        }}>
          <Text type="secondary">user:</Text>{" "}
          {String(req.payload.prompt ?? "")}
        </Paragraph>
      )}
      {resp && (
        <Paragraph style={{ fontSize: 13, margin: "4px 0" }}>
          <Text type="secondary">asst:</Text>{" "}
          {String(resp.payload.content ?? "")}
        </Paragraph>
      )}
      {toolPairs.map(([call, result], i) => (
        <ToolCallInline
          key={`${call.turn_id}-${i}-${String(call.payload.tool)}`}
          call={call}
          result={result}
        />
      ))}
    </div>
  );
}

function collectToolPairs(
  rows: AgentTurnRow[]
): Array<readonly [AgentTurnRow, AgentTurnRow | undefined]> {
  const calls = rows.filter((r) => r.kind === "tool_call");
  const results = rows.filter((r) => r.kind === "tool_result");
  return calls.map((c, i) => [c, results[i]] as const);
}
