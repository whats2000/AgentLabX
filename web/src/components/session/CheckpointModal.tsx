import { useMemo, useState } from "react";
import { Alert, Button, Modal, Space, Typography, message } from "antd";
import {
  CheckOutlined,
  CloseOutlined,
  ForwardOutlined,
} from "@ant-design/icons";
import { useWSStore } from "../../stores/wsStore";
import { wsRegistry } from "../../api/wsRegistry";
import { RedirectModal } from "./RedirectModal";
import { usePIHistory } from "../../hooks/usePIHistory";
import type { ClientAction, PipelineEvent } from "../../types/events";

const { Text, Paragraph } = Typography;

/** Shown when the backend returns an unexpected error on approve/reject. */
const CHECKPOINT_ERROR_NOTE =
  "Failed to send checkpoint action. Check console for details.";

/** Minimum confidence required to surface PI advice in the modal banner. */
const PI_ADVICE_CONFIDENCE_THRESHOLD = 0.6;

interface CheckpointPayload {
  stage?: string;
  pi_recommendation?: string;
  output?: string;
  [k: string]: unknown;
}

const EMPTY: PipelineEvent[] = [];

interface Props {
  sessionId: string;
}

export function CheckpointModal({ sessionId }: Props) {
  const events = useWSStore((s) => s.events[sessionId] ?? EMPTY);

  // Fetch PI advisor decision history to surface high-confidence advice.
  const { data: piHistory } = usePIHistory(sessionId);
  const latestPIDecision =
    piHistory && piHistory.length > 0 ? piHistory[piHistory.length - 1] : null;
  const shouldSurfacePIAdvice =
    latestPIDecision !== null &&
    latestPIDecision !== undefined &&
    latestPIDecision.used_fallback === false &&
    latestPIDecision.confidence >= PI_ADVICE_CONFIDENCE_THRESHOLD;

  // Pull the most recent checkpoint_reached event. We key the modal by the
  // event's (timestamp, stage) so when a new one arrives it re-opens.
  const latestCheckpoint = useMemo(() => {
    for (let i = events.length - 1; i >= 0; i -= 1) {
      if (events[i].type === "checkpoint_reached") {
        return events[i] as PipelineEvent<CheckpointPayload>;
      }
    }
    return null;
  }, [events]);

  const [dismissedKey, setDismissedKey] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [redirectOpen, setRedirectOpen] = useState(false);

  const currentKey = latestCheckpoint
    ? `${latestCheckpoint.timestamp ?? ""}-${latestCheckpoint.data?.stage ?? ""}`
    : null;
  const open =
    latestCheckpoint !== null &&
    currentKey !== null &&
    dismissedKey !== currentKey;

  const close = () => {
    if (currentKey) setDismissedKey(currentKey);
  };

  const sendAction = async (action: ClientAction) => {
    // approve / reject: call the backend checkpoint endpoint to resume the
    // paused pipeline (Plan 7E A2). redirect / edit are deferred (501).
    if (action.action === "approve" || action.action === "reject") {
      setSubmitting(true);
      try {
        const resp = await fetch(
          `/api/sessions/${sessionId}/checkpoint/approve`,
          {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ action: action.action, reason: action.reason }),
          },
        );
        if (!resp.ok) {
          const detail = await resp.json().catch(() => ({}));
          if (resp.status === 501) {
            message.warning(
              detail?.detail ?? "This action is not yet supported.",
            );
          } else {
            message.error(CHECKPOINT_ERROR_NOTE);
            console.error("checkpoint/approve error", resp.status, detail);
          }
          return;
        }
      } catch (err) {
        message.error(CHECKPOINT_ERROR_NOTE);
        console.error("checkpoint/approve fetch error", err);
        return;
      } finally {
        setSubmitting(false);
      }
    } else {
      // edit / redirect: send over WS as before (deferred path, backend returns 501
      // for edit; redirect goes via RedirectModal which has its own endpoint)
      const socket = wsRegistry.getSocket(sessionId);
      if (!socket) {
        message.warning("Not connected.");
        return;
      }
      socket.send(action);
    }
    close();
  };

  const stage = latestCheckpoint?.data?.stage ?? "unknown";
  const piRec = latestCheckpoint?.data?.pi_recommendation;
  const output = latestCheckpoint?.data?.output;

  return (
    <>
      <Modal
        open={open}
        onCancel={close}
        title={`Checkpoint: ${stage}`}
        footer={null}
        destroyOnHidden
        width={640}
      >
        <Space direction="vertical" size={16} style={{ width: "100%" }}>
          {shouldSurfacePIAdvice && latestPIDecision && (
            <Alert
              type="info"
              showIcon
              message={
                <span>
                  PI advisor recommends{" "}
                  <strong>{latestPIDecision.next_stage ?? "(no stage)"}</strong>
                  {" "}
                  ({Math.round(latestPIDecision.confidence * 100)}% confidence)
                </span>
              }
              description={latestPIDecision.reasoning}
              style={{ marginBottom: 0 }}
            />
          )}
          {piRec ? (
            <div>
              <Text
                type="secondary"
                style={{
                  fontSize: 11,
                  textTransform: "uppercase",
                  letterSpacing: 0.05,
                }}
              >
                PI recommendation
              </Text>
              <Paragraph style={{ margin: 0 }}>{piRec}</Paragraph>
            </div>
          ) : (
            <Text type="secondary">Waiting for PI assessment...</Text>
          )}

          {output ? (
            <div>
              <Text
                type="secondary"
                style={{
                  fontSize: 11,
                  textTransform: "uppercase",
                  letterSpacing: 0.05,
                }}
              >
                Stage output
              </Text>
              <pre
                style={{
                  whiteSpace: "pre-wrap",
                  fontSize: 12,
                  background: "#fafafa",
                  padding: 12,
                  borderRadius: 8,
                  maxHeight: 240,
                  overflow: "auto",
                  margin: 0,
                }}
              >
                {output}
              </pre>
            </div>
          ) : null}

          <Space style={{ justifyContent: "flex-end", width: "100%" }}>
            <Button
              icon={<ForwardOutlined />}
              onClick={() => setRedirectOpen(true)}
            >
              Redirect
            </Button>
            <Button
              icon={<CloseOutlined />}
              onClick={() => sendAction({ action: "reject" })}
              loading={submitting}
              disabled={submitting}
            >
              Reject
            </Button>
            <Button
              type="primary"
              icon={<CheckOutlined />}
              onClick={() => sendAction({ action: "approve" })}
              loading={submitting}
              disabled={submitting}
            >
              Approve
            </Button>
          </Space>
        </Space>
      </Modal>
      <RedirectModal
        sessionId={sessionId}
        open={redirectOpen}
        onClose={() => {
          setRedirectOpen(false);
          // Redirect was chosen; also dismiss the checkpoint modal.
          close();
        }}
      />
    </>
  );
}
