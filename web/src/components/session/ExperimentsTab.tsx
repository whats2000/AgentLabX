import { Alert, Empty, Skeleton, Typography, Tag } from "antd";
import { useExperiments } from "../../hooks/useExperiments";
import { ExperimentDetail } from "./ExperimentDetail";

const { Title, Text } = Typography;

export function ExperimentsTab({ sessionId }: { sessionId: string }) {
  const { data, isLoading } = useExperiments(sessionId);
  if (isLoading) return <Skeleton active />;
  if (!data || (data.runs.length === 0 && data.log.length === 0)) {
    return <Empty description="No experiments yet" />;
  }

  const failures = (data.log as Array<Record<string, unknown>>).filter(
    (a) => a.outcome === "failure"
  );

  return (
    <div>
      {failures.length > 0 && (
        <Alert
          type="warning"
          showIcon
          message={
            <Title level={5} style={{ margin: 0 }}>
              Prior attempts — {failures.length} failed
            </Title>
          }
          description={
            <ul style={{ margin: 0, paddingLeft: 20 }}>
              {failures.slice(-5).map((f, i) => (
                <li key={(f.attempt_id as string) ?? i}>
                  <Text>{(f.approach_summary as string) || "(no summary)"}</Text>
                  <Tag color="red" style={{ marginLeft: 8 }}>
                    {f.failure_reason as string}
                  </Tag>
                </li>
              ))}
            </ul>
          }
          style={{ marginBottom: 16 }}
        />
      )}
      {data.runs.map((run, i) => (
        <ExperimentDetail key={(run.index as number | undefined) ?? i} run={run} />
      ))}
    </div>
  );
}
