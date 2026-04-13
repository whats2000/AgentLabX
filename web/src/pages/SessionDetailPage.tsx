import { Layout, Tabs, Typography, Alert, Skeleton, Card } from "antd";
import { useParams, Link } from "react-router-dom";
import { useSession } from "../hooks/useSession";
import { useWebSocket } from "../hooks/useWebSocket";
import { useUIStore } from "../stores/uiStore";
import { StatusBadge } from "../components/common/StatusBadge";
import { ControlBar } from "../components/session/ControlBar";
import { GraphTopology } from "../components/session/GraphTopology";
import { ChatView } from "../components/session/ChatView";
import { StageOutputPanel } from "../components/session/StageOutputPanel";
import { ExperimentsTab } from "../components/session/ExperimentsTab";
import { CostTracker } from "../components/session/CostTracker";
import { AgentMonitor } from "../components/session/AgentMonitor";
import { HypothesisTracker } from "../components/session/HypothesisTracker";
import { PIDecisionLog } from "../components/session/PIDecisionLog";
import { CheckpointModal } from "../components/session/CheckpointModal";
import { FeedbackInput } from "../components/session/FeedbackInput";
import { CrossStageRequestsPanel } from "../components/session/CrossStageRequestsPanel";

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

  // Wire the session-scoped WebSocket; auto-invalidates TanStack cache.
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

  // Outer flex column: graph canvas on top, tabs+siders below, sticky feedback at bottom.
  return (
    <div
      style={{
        display: "flex",
        flexDirection: "column",
        minHeight: "calc(100vh - 56px - 64px)",
        width: "100%",
      }}
    >
      {/* Header — topic + session_id + status badge */}
      <div
        style={{
          marginBottom: 16,
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

      {/* Graph canvas — always visible */}
      <div style={{ marginBottom: 16 }}>
        <Card variant="borderless" styles={{ body: { padding: 8 } }}>
          <GraphTopology sessionId={sessionId} />
        </Card>
      </div>

      {/* Main 3-column layout */}
      <Card
        variant="borderless"
        styles={{ body: { padding: 0 } }}
        style={{ flex: 1, display: "flex", width: "100%" }}
      >
        <Layout style={{ background: "transparent", flex: 1, width: "100%" }}>
          <Sider
            width={200}
            theme="light"
            style={{ background: "#ffffff", borderRight: "1px solid #efefef" }}
          >
            <SectionHeader>Controls</SectionHeader>
            <ControlBar sessionId={sessionId} />
          </Sider>

          <Content
            style={{
              background: "#ffffff",
              padding: "12px 24px",
              flex: 1,
              minWidth: 0,
              overflow: "auto",
            }}
          >
            <Tabs
              activeKey={detailTab}
              onChange={(k) => setDetailTab(k as typeof detailTab)}
              type="line"
              items={[
                {
                  key: "conversations",
                  label: "Conversations",
                  children: <ChatView sessionId={sessionId} />,
                },
                {
                  key: "artifacts",
                  label: "Artifacts",
                  children: <StageOutputPanel sessionId={sessionId} />,
                },
                {
                  key: "experiments",
                  label: "Experiments",
                  children: <ExperimentsTab sessionId={sessionId} />,
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
            width={320}
            theme="light"
            style={{ background: "#ffffff", borderLeft: "1px solid #efefef" }}
          >
            <SectionHeader>Agent Monitor</SectionHeader>
            <AgentMonitor sessionId={sessionId} />
            <div style={{ borderTop: "1px solid #efefef" }} />
            <SectionHeader>Hypotheses</SectionHeader>
            <HypothesisTracker sessionId={sessionId} />
            <div style={{ borderTop: "1px solid #efefef" }} />
            <SectionHeader>Cross-stage requests</SectionHeader>
            <CrossStageRequestsPanel sessionId={sessionId} />
            <div style={{ borderTop: "1px solid #efefef" }} />
            <SectionHeader>PI decisions</SectionHeader>
            <div style={{ padding: "0 12px 12px" }}>
              <PIDecisionLog sessionId={sessionId} />
            </div>
            <div style={{ borderTop: "1px solid #efefef" }} />
            <SectionHeader>Cost</SectionHeader>
            <CostTracker sessionId={sessionId} compact />
          </Sider>
        </Layout>
      </Card>

      {/* Sticky feedback input footer */}
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

      {/* Checkpoint modal — self-manages open state from WS events. */}
      <CheckpointModal sessionId={sessionId} />
    </div>
  );
}
