import { Tag, Typography } from "antd";
import { ToolCallAnnotation } from "./ToolCallAnnotation";
import type { AgentTurnRow } from "../../types/domain";

const { Text } = Typography;

// Deterministic color from agent name
const PALETTE = [
  "#1677ff",
  "#fa8c16",
  "#52c41a",
  "#722ed1",
  "#eb2f96",
  "#13c2c2",
  "#faad14",
  "#f5222d",
];

function agentColor(name: string): string {
  let h = 0;
  for (let i = 0; i < name.length; i++) {
    h = ((h * 31 + name.charCodeAt(i)) >>> 0) % PALETTE.length;
  }
  return PALETTE[h];
}

function collectToolPairs(
  rows: AgentTurnRow[],
): Array<readonly [AgentTurnRow, AgentTurnRow | undefined]> {
  const calls = rows.filter((r) => r.kind === "tool_call");
  const results = rows.filter((r) => r.kind === "tool_result");
  return calls.map((c, i) => [c, results[i]] as const);
}

export function AgentTurnBubble({ rows }: { rows: AgentTurnRow[] }) {
  const first = rows[0];
  const resp = rows.find((r) => r.kind === "llm_response");
  const toolPairs = collectToolPairs(rows);
  const color = agentColor(first.agent);
  const initial = first.agent[0]?.toUpperCase() ?? "?";

  // Suppress until the response arrives
  if (!resp) return null;

  return (
    <div style={{ display: "flex", gap: 8, alignItems: "flex-start" }}>
      {/* Avatar */}
      <div
        style={{
          width: 28,
          height: 28,
          borderRadius: "50%",
          background: color,
          color: "#fff",
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          fontSize: 12,
          fontWeight: 600,
          flexShrink: 0,
        }}
      >
        {initial}
      </div>

      <div style={{ flex: 1, minWidth: 0 }}>
        {/* Agent name + mock tag */}
        <div style={{ fontSize: 11, color: "#6b7280", marginBottom: 2 }}>
          <Text strong style={{ color, fontSize: 12 }}>
            {first.agent}
          </Text>
          {first.is_mock && (
            <Tag
              color="cyan"
              bordered={false}
              style={{ marginLeft: 6, fontSize: 10 }}
            >
              mock
            </Tag>
          )}
        </div>

        {/* Response bubble */}
        <div
          style={{
            background: "#fff",
            border: "1px solid #f0f0f0",
            borderRadius: 8,
            padding: "8px 10px",
            fontSize: 13,
            lineHeight: 1.5,
            whiteSpace: "pre-wrap",
            wordBreak: "break-word",
          }}
        >
          {String(resp.payload.content ?? "")}
        </div>

        {/* Tool call annotations */}
        {toolPairs.length > 0 && (
          <div style={{ marginTop: 4 }}>
            {toolPairs.map(([call, result], i) => (
              <ToolCallAnnotation key={i} call={call} result={result} />
            ))}
          </div>
        )}

        {/* Metadata footer */}
        <div style={{ fontSize: 10, color: "#9ca3af", marginTop: 4 }}>
          {resp.tokens_in != null && resp.tokens_out != null && (
            <span>
              {resp.tokens_in}+{resp.tokens_out} tok ·{" "}
            </span>
          )}
          {resp.cost_usd != null && resp.cost_usd > 0 && (
            <span>${resp.cost_usd.toFixed(4)} · </span>
          )}
          <span>{resp.ts.slice(11, 19)}</span>
        </div>
      </div>
    </div>
  );
}
