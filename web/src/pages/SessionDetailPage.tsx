import { useEffect, useRef } from "react";
import { Layout, Drawer, Button, Col, Row, Tabs, Typography, Alert, Skeleton, Card, Badge } from "antd";
import { useParams, Link } from "react-router-dom";
import { MenuUnfoldOutlined } from "@ant-design/icons";
import { useSession } from "../hooks/useSession";
import { useGraph } from "../hooks/useGraph";
import { useWebSocket } from "../hooks/useWebSocket";
import { useUIStore } from "../stores/uiStore";
import { useStagePlans } from "../hooks/useStagePlans";
import { StatusBadge } from "../components/common/StatusBadge";
import { ControlBar } from "../components/session/ControlBar";
import { GraphTopology } from "../components/session/GraphTopology";
import { StageSubgraphDrawer } from "../components/session/StageSubgraphDrawer";
import { LabMeetingOverlay } from "../components/session/LabMeetingOverlay";
import { ChatView } from "../components/session/ChatView";
import { StageOutputPanel } from "../components/session/StageOutputPanel";
import { ExperimentsTab } from "../components/session/ExperimentsTab";
import { CostTracker } from "../components/session/CostTracker";
import { AgentMonitor } from "../components/session/AgentMonitor";
import { HypothesisTracker } from "../components/session/HypothesisTracker";
import { PIDecisionLog } from "../components/session/PIDecisionLog";
import { CheckpointModal } from "../components/session/CheckpointModal";
import { FeedbackInput } from "../components/session/FeedbackInput";
import { StagePlanCard } from "../components/session/StagePlanCard";
import type { DrawerTab } from "../stores/uiStore";

const { Text } = Typography;

/** Hook that returns the previous value of a variable. */
function usePrevious<T>(value: T): T | undefined {
  const ref = useRef<T | undefined>(undefined);
  useEffect(() => {
    ref.current = value;
  });
  return ref.current;
}

/** Wraps StagePlanCard with the latest plan for the given stage. */
function StagePlanForActive({ sessionId, stage }: { sessionId: string; stage: string }) {
  const { data } = useStagePlans(sessionId, stage);
  const latest = data?.plans[data.plans.length - 1] ?? null;
  return <StagePlanCard plan={latest} />;
}

export default function SessionDetailPage() {
  const { sessionId = "" } = useParams();
  const { data: session, isLoading, error } = useSession(sessionId);
  const { data: topology } = useGraph(sessionId);

  const {
    innerPanelOpen,
    meetingPanelOpen,
    drawerOpen,
    drawerTab,
    toggleInnerPanel,
    toggleMeetingPanel,
    toggleDrawer,
    setDrawerTab,
    resetPanelState,
  } = useUIStore();

  // Reset per-session panel state when navigating between sessions.
  // Prevents stale "inner panel open" claims from a prior session sticking
  // into a new one (Plan 7E C5).
  // Leave drawerOpen + drawerTab unchanged — they're user preferences, not
  // session-specific state.
  useEffect(() => {
    resetPanelState();
  }, [sessionId]); // eslint-disable-line react-hooks/exhaustive-deps

  // Wire the session-scoped WebSocket; auto-invalidates TanStack cache.
  useWebSocket(sessionId);

  const activeStage = topology?.cursor?.node_id ?? null;
  const stageSubgraph =
    topology?.subgraphs.find((s) => s.id === activeStage) ?? null;
  const meetingSubgraph =
    topology?.subgraphs.find((s) => s.id === "lab_meeting") ?? null;
  const internalNode = topology?.cursor?.internal_node ?? null;
  const meetingNode = topology?.cursor?.meeting_node ?? null;
  const meetingActive = meetingNode !== null;

  // Auto-close subgraph panels when active stage changes
  const prevActiveStage = usePrevious(activeStage);
  useEffect(() => {
    if (prevActiveStage && prevActiveStage !== activeStage) {
      if (innerPanelOpen) toggleInnerPanel();
      if (meetingPanelOpen) toggleMeetingPanel();
    }
  }, [activeStage]); // eslint-disable-line react-hooks/exhaustive-deps

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

  const drawerTabItems = [
    {
      key: "monitor" as DrawerTab,
      label: "Monitor",
      children: (
        <AgentMonitor sessionId={sessionId} activeStage={activeStage} />
      ),
    },
    {
      key: "plan" as DrawerTab,
      label: "Plan",
      children: activeStage ? (
        <StagePlanForActive sessionId={sessionId} stage={activeStage} />
      ) : (
        <Text type="secondary">No active stage</Text>
      ),
    },
    {
      key: "hypotheses" as DrawerTab,
      label: "Hyps",
      children: <HypothesisTracker sessionId={sessionId} />,
    },
    {
      key: "pi" as DrawerTab,
      label: "PI",
      children: <PIDecisionLog sessionId={sessionId} />,
    },
    {
      key: "cost" as DrawerTab,
      label: "Cost",
      children: <CostTracker sessionId={sessionId} />,
    },
    {
      key: "artifacts" as DrawerTab,
      label: "Artifacts",
      children: <StageOutputPanel sessionId={sessionId} />,
    },
    {
      key: "experiments" as DrawerTab,
      label: "Exp",
      children: <ExperimentsTab sessionId={sessionId} />,
    },
  ];

  return (
    <Layout style={{ minHeight: "calc(100vh - 56px - 64px)", background: "transparent" }}>
      {/* Header */}
      <div
        style={{
          padding: "12px 16px",
          background: "#fff",
          border: "1px solid #efefef",
          borderRadius: 8,
          marginBottom: 12,
          display: "flex",
          justifyContent: "space-between",
          alignItems: "center",
          gap: 16,
          flexWrap: "wrap",
        }}
      >
        <div style={{ display: "flex", alignItems: "center", gap: 12, minWidth: 0 }}>
          <div style={{ minWidth: 0 }}>
            <div style={{ fontWeight: 600, fontSize: 16, lineHeight: 1.3 }}>
              {session.research_topic}
            </div>
            <Text type="secondary" style={{ fontSize: 12 }}>
              {session.session_id}
            </Text>
          </div>
          <StatusBadge status={session.status} />
        </div>
        <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
          <ControlBar sessionId={sessionId} layout="horizontal" />
          <Button
            icon={<MenuUnfoldOutlined />}
            onClick={toggleDrawer}
            data-testid="drawer-toggle"
          >
            Details
          </Button>
        </div>
      </div>

      {/* GraphTopology — always visible */}
      <div
        style={{
          background: "#fff",
          border: "1px solid #efefef",
          borderRadius: 8,
          padding: 8,
          marginBottom: 12,
        }}
      >
        <GraphTopology
          sessionId={sessionId}
          topology={topology}
          onStageClick={(stageId) => {
            if (stageId === activeStage) toggleInnerPanel();
          }}
        />
      </div>

      {/* Conditional subgraph row */}
      {innerPanelOpen && (
        <div style={{ marginBottom: 12 }}>
          <Row gutter={16}>
            <Col span={meetingPanelOpen && meetingActive ? 12 : 24}>
              <StageSubgraphDrawer
                activeStage={activeStage}
                subgraph={stageSubgraph}
                cursorInternalNode={internalNode}
                meetingActive={meetingActive}
                onWorkClick={toggleMeetingPanel}
              />
            </Col>
            {meetingPanelOpen && meetingActive && (
              <Col span={12}>
                <LabMeetingOverlay
                  subgraph={meetingSubgraph}
                  cursorMeetingNode={meetingNode}
                />
              </Col>
            )}
          </Row>
        </div>
      )}

      {/* Main content: ChatView flex + sticky FeedbackInput */}
      <div
        style={{
          flex: 1,
          background: "#fff",
          border: "1px solid #efefef",
          borderRadius: 8,
          padding: 16,
          marginBottom: 0,
        }}
      >
        <ChatView sessionId={sessionId} activeStage={activeStage} />
      </div>

      {/* Sticky feedback input footer */}
      <div
        style={{
          position: "sticky",
          bottom: 0,
          marginTop: 12,
          background: "#ffffff",
          border: "1px solid #efefef",
          borderRadius: 8,
          padding: 10,
        }}
      >
        <FeedbackInput sessionId={sessionId} />
      </div>

      {/* Right details drawer */}
      <Drawer
        open={drawerOpen}
        onClose={toggleDrawer}
        width={320}
        title="Details"
        placement="right"
        data-testid="details-drawer"
      >
        <Tabs
          activeKey={drawerTab}
          onChange={(key) => setDrawerTab(key as DrawerTab)}
          size="small"
          items={drawerTabItems}
        />
      </Drawer>

      {/* Checkpoint modal — self-manages open state from WS events */}
      <CheckpointModal sessionId={sessionId} />
    </Layout>
  );
}
