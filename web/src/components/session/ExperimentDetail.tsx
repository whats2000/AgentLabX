import { Card, Collapse, Descriptions, Tag } from "antd";

interface Props {
  run: Record<string, unknown>;
}

export function ExperimentDetail({ run }: Props) {
  const repro = (run.reproducibility as Record<string, unknown> | undefined) ?? {};
  const metrics = (run.metrics as Record<string, unknown> | undefined) ?? {};
  const tag = run.tag as string | undefined;
  const index = run.index as number | undefined;
  const hypothesisId = run.hypothesis_id as string | undefined;
  const stdout = run.stdout as string | undefined;
  const stderr = run.stderr as string | undefined;

  return (
    <Card
      size="small"
      style={{ marginBottom: 12 }}
      title={
        <span>
          {tag && <Tag color="blue">{tag}</Tag>}
          #{index ?? "?"} {hypothesisId && <Tag>H:{hypothesisId}</Tag>}
        </span>
      }
    >
      <Descriptions size="small" column={2}>
        {Object.entries(metrics).map(([k, v]) => (
          <Descriptions.Item key={k} label={k}>
            {String(v)}
          </Descriptions.Item>
        ))}
      </Descriptions>
      <Collapse
        ghost
        items={[
          {
            key: "repro",
            label: "Reproducibility",
            children: (
              <Descriptions size="small" column={1}>
                <Descriptions.Item label="seed">
                  {String(repro.random_seed ?? "")}
                </Descriptions.Item>
                <Descriptions.Item label="run">
                  {String(repro.run_command ?? "")}
                </Descriptions.Item>
                <Descriptions.Item label="git">
                  {String(repro.git_ref ?? "")}
                </Descriptions.Item>
                <Descriptions.Item label="env hash">
                  {String(repro.environment_hash ?? "")}
                </Descriptions.Item>
              </Descriptions>
            ),
          },
          {
            key: "stdout",
            label: "stdout",
            children: (
              <pre style={{ fontSize: 11, background: "#fafafa", padding: 8 }}>
                {stdout ?? "(none)"}
              </pre>
            ),
          },
          {
            key: "stderr",
            label: "stderr",
            children: (
              <pre style={{ fontSize: 11, background: "#fff1f0", padding: 8 }}>
                {stderr ?? "(none)"}
              </pre>
            ),
          },
        ]}
      />
    </Card>
  );
}
