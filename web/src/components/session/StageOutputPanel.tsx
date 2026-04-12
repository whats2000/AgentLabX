import { useMemo, useState } from "react";
import {
  Button,
  Card,
  Collapse,
  Empty,
  Space,
  Table,
  Tabs,
  Tag,
  Typography,
  message,
} from "antd";
import {
  CopyOutlined,
  ExperimentOutlined,
  FileTextOutlined,
  LeftOutlined,
  RightOutlined,
} from "@ant-design/icons";
import { useArtifacts } from "../../hooks/useArtifacts";
import type {
  ArtifactsPayload,
  EDAResult,
  ExperimentResult,
  LitReviewResult,
  ReportResult,
  ResearchPlan,
  ReviewResult,
} from "../../types/artifacts";

const { Text, Paragraph, Title } = Typography;

interface Props {
  sessionId: string;
  compact?: boolean;
}

const EMPTY_ARTIFACTS: ArtifactsPayload = {
  literature_review: [],
  plan: [],
  data_exploration: [],
  dataset_code: [],
  experiment_results: [],
  interpretation: [],
  report: [],
  review: [],
};

function LitReviewView({ item }: { item: LitReviewResult }) {
  return (
    <div>
      <Paragraph>{item.summary}</Paragraph>
      <Table
        size="small"
        rowKey={(row) => row.title}
        pagination={false}
        dataSource={item.papers}
        columns={[
          { title: "Title", dataIndex: "title", key: "title" },
          { title: "Year", dataIndex: "year", key: "year", width: 80 },
          {
            title: "Authors",
            dataIndex: "authors",
            key: "authors",
            ellipsis: true,
          },
        ]}
      />
    </div>
  );
}

function PlanView({ item }: { item: ResearchPlan }) {
  return (
    <div>
      <Title level={5} style={{ marginTop: 0 }}>
        Goals
      </Title>
      <ul>
        {item.goals.map((g, i) => (
          <li key={i}>{g}</li>
        ))}
      </ul>
      <Title level={5}>Methodology</Title>
      <Paragraph>{item.methodology}</Paragraph>
      <Title level={5}>Hypotheses</Title>
      <ul>
        {item.hypotheses.map((h, i) => (
          <li key={i}>{h}</li>
        ))}
      </ul>
      <Collapse
        ghost
        items={[
          {
            key: "full",
            label: "Full plan text",
            children: (
              <pre style={{ whiteSpace: "pre-wrap", fontSize: 12 }}>
                {item.full_text}
              </pre>
            ),
          },
        ]}
      />
    </div>
  );
}

function EDAView({ item }: { item: EDAResult }) {
  return (
    <div>
      <Title level={5} style={{ marginTop: 0 }}>
        Findings
      </Title>
      <ul>
        {item.findings.map((f, i) => (
          <li key={i}>{f}</li>
        ))}
      </ul>
      <Title level={5}>Data quality issues</Title>
      {item.data_quality_issues.length === 0 ? (
        <Text type="secondary">None reported</Text>
      ) : (
        <ul>
          {item.data_quality_issues.map((f, i) => (
            <li key={i}>{f}</li>
          ))}
        </ul>
      )}
      <Title level={5}>Recommendations</Title>
      <ul>
        {item.recommendations.map((f, i) => (
          <li key={i}>{f}</li>
        ))}
      </ul>
    </div>
  );
}

function DatasetCodeView({ item }: { item: string }) {
  return (
    <pre style={{ whiteSpace: "pre-wrap", fontSize: 12, margin: 0 }}>
      {item}
    </pre>
  );
}

function ExperimentView({ item }: { item: ExperimentResult }) {
  const tagColor =
    item.tag === "baseline"
      ? "default"
      : item.tag === "main"
        ? "green"
        : "gold";
  return (
    <div>
      <Space size={12} style={{ marginBottom: 12 }}>
        <Tag color={tagColor} bordered={false}>
          {item.tag}
        </Tag>
        {item.hypothesis_id ? (
          <Text type="secondary" style={{ fontSize: 12 }}>
            hypothesis: {item.hypothesis_id}
          </Text>
        ) : null}
      </Space>
      <Paragraph>{item.description}</Paragraph>
      <div
        style={{
          display: "grid",
          gridTemplateColumns: "repeat(auto-fit, minmax(140px, 1fr))",
          gap: 8,
          marginBottom: 12,
        }}
      >
        {Object.entries(item.metrics).map(([k, v]) => (
          <Card
            key={k}
            size="small"
            variant="borderless"
            style={{ background: "#fafafa" }}
          >
            <Text type="secondary" style={{ fontSize: 11 }}>
              {k}
            </Text>
            <div style={{ fontSize: 18, fontWeight: 600 }}>{v}</div>
          </Card>
        ))}
      </div>
      {item.reproducibility ? (
        <Collapse
          ghost
          items={[
            {
              key: "repro",
              label: "Reproducibility",
              children: (
                <pre style={{ whiteSpace: "pre-wrap", fontSize: 11 }}>
                  {JSON.stringify(item.reproducibility, null, 2)}
                </pre>
              ),
            },
          ]}
        />
      ) : null}
    </div>
  );
}

function ReportView({ item }: { item: ReportResult }) {
  const copy = async () => {
    try {
      await navigator.clipboard.writeText(item.latex_source);
      message.success("LaTeX copied");
    } catch {
      message.error("Copy failed");
    }
  };
  return (
    <div>
      <div
        style={{
          display: "flex",
          justifyContent: "flex-end",
          marginBottom: 8,
        }}
      >
        <Button
          size="small"
          type="text"
          icon={<CopyOutlined />}
          onClick={copy}
        >
          Copy LaTeX
        </Button>
      </div>
      <pre
        style={{
          whiteSpace: "pre-wrap",
          fontSize: 12,
          background: "#fafafa",
          padding: 12,
          borderRadius: 8,
          maxHeight: 400,
          overflow: "auto",
          margin: 0,
        }}
      >
        {item.latex_source}
      </pre>
      {item.compiled_pdf_path ? (
        <Text type="secondary" style={{ fontSize: 12 }}>
          PDF: {item.compiled_pdf_path}
        </Text>
      ) : null}
    </div>
  );
}

function ReviewView({ item }: { item: ReviewResult }) {
  const decisionColor =
    item.decision === "accept"
      ? "green"
      : item.decision === "revise"
        ? "gold"
        : "red";
  return (
    <div>
      <Space size={12} style={{ marginBottom: 12 }}>
        <Tag color={decisionColor} bordered={false}>
          {item.decision}
        </Tag>
        <Text type="secondary" style={{ fontSize: 12 }}>
          {item.reviewer_id}
        </Text>
      </Space>
      <Table
        size="small"
        pagination={false}
        dataSource={Object.entries(item.scores).map(([k, v]) => ({
          key: k,
          k,
          v,
        }))}
        columns={[
          { title: "Criterion", dataIndex: "k", key: "k" },
          { title: "Score", dataIndex: "v", key: "v", width: 100 },
        ]}
      />
      <Paragraph style={{ marginTop: 12 }}>{item.feedback}</Paragraph>
    </div>
  );
}

function InterpretationView({ item }: { item: string }) {
  return <Paragraph style={{ whiteSpace: "pre-wrap" }}>{item}</Paragraph>;
}

function StageSection<T>({
  label,
  items,
  render,
}: {
  label: string;
  items: T[];
  render: (item: T, index: number) => React.ReactNode;
}) {
  // Track an offset from the latest rather than an absolute index so the
  // component always defaults to the newest version even when items arrive
  // asynchronously (initial render has items=[] then data populates).
  const [offsetFromLatest, setOffsetFromLatest] = useState(0);
  if (items.length === 0) {
    return (
      <Empty
        image={Empty.PRESENTED_IMAGE_SIMPLE}
        description={
          <Text type="secondary">No {label.toLowerCase()} yet.</Text>
        }
      />
    );
  }
  const clampedOffset = Math.min(offsetFromLatest, items.length - 1);
  const index = items.length - 1 - clampedOffset;
  const current = items[index];
  return (
    <div>
      {items.length > 1 ? (
        <Space style={{ marginBottom: 12 }}>
          <Button
            size="small"
            icon={<LeftOutlined />}
            disabled={index <= 0}
            onClick={() =>
              setOffsetFromLatest((o) => Math.min(o + 1, items.length - 1))
            }
          />
          <Text type="secondary" style={{ fontSize: 12 }}>
            Version {index + 1} of {items.length}
          </Text>
          <Button
            size="small"
            icon={<RightOutlined />}
            disabled={index >= items.length - 1}
            onClick={() => setOffsetFromLatest((o) => Math.max(o - 1, 0))}
          />
        </Space>
      ) : null}
      {render(current, index)}
    </div>
  );
}

export function StageOutputPanel({ sessionId, compact = false }: Props) {
  const { data } = useArtifacts(sessionId);
  const payload = (data ?? EMPTY_ARTIFACTS) as ArtifactsPayload;

  const sections: Array<{
    key: string;
    label: string;
    icon: React.ReactNode;
    count: number;
    node: React.ReactNode;
  }> = useMemo(
    () => [
      {
        key: "literature_review",
        label: "Literature",
        icon: <FileTextOutlined />,
        count: payload.literature_review.length,
        node: (
          <StageSection
            label="Literature reviews"
            items={payload.literature_review}
            render={(item) => <LitReviewView item={item} />}
          />
        ),
      },
      {
        key: "plan",
        label: "Plan",
        icon: <FileTextOutlined />,
        count: payload.plan.length,
        node: (
          <StageSection
            label="Plans"
            items={payload.plan}
            render={(item) => <PlanView item={item} />}
          />
        ),
      },
      {
        key: "data_exploration",
        label: "EDA",
        icon: <FileTextOutlined />,
        count: payload.data_exploration.length,
        node: (
          <StageSection
            label="EDA results"
            items={payload.data_exploration}
            render={(item) => <EDAView item={item} />}
          />
        ),
      },
      {
        key: "dataset_code",
        label: "Dataset",
        icon: <FileTextOutlined />,
        count: payload.dataset_code.length,
        node: (
          <StageSection
            label="Dataset code"
            items={payload.dataset_code}
            render={(item) => <DatasetCodeView item={item} />}
          />
        ),
      },
      {
        key: "experiment_results",
        label: "Experiments",
        icon: <ExperimentOutlined />,
        count: payload.experiment_results.length,
        node: (
          <StageSection
            label="Experiments"
            items={payload.experiment_results}
            render={(item) => <ExperimentView item={item} />}
          />
        ),
      },
      {
        key: "interpretation",
        label: "Interpretation",
        icon: <FileTextOutlined />,
        count: payload.interpretation.length,
        node: (
          <StageSection
            label="Interpretations"
            items={payload.interpretation}
            render={(item) => <InterpretationView item={item} />}
          />
        ),
      },
      {
        key: "report",
        label: "Report",
        icon: <FileTextOutlined />,
        count: payload.report.length,
        node: (
          <StageSection
            label="Reports"
            items={payload.report}
            render={(item) => <ReportView item={item} />}
          />
        ),
      },
      {
        key: "review",
        label: "Review",
        icon: <FileTextOutlined />,
        count: payload.review.length,
        node: (
          <StageSection
            label="Reviews"
            items={payload.review}
            render={(item) => <ReviewView item={item} />}
          />
        ),
      },
    ],
    [payload],
  );

  if (compact) {
    // Find the most recently populated section; show a tiny summary.
    const withContent = sections.filter((s) => s.count > 0);
    const latest = withContent[withContent.length - 1];
    if (!latest) {
      return (
        <Text type="secondary" style={{ fontSize: 12 }}>
          No outputs yet.
        </Text>
      );
    }
    return (
      <div>
        <Text
          type="secondary"
          style={{
            fontSize: 11,
            textTransform: "uppercase",
            letterSpacing: 0.05,
          }}
        >
          Latest: {latest.label}
        </Text>
        <div style={{ marginTop: 4, fontSize: 12 }}>
          {latest.count} version{latest.count === 1 ? "" : "s"}
        </div>
      </div>
    );
  }

  return (
    <Tabs
      size="small"
      defaultActiveKey={
        sections.find((s) => s.count > 0)?.key ?? "literature_review"
      }
      items={sections.map((s) => ({
        key: s.key,
        label: (
          <span>
            {s.icon} {s.label}{" "}
            {s.count > 0 ? <Tag bordered={false}>{s.count}</Tag> : null}
          </span>
        ),
        children: s.node,
      }))}
    />
  );
}
