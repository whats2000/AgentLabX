import { Gauge } from "@ant-design/plots";

/**
 * Isolated so tests can mock `./CostGauge` without needing a canvas
 * polyfill (jsdom cannot paint the real @ant-design/plots output).
 */
export function CostGauge({
  current,
  ceiling,
  color,
}: {
  current: number;
  ceiling: number;
  color: string;
}) {
  return (
    <div style={{ height: 240 }} data-testid="cost-gauge">
      <Gauge
        data={{ target: current, total: ceiling }}
        scale={{ color: { range: [color] } }}
        legend={false}
        autoFit
      />
    </div>
  );
}
