import { Tag } from "antd";
import type { SessionStatus } from "../../types/domain";

const STATUS_STYLES: Record<
  SessionStatus,
  { color: string; label: string }
> = {
  created: { color: "default", label: "Created" },
  running: { color: "green", label: "Running" },
  paused: { color: "gold", label: "Paused" },
  completed: { color: "blue", label: "Completed" },
  failed: { color: "red", label: "Failed" },
};

interface Props {
  status: SessionStatus | string;
}

export function StatusBadge({ status }: Props) {
  const style = STATUS_STYLES[status as SessionStatus] ?? {
    color: "default",
    label: status,
  };
  return (
    <Tag
      color={style.color}
      bordered={false}
      style={{ fontSize: 12, fontWeight: 500, padding: "0 10px" }}
    >
      {style.label}
    </Tag>
  );
}

// Alias for future clarity — new code should prefer StatusTag.
export { StatusBadge as StatusTag };
