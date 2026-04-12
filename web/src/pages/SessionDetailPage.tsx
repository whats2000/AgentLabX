import { Layout, Tabs, Typography, Alert, Skeleton, Card } from "antd";
import { useParams, Link } from "react-router-dom";
import { useSession } from "../hooks/useSession";
import { useWebSocket } from "../hooks/useWebSocket";
import { useUIStore } from "../stores/uiStore";
import { StatusBadge } from "../components/common/StatusBadge";
import { ControlBar } from "../components/session/ControlBar";
import { PipelineTracker } from "../components/session/PipelineTracker";
import { PipelineGraph } from "../components/session/PipelineGraph";
import { AgentActivityFeed } from "../components/session/AgentActivityFeed";
import { StageOutputPanel } from "../components/session/StageOutputPanel";
import { HypothesisTracker } from "../components/session/HypothesisTracker";
import { CostTracker } from "../components/session/CostTracker";
import { FeedbackInput } from "../components/session/FeedbackInput";

const { Sider, Content } = Layout;
const { Title, Text } = Typography;

function SectionHeader({ children }: { children: React.ReactNode }) {
  return (
    <div
      style={{
        padding: "12px 16px 8px",
        color: "#6b7280",
        fontSize: 11,
        fontWeight: 600,
        textTransform: "uppercase",
        letterSpacing: "0.05em",
      }}
    >
      {children}
    </div>
  );
}

export default function SessionDetailPage() {
  const { sessionId = "" } = useParams();
  const { data: session, isLoading, error } = useSession(sessionId);
  const detailTab = useUIStore((s) => s.detailTab);
  const setDetailTab = useUIStore((s) => s.setDetailTab);

  // Wire the session-scoped WebSocket; auto-invalidates TanStack cache (Fix H).
  useWebSocket(sessionId);

  if (error) {
    return (
      <Alert
        type="error"
        showIcon
        message="Failed to load session"
        description={
          <>
            {error instanceof Error ? error.message : String(error)}{" "}
            <Link to="/sessions">Back to sessions</Link>
          </>
        }
      />
    );
  }

  if (isLoading || !session) {
    return (
      <Card variant="borderless">
        <Skeleton active paragraph={{ rows: 4 }} />
      </Card>
    );
  }

  // Outer flex column so the sticky FeedbackInput gets its own row that spans
  // the full width (Fix K). The inner Layout handles the three columns.
  return (
    <div
      style={{
        display: "flex",
        flexDirection: "column",
        // Subtract shell padding (32px top + 32px bottom = 64) from 100vh,
        // then account for the 56px header
        minHeight: "calc(100vh - 56px - 64px)",
      }}
    >
      {/* Topline identity */}
      <div style={{ marginBottom: 16 }}>
        <div
          style={{
            display: "flex",
            justifyContent: "space-between",
            alignItems: "flex-start",
            gap: 16,
          }}
        >
          <div>
            <Title level={3} style={{ margin: 0, fontWeight: 600 }}>
              {session.research_topic}
            </Title>
            <Text type="secondary" style={{ fontSize: 12 }}>
              {session.session_id} · {session.user_id}
            </Text>
          </div>
          <StatusBadge status={session.status} />
        </div>
      </div>

      {/* 3-column layout */}
      <Card
        variant="borderless"
        styles={{ body: { padding: 0 } }}
        style={{ flex: 1, overflow: "hidden", display: "flex" }}
      >
        <Layout style={{ background: "transparent", flex: 1 }}>
          <Sider
            width={260}
            theme="light"
            style={{
              background: "#ffffff",
              borderRight: "1px solid #efefef",
            }}
          >
            <SectionHeader>Controls</SectionHeader>
            <ControlBar sessionId={sessionId} />
            <SectionHeader>Pipeline</SectionHeader>
            <PipelineTracker sessionId={sessionId} />
          </Sider>

          <Content style={{ background: "#ffffff", padding: "12px 24px" }}>
            <Tabs
              activeKey={detailTab}
              onChange={(key) => setDetailTab(key as typeof detailTab)}
              type="line"
              items={[
                {
                  key: "activity",
                  label: "Activity",
                  children: <AgentActivityFeed sessionId={sessionId} />,
                },
                {
                  key: "artifacts",
                  label: "Artifacts",
                  children: <StageOutputPanel sessionId={sessionId} />,
                },
                {
                  key: "graph",
                  label: "Graph",
                  children: <PipelineGraph sessionId={sessionId} />,
                },
                {
                  key: "cost",
                  label: "Cost",
                  children: <CostTracker sessionId={sessionId} />,
                },
              ]}
            />
          </Content>

          <Sider
            width={300}
            theme="light"
            style={{
              background: "#ffffff",
              borderLeft: "1px solid #efefef",
            }}
          >
            <SectionHeader>Current stage</SectionHeader>
            <div style={{ padding: "0 16px 16px" }}>
              <StageOutputPanel sessionId={sessionId} compact />
            </div>
            <div style={{ borderTop: "1px solid #efefef" }} />
            <SectionHeader>Hypotheses</SectionHeader>
            <HypothesisTracker sessionId={sessionId} />
            <div style={{ borderTop: "1px solid #efefef" }} />
            <SectionHeader>Cost</SectionHeader>
            <CostTracker sessionId={sessionId} compact />
          </Sider>
        </Layout>
      </Card>

      {/* Sticky feedback bar — outside the Layout so it spans full width */}
      <div
        style={{
          position: "sticky",
          bottom: 0,
          marginTop: 16,
          background: "#ffffff",
          border: "1px solid #efefef",
          borderRadius: 12,
          padding: 12,
        }}
      >
        <FeedbackInput sessionId={sessionId} />
      </div>
    </div>
  );
}
