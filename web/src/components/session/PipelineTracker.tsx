import type { ReactNode } from "react";
import { Steps } from "antd";
import {
  CheckCircleFilled,
  ClockCircleOutlined,
  LoadingOutlined,
} from "@ant-design/icons";
import { useSession } from "../../hooks/useSession";
import { STAGE_LABELS, STAGE_SEQUENCE } from "../../lib/pipelineStages";

interface Props {
  sessionId: string;
}

// SessionDetail in the generated schema does not yet expose current_stage /
// completed_stages fields (backend schema gap — see Task 16). We read them
// via a narrowed interface so the hook stays typed.
interface SessionWithStageInfo {
  current_stage?: string;
  completed_stages?: string[];
}

export function PipelineTracker({ sessionId }: Props) {
  const { data: session } = useSession(sessionId);
  const sessionExtra = (session ?? {}) as SessionWithStageInfo;
  const currentStage = sessionExtra.current_stage ?? "";
  const completed = new Set(sessionExtra.completed_stages ?? []);

  const currentIndex = STAGE_SEQUENCE.findIndex((s) => s === currentStage);

  const items = STAGE_SEQUENCE.map((stage, i) => {
    let status: "wait" | "process" | "finish" | "error" = "wait";
    let icon: ReactNode = <ClockCircleOutlined />;

    if (completed.has(stage)) {
      status = "finish";
      icon = <CheckCircleFilled style={{ color: "#10a37f" }} />;
    } else if (stage === currentStage) {
      status = "process";
      icon = <LoadingOutlined style={{ color: "#10a37f" }} />;
    } else if (currentIndex >= 0 && i < currentIndex) {
      // Passed but not in completed — treat as finished (best-effort)
      status = "finish";
      icon = <CheckCircleFilled style={{ color: "#a7f3d0" }} />;
    }

    return {
      key: stage,
      title: <span style={{ fontSize: 13 }}>{STAGE_LABELS[stage]}</span>,
      status,
      icon,
    };
  });

  return (
    <div style={{ padding: "8px 16px 16px" }}>
      <Steps
        direction="vertical"
        size="small"
        current={Math.max(currentIndex, 0)}
        items={items}
      />
    </div>
  );
}
