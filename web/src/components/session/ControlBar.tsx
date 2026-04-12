import { useState } from "react";
import {
  Button,
  Collapse,
  Segmented,
  Select,
  Space,
  Typography,
  message,
} from "antd";
import {
  ForwardOutlined,
  PauseCircleOutlined,
  PlayCircleOutlined,
  RedoOutlined,
} from "@ant-design/icons";
import { useSession } from "../../hooks/useSession";
import {
  usePauseSession,
  useResumeSession,
  useStartSession,
  useUpdatePreferences,
} from "../../hooks/useSessionMutations";
import { StatusBadge } from "../common/StatusBadge";
import { STAGE_LABELS, STAGE_SEQUENCE } from "../../lib/pipelineStages";
import { RedirectModal } from "./RedirectModal";

const { Text } = Typography;

type ControlLevel = "auto" | "notify" | "approve" | "edit";
type BacktrackControl = "auto" | "notify" | "approve";
type Mode = "auto" | "hitl";

interface Props {
  sessionId: string;
}

const SECTION_LABEL_STYLE: React.CSSProperties = {
  fontSize: 11,
  textTransform: "uppercase",
  letterSpacing: 0.05,
};

export function ControlBar({ sessionId }: Props) {
  const { data: session } = useSession(sessionId);
  const [redirectOpen, setRedirectOpen] = useState(false);

  const status = session?.status ?? "created";
  const preferences = (session?.preferences ?? {}) as {
    mode?: Mode;
    stage_controls?: Record<string, ControlLevel>;
    backtrack_control?: BacktrackControl;
  };
  const mode: Mode = preferences.mode ?? "auto";
  const stageControls = preferences.stage_controls ?? {};
  const backtrackControl: BacktrackControl =
    preferences.backtrack_control ?? "auto";

  const startMutation = useStartSession(sessionId);
  const pauseMutation = usePauseSession(sessionId);
  const resumeMutation = useResumeSession(sessionId);
  const updatePrefs = useUpdatePreferences(sessionId);

  let primaryAction: React.ReactNode;
  if (status === "created") {
    primaryAction = (
      <Button
        type="primary"
        icon={<PlayCircleOutlined />}
        block
        loading={startMutation.isPending}
        onClick={async () => {
          try {
            await startMutation.mutateAsync();
          } catch (err) {
            message.error(err instanceof Error ? err.message : "Start failed");
          }
        }}
      >
        Start session
      </Button>
    );
  } else if (status === "running") {
    primaryAction = (
      <Button
        icon={<PauseCircleOutlined />}
        block
        loading={pauseMutation.isPending}
        onClick={async () => {
          try {
            await pauseMutation.mutateAsync();
          } catch (err) {
            message.error(err instanceof Error ? err.message : "Pause failed");
          }
        }}
      >
        Pause
      </Button>
    );
  } else if (status === "paused") {
    primaryAction = (
      <Button
        type="primary"
        icon={<RedoOutlined />}
        block
        loading={resumeMutation.isPending}
        onClick={async () => {
          try {
            await resumeMutation.mutateAsync();
          } catch (err) {
            message.error(err instanceof Error ? err.message : "Resume failed");
          }
        }}
      >
        Resume
      </Button>
    );
  } else {
    primaryAction = (
      <Button block disabled>
        {status === "completed" ? "Completed" : "Failed"}
      </Button>
    );
  }

  const isTerminal = status === "completed" || status === "failed";

  return (
    <div style={{ padding: 12 }}>
      <div
        style={{
          display: "flex",
          justifyContent: "space-between",
          alignItems: "center",
          marginBottom: 12,
        }}
      >
        <Text type="secondary" style={SECTION_LABEL_STYLE}>
          Status
        </Text>
        <StatusBadge status={status} />
      </div>

      <div style={{ marginBottom: 12 }}>{primaryAction}</div>

      <Space direction="vertical" style={{ width: "100%" }} size={12}>
        <div>
          <Text type="secondary" style={SECTION_LABEL_STYLE}>
            Mode
          </Text>
          <Segmented
            block
            size="small"
            value={mode}
            disabled={isTerminal}
            onChange={(value) => updatePrefs.mutate({ mode: value as Mode })}
            options={[
              { label: "Auto", value: "auto" },
              { label: "HITL", value: "hitl" },
            ]}
            style={{ marginTop: 4 }}
          />
        </div>

        <div>
          <Text type="secondary" style={SECTION_LABEL_STYLE}>
            Backtrack
          </Text>
          <Segmented
            block
            size="small"
            value={backtrackControl}
            disabled={isTerminal}
            onChange={(value) =>
              updatePrefs.mutate({
                backtrack_control: value as BacktrackControl,
              })
            }
            options={[
              { label: "Auto", value: "auto" },
              { label: "Notify", value: "notify" },
              { label: "Approve", value: "approve" },
            ]}
            style={{ marginTop: 4 }}
          />
        </div>

        {mode === "hitl" ? (
          <Collapse
            ghost
            size="small"
            items={[
              {
                key: "stage-controls",
                label: "Stage controls",
                children: (
                  <Space
                    direction="vertical"
                    size={4}
                    style={{ width: "100%" }}
                  >
                    {STAGE_SEQUENCE.map((stage) => {
                      const value = stageControls[stage] ?? "auto";
                      return (
                        <div
                          key={stage}
                          style={{
                            display: "flex",
                            gap: 8,
                            alignItems: "center",
                            justifyContent: "space-between",
                          }}
                        >
                          <Text style={{ fontSize: 12 }}>
                            {STAGE_LABELS[stage]}
                          </Text>
                          <Select
                            size="small"
                            value={value}
                            style={{ width: 100 }}
                            disabled={isTerminal}
                            onChange={(v) => {
                              updatePrefs.mutate({
                                stage_controls: {
                                  ...stageControls,
                                  [stage]: v as ControlLevel,
                                },
                              });
                            }}
                            options={[
                              { label: "Auto", value: "auto" },
                              { label: "Notify", value: "notify" },
                              { label: "Approve", value: "approve" },
                              { label: "Edit", value: "edit" },
                            ]}
                          />
                        </div>
                      );
                    })}
                  </Space>
                ),
              },
            ]}
          />
        ) : null}

        <Button
          type="text"
          icon={<ForwardOutlined />}
          block
          disabled={status !== "running"}
          onClick={() => setRedirectOpen(true)}
        >
          Redirect...
        </Button>
      </Space>

      <RedirectModal
        sessionId={sessionId}
        open={redirectOpen}
        onClose={() => setRedirectOpen(false)}
      />
    </div>
  );
}
