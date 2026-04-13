import { useState } from "react";
import {
  Button,
  Segmented,
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
import { RedirectModal } from "./RedirectModal";

const { Text } = Typography;

type BacktrackControl = "auto" | "notify" | "approve";
type Mode = "auto" | "hitl";

interface Props {
  sessionId: string;
  /** "vertical" (default) stacks controls in a column; "horizontal" renders inline. */
  layout?: "vertical" | "horizontal";
}

const SECTION_LABEL_STYLE: React.CSSProperties = {
  fontSize: 11,
  textTransform: "uppercase",
  letterSpacing: 0.05,
};

export function ControlBar({ sessionId, layout = "vertical" }: Props) {
  const { data: session } = useSession(sessionId);
  const [redirectOpen, setRedirectOpen] = useState(false);

  const status = session?.status ?? "created";
  const preferences = (session?.preferences ?? {}) as {
    mode?: Mode;
    backtrack_control?: BacktrackControl;
  };
  const mode: Mode = preferences.mode ?? "auto";
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
      <Button disabled>
        {status === "completed" ? "Completed" : "Failed"}
      </Button>
    );
  }

  const isTerminal = status === "completed" || status === "failed";

  if (layout === "horizontal") {
    return (
      <Space wrap align="center" size={16}>
        <StatusBadge status={status} />
        {primaryAction}
        <Space align="center" size={4}>
          <Text type="secondary" style={SECTION_LABEL_STYLE}>
            Mode
          </Text>
          <Segmented
            size="small"
            value={mode}
            disabled={isTerminal}
            onChange={(value) => updatePrefs.mutate({ mode: value as Mode })}
            options={[
              { label: "Auto", value: "auto" },
              { label: "HITL", value: "hitl" },
            ]}
          />
        </Space>
        <Space align="center" size={4}>
          <Text type="secondary" style={SECTION_LABEL_STYLE}>
            Backtrack
          </Text>
          <Segmented
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
          />
        </Space>
        <Button
          type="text"
          icon={<ForwardOutlined />}
          disabled={status !== "running"}
          onClick={() => setRedirectOpen(true)}
        >
          Redirect...
        </Button>
        <RedirectModal
          sessionId={sessionId}
          open={redirectOpen}
          onClose={() => setRedirectOpen(false)}
        />
      </Space>
    );
  }

  // Vertical layout (default — original behavior)
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
