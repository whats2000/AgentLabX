import { Row, Col } from "antd";
import { ExperimentDetail } from "./ExperimentDetail";

interface Props {
  a: Record<string, unknown>;
  b: Record<string, unknown>;
}

export function ExperimentDiffView({ a, b }: Props) {
  return (
    <Row gutter={16}>
      <Col span={12}>
        <ExperimentDetail run={a} />
      </Col>
      <Col span={12}>
        <ExperimentDetail run={b} />
      </Col>
    </Row>
  );
}
