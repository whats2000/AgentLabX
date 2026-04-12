import { useEffect, useMemo, useRef, useState } from "react";
import { Button, Empty, Tooltip, Typography } from "antd";
import {
  ArrowRightOutlined,
  ArrowUpOutlined,
  CheckCircleOutlined,
  CloseCircleOutlined,
  InfoCircleOutlined,
  MessageOutlined,
  PlayCircleOutlined,
  ToolOutlined,
} from "@ant-design/icons";
import { useWSStore } from "../../stores/wsStore";
import type { PipelineEvent, PipelineEventType } from "../../types/events";
import { formatRelative } from "../../lib/relativeTime";

const { Text } = Typography;

// Stable empty reference so the zustand selector returns the same array
// across renders when a session has no events yet (avoids getSnapshot
// caching warnings and infinite render loops).
const EMPTY_EVENTS: PipelineEvent[] = [];

interface IconMeta {
  icon: React.ReactNode;
  color: string;
}

function iconFor(type: PipelineEventType): IconMeta {
  switch (type) {
    case "stage_started":
      return { icon: <PlayCircleOutlined />, color: "#3b82f6" };
    case "stage_completed":
      return { icon: <CheckCircleOutlined />, color: "#10a37f" };
    case "stage_failed":
      return { icon: <CloseCircleOutlined />, color: "#ef4444" };
    case "transition":
      return { icon: <ArrowRightOutlined />, color: "#6b7280" };
    case "cost_update":
      return { icon: <InfoCircleOutlined />, color: "#6366f1" };
    case "agent_thinking":
      return { icon: <MessageOutlined />, color: "#94a3b8" };
    case "agent_tool_call":
      return { icon: <ToolOutlined />, color: "#f59e0b" };
    case "agent_dialogue":
      return { icon: <MessageOutlined />, color: "#64748b" };
    case "error":
      return { icon: <CloseCircleOutlined />, color: "#ef4444" };
    default:
      return { icon: <InfoCircleOutlined />, color: "#9ca3af" };
  }
}

function titleFor(event: PipelineEvent): string {
  const d = event.data as Record<string, unknown> | null | undefined;
  switch (event.type) {
    case "stage_started":
      return `Stage ${d?.stage ?? "?"} started`;
    case "stage_completed":
      return `Stage ${d?.stage ?? "?"} completed`;
    case "stage_failed":
      return `Stage ${d?.stage ?? "?"} failed`;
    case "transition":
      return `Transition ${d?.from ?? "?"} → ${d?.to ?? "?"}`;
    case "cost_update":
      return `Cost update`;
    case "agent_thinking":
      return `${(d?.agent as string) ?? "Agent"} thinking`;
    case "agent_tool_call":
      return `${(d?.agent as string) ?? "Agent"} called ${d?.tool ?? "?"}`;
    case "agent_dialogue":
      return `${(d?.agent as string) ?? "Agent"}: ${d?.text ?? ""}`;
    case "error":
      return `Error`;
    default:
      return event.type;
  }
}

function subtitleFor(event: PipelineEvent): string | null {
  const d = event.data as Record<string, unknown> | null | undefined;
  switch (event.type) {
    case "stage_completed":
      return (d?.reason as string) || null;
    case "stage_failed":
      return (d?.message as string) || (d?.error_type as string) || null;
    case "transition":
      return (d?.reason as string) || null;
    case "cost_update": {
      const tc = d?.total_cost;
      return typeof tc === "number" ? `$${tc.toFixed(4)}` : null;
    }
    case "agent_thinking":
    case "agent_dialogue":
      return (d?.text as string) || null;
    case "error":
      return (d?.message as string) || null;
    default:
      return null;
  }
}

interface Props {
  sessionId: string;
}

export function AgentActivityFeed({ sessionId }: Props) {
  const events = useWSStore((s) => s.events[sessionId] ?? EMPTY_EVENTS);
  const containerRef = useRef<HTMLDivElement | null>(null);
  const [autoScroll, setAutoScroll] = useState(true);
  const [now, setNow] = useState(Date.now());

  // Newest first
  const ordered = useMemo(() => [...events].reverse(), [events]);

  // Refresh relative timestamps every 30s
  useEffect(() => {
    const id = window.setInterval(() => setNow(Date.now()), 30_000);
    return () => window.clearInterval(id);
  }, []);

  // Track user scroll to gate auto-scroll
  function handleScroll(): void {
    const el = containerRef.current;
    if (!el) return;
    setAutoScroll(el.scrollTop < 40);
  }

  // On new events, snap to top if auto-scroll is on
  useEffect(() => {
    if (!autoScroll) return;
    const el = containerRef.current;
    if (!el) return;
    el.scrollTop = 0;
  }, [ordered.length, autoScroll]);

  function scrollToTop(): void {
    const el = containerRef.current;
    if (!el) return;
    el.scrollTop = 0;
    setAutoScroll(true);
  }

  if (ordered.length === 0) {
    return (
      <div style={{ padding: 40 }}>
        <Empty
          image={Empty.PRESENTED_IMAGE_SIMPLE}
          description={
            <Text type="secondary">
              Activity will stream here once the session runs.
            </Text>
          }
        />
      </div>
    );
  }

  return (
    <div
      style={{
        position: "relative",
        height: "100%",
        minHeight: 400,
      }}
    >
      <div
        ref={containerRef}
        onScroll={handleScroll}
        style={{
          maxHeight: 560,
          overflowY: "auto",
          paddingRight: 4,
        }}
      >
        {ordered.map((event, i) => {
          const { icon, color } = iconFor(event.type);
          const title = titleFor(event);
          const subtitle = subtitleFor(event);
          return (
            <div
              key={`${event.type}-${event.timestamp ?? i}-${i}`}
              style={{
                display: "flex",
                gap: 12,
                padding: "12px 4px",
                borderBottom: "1px solid #f0f0f0",
                alignItems: "flex-start",
              }}
            >
              <span style={{ color, marginTop: 2 }}>{icon}</span>
              <div style={{ flex: 1, minWidth: 0 }}>
                <div
                  style={{
                    display: "flex",
                    justifyContent: "space-between",
                    alignItems: "baseline",
                    gap: 12,
                  }}
                >
                  <Text style={{ fontSize: 13, fontWeight: 500 }}>
                    {title}
                  </Text>
                  <Tooltip title={event.timestamp ?? "no timestamp"}>
                    <Text type="secondary" style={{ fontSize: 12 }}>
                      {formatRelative(event.timestamp, now)}
                    </Text>
                  </Tooltip>
                </div>
                {subtitle ? (
                  <div>
                    <Text
                      type="secondary"
                      style={{
                        fontSize: 12,
                        display: "block",
                        wordBreak: "break-word",
                      }}
                    >
                      {subtitle}
                    </Text>
                  </div>
                ) : null}
              </div>
            </div>
          );
        })}
      </div>

      {!autoScroll ? (
        <Button
          size="small"
          type="primary"
          icon={<ArrowUpOutlined />}
          onClick={scrollToTop}
          style={{
            position: "absolute",
            bottom: 16,
            right: 16,
            boxShadow: "0 2px 8px rgba(0,0,0,0.15)",
          }}
        >
          New events
        </Button>
      ) : null}
    </div>
  );
}
