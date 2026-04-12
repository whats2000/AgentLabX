import { Line } from "@ant-design/plots";

/**
 * Isolated so tests can mock `./CostLine` without needing a canvas
 * polyfill (jsdom cannot paint the real @ant-design/plots output).
 */
export function CostLine({
  data,
}: {
  data: Array<{ t: string; cost: number }>;
}) {
  return (
    <div style={{ height: 240 }} data-testid="cost-line">
      <Line
        data={data}
        xField="t"
        yField="cost"
        point={{ size: 3 }}
        style={{ stroke: "#10a37f", strokeWidth: 2 }}
        axis={{ x: { title: "Event" }, y: { title: "Total cost ($)" } }}
        autoFit
      />
    </div>
  );
}
