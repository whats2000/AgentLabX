import { useState } from "react";
import {
  Button,
  Card,
  Collapse,
  Form,
  Input,
  InputNumber,
  Radio,
  Select,
  Space,
  Steps,
  Typography,
  message,
} from "antd";
import {
  ArrowLeftOutlined,
  ArrowRightOutlined,
  CheckOutlined,
} from "@ant-design/icons";
import { useNavigate } from "react-router-dom";
import { useCreateSession } from "../hooks/useCreateSession";
import type { ControlLevel, BacktrackControl } from "../types/domain";

const { Title, Text, Paragraph } = Typography;

const STAGES = [
  "literature_review",
  "plan_formulation",
  "data_exploration",
  "data_preparation",
  "experimentation",
  "results_interpretation",
  "report_writing",
  "peer_review",
] as const;

type Stage = (typeof STAGES)[number];

const CONTROL_LEVELS: ControlLevel[] = ["auto", "notify", "approve", "edit"];
const BACKTRACK_LEVELS: BacktrackControl[] = ["auto", "notify", "approve"];

interface WizardState {
  topic: string;
  user_id: string;
  skip_stages: Stage[];
  max_total_iterations: number;
  stage_controls: Record<Stage, ControlLevel>;
  backtrack_control: BacktrackControl;
}

const initialState: WizardState = {
  topic: "",
  user_id: "default",
  skip_stages: [],
  max_total_iterations: 50,
  stage_controls: Object.fromEntries(
    STAGES.map((s) => [s, "auto"]),
  ) as Record<Stage, ControlLevel>,
  backtrack_control: "auto",
};

/**
 * Convert wizard state → minimal SessionCreateRequest body.
 *
 * We intentionally omit keys whose values match the backend defaults so the
 * persisted config stays small and won't shadow future default changes.
 *
 * Mode (auto / hitl) is *not* part of the wizard — it's derived from the
 * per-stage controls at runtime, and users can flip it at any time from the
 * session detail ControlBar. Sending mode=hitl here would be redundant.
 */
export function buildCreateBody(s: WizardState) {
  const config: Record<string, unknown> = {};

  const pipeline: Record<string, unknown> = {};
  if (s.skip_stages.length) pipeline.skip_stages = s.skip_stages;
  if (s.max_total_iterations !== 50)
    pipeline.max_total_iterations = s.max_total_iterations;
  if (Object.keys(pipeline).length) config.pipeline = pipeline;

  const prefs: Record<string, unknown> = {};
  const nonAuto = Object.entries(s.stage_controls).filter(
    ([, v]) => v !== "auto",
  );
  if (nonAuto.length) prefs.stage_controls = Object.fromEntries(nonAuto);
  if (s.backtrack_control !== "auto")
    prefs.backtrack_control = s.backtrack_control;
  // If any oversight override is present, mark mode=hitl so the backend
  // respects the per-stage controls. Otherwise omit mode entirely and let
  // the backend default ("auto") apply.
  if (Object.keys(prefs).length) {
    prefs.mode = "hitl";
    config.preferences = prefs;
  }

  return {
    topic: s.topic.trim(),
    user_id: s.user_id.trim() || "default",
    config,
  };
}

function prettyStage(stage: string): string {
  return stage
    .split("_")
    .map((w) => w.charAt(0).toUpperCase() + w.slice(1))
    .join(" ");
}

interface SummaryRowProps {
  label: string;
  children: React.ReactNode;
}

function SummaryRow({ label, children }: SummaryRowProps) {
  return (
    <div
      style={{
        display: "flex",
        gap: 16,
        padding: "10px 0",
        borderBottom: "1px solid #f0f0f0",
      }}
    >
      <Text
        type="secondary"
        style={{ minWidth: 160, flexShrink: 0, fontSize: 13 }}
      >
        {label}
      </Text>
      <div style={{ flex: 1, fontSize: 14 }}>{children}</div>
    </div>
  );
}

export default function SessionCreatePage() {
  const navigate = useNavigate();
  const [step, setStep] = useState(0);
  const [state, setState] = useState<WizardState>(initialState);
  const createMutation = useCreateSession();

  const steps = ["Topic", "Pipeline", "Oversight", "Review"];

  const isStepValid = (s: number): boolean => {
    if (s === 0) return state.topic.trim().length >= 10;
    if (s === 1) return state.max_total_iterations >= 5;
    return true;
  };

  const update = <K extends keyof WizardState>(key: K, value: WizardState[K]) =>
    setState((prev) => ({ ...prev, [key]: value }));

  const stepContent = (() => {
    switch (step) {
      case 0:
        return (
          <Form layout="vertical" size="large">
            <Paragraph type="secondary" style={{ marginTop: 0 }}>
              Describe the research question. This seed text drives every
              downstream stage, so be specific about goals, scope, and any
              constraints.
            </Paragraph>
            <Form.Item
              label="Research topic"
              required
              help="At least 10 characters. Be specific — this guides every stage."
            >
              <Input.TextArea
                placeholder="Describe your research question..."
                rows={5}
                value={state.topic}
                onChange={(e) => update("topic", e.target.value)}
                maxLength={2000}
                showCount
              />
            </Form.Item>
            <Form.Item
              label="User ID"
              help="Optional. Used to attribute this session. Defaults to 'default'."
            >
              <Input
                placeholder="default"
                value={state.user_id}
                onChange={(e) => update("user_id", e.target.value)}
              />
            </Form.Item>
          </Form>
        );

      case 1:
        return (
          <Form layout="vertical" size="large">
            <Paragraph type="secondary" style={{ marginTop: 0 }}>
              Pick which stages to run and an iteration ceiling. You can still
              adjust pacing and oversight after the session starts.
            </Paragraph>
            <Form.Item
              label="Skip stages"
              help="Leave empty to run the full 8-stage pipeline."
            >
              <Select
                mode="multiple"
                allowClear
                placeholder="Select stages to skip"
                value={state.skip_stages}
                onChange={(v) => update("skip_stages", v as Stage[])}
                options={STAGES.map((s) => ({
                  label: prettyStage(s),
                  value: s,
                }))}
              />
            </Form.Item>
            <Form.Item
              label="Max total iterations"
              help="Hard ceiling across all stages. Default 50."
            >
              <InputNumber
                min={5}
                max={500}
                value={state.max_total_iterations}
                onChange={(v) =>
                  update("max_total_iterations", typeof v === "number" ? v : 50)
                }
                style={{ width: 160 }}
              />
            </Form.Item>
          </Form>
        );

      case 2:
        return (
          <Form layout="vertical" size="large">
            <Paragraph type="secondary" style={{ marginTop: 0 }}>
              Optional. Stages left on <Text code>auto</Text> run without
              prompts; anything else pauses for your input at that stage. You
              can flip any stage live from the session detail sidebar.
            </Paragraph>
            <div style={{ marginBottom: 24 }}>
              <Text strong>Per-stage controls</Text>
              <div
                style={{
                  marginTop: 12,
                  border: "1px solid #f0f0f0",
                  borderRadius: 8,
                }}
              >
                {STAGES.map((stage, idx) => (
                  <div
                    key={stage}
                    style={{
                      display: "flex",
                      alignItems: "center",
                      justifyContent: "space-between",
                      padding: "12px 16px",
                      borderBottom:
                        idx < STAGES.length - 1 ? "1px solid #f0f0f0" : "none",
                    }}
                  >
                    <Text style={{ fontSize: 14 }}>{prettyStage(stage)}</Text>
                    <Radio.Group
                      size="small"
                      value={state.stage_controls[stage]}
                      onChange={(e) =>
                        setState((prev) => ({
                          ...prev,
                          stage_controls: {
                            ...prev.stage_controls,
                            [stage]: e.target.value as ControlLevel,
                          },
                        }))
                      }
                    >
                      {CONTROL_LEVELS.map((lvl) => (
                        <Radio.Button key={lvl} value={lvl}>
                          {lvl}
                        </Radio.Button>
                      ))}
                    </Radio.Group>
                  </div>
                ))}
              </div>
            </div>
            <Form.Item
              label="Backtrack control"
              help="How to handle stage transitions that revisit earlier work."
            >
              <Radio.Group
                value={state.backtrack_control}
                onChange={(e) =>
                  update(
                    "backtrack_control",
                    e.target.value as BacktrackControl,
                  )
                }
              >
                {BACKTRACK_LEVELS.map((lvl) => (
                  <Radio.Button key={lvl} value={lvl}>
                    {lvl}
                  </Radio.Button>
                ))}
              </Radio.Group>
            </Form.Item>
          </Form>
        );

      case 3: {
        const body = buildCreateBody(state);
        const hitlOverrides = Object.entries(state.stage_controls).filter(
          ([, v]) => v !== "auto",
        );
        return (
          <div>
            <Paragraph type="secondary" style={{ marginTop: 0 }}>
              Review your configuration before launching.
            </Paragraph>
            <div style={{ marginBottom: 24 }}>
              <SummaryRow label="Topic">
                <Text>{state.topic.trim() || "(empty)"}</Text>
              </SummaryRow>
              <SummaryRow label="User ID">
                <Text>{state.user_id.trim() || "default"}</Text>
              </SummaryRow>
              <SummaryRow label="Skip stages">
                <Text>
                  {state.skip_stages.length
                    ? state.skip_stages.map(prettyStage).join(", ")
                    : "(none)"}
                </Text>
              </SummaryRow>
              <SummaryRow label="Max iterations">
                <Text>{state.max_total_iterations}</Text>
              </SummaryRow>
              <SummaryRow label="Stage overrides">
                <Text>
                  {hitlOverrides.length
                    ? hitlOverrides
                        .map(([s, v]) => `${prettyStage(s)}: ${v}`)
                        .join(", ")
                    : "(all auto)"}
                </Text>
              </SummaryRow>
              {state.backtrack_control !== "auto" && (
                <SummaryRow label="Backtrack control">
                  <Text>{state.backtrack_control}</Text>
                </SummaryRow>
              )}
            </div>
            <Collapse
              items={[
                {
                  key: "json",
                  label: "Show request JSON",
                  children: (
                    <pre
                      style={{
                        margin: 0,
                        fontSize: 12,
                        background: "#fafafa",
                        padding: 12,
                        borderRadius: 6,
                        overflow: "auto",
                      }}
                    >
                      {JSON.stringify(body, null, 2)}
                    </pre>
                  ),
                },
              ]}
            />
          </div>
        );
      }

      default:
        return null;
    }
  })();

  const handleNext = () => setStep((s) => Math.min(s + 1, steps.length - 1));
  const handlePrev = () => setStep((s) => Math.max(s - 1, 0));

  const handleSubmit = async () => {
    try {
      const body = buildCreateBody(state);
      const session = await createMutation.mutateAsync(body);
      message.success("Session created");
      navigate(`/sessions/${session.session_id}`);
    } catch (err) {
      message.error(err instanceof Error ? err.message : "Create failed");
    }
  };

  return (
    <div>
      <div style={{ marginBottom: 24 }}>
        <Title level={3} style={{ margin: 0, fontWeight: 600 }}>
          New session
        </Title>
        <Text type="secondary">Configure your research run, then launch.</Text>
      </div>
      <Card variant="borderless">
        <Steps
          current={step}
          size="small"
          items={steps.map((s) => ({ title: s }))}
          style={{ marginBottom: 32 }}
        />
        <div style={{ minHeight: 280 }}>{stepContent}</div>
        <div
          style={{
            display: "flex",
            justifyContent: "space-between",
            marginTop: 32,
            paddingTop: 16,
            borderTop: "1px solid #f0f0f0",
          }}
        >
          <Space>
            <Button
              type="text"
              icon={<ArrowLeftOutlined />}
              onClick={handlePrev}
              disabled={step === 0}
            >
              Previous
            </Button>
            <Button type="text" onClick={() => navigate("/sessions")}>
              Cancel
            </Button>
          </Space>
          {step < steps.length - 1 ? (
            <Button
              type="primary"
              onClick={handleNext}
              disabled={!isStepValid(step)}
            >
              Next <ArrowRightOutlined />
            </Button>
          ) : (
            <Button
              type="primary"
              icon={<CheckOutlined />}
              onClick={handleSubmit}
              loading={createMutation.isPending}
              disabled={!isStepValid(0)}
            >
              Create session
            </Button>
          )}
        </div>
      </Card>
    </div>
  );
}
