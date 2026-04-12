import {
  Button,
  Card,
  Empty,
  Input,
  Popconfirm,
  Space,
  Table,
  Typography,
  message,
} from "antd";
import {
  DeleteOutlined,
  EyeOutlined,
  PlusOutlined,
  SearchOutlined,
} from "@ant-design/icons";
import type { ColumnsType } from "antd/es/table";
import { useNavigate } from "react-router-dom";
import { useSessions } from "../hooks/useSessions";
import { useDeleteSession } from "../hooks/useDeleteSession";
import { useUIStore } from "../stores/uiStore";
import { StatusBadge } from "../components/common/StatusBadge";
import type { SessionSummary } from "../types/domain";

const { Title, Text } = Typography;

export default function SessionListPage() {
  const navigate = useNavigate();
  const filter = useUIStore((s) => s.sessionListFilter);
  const setFilter = useUIStore((s) => s.setSessionListFilter);
  const { data: sessions, isLoading, error } = useSessions();
  const deleteMutation = useDeleteSession();

  const filtered = (sessions ?? []).filter((s) => {
    if (!filter) return true;
    const q = filter.toLowerCase();
    return (
      s.research_topic.toLowerCase().includes(q) ||
      s.session_id.toLowerCase().includes(q) ||
      s.user_id.toLowerCase().includes(q)
    );
  });

  const columns: ColumnsType<SessionSummary> = [
    {
      title: "Topic",
      dataIndex: "research_topic",
      key: "research_topic",
      render: (text: string, record) => (
        <div>
          <Button
            type="link"
            onClick={() => navigate(`/sessions/${record.session_id}`)}
            style={{
              padding: 0,
              height: "auto",
              fontWeight: 500,
              color: "#262626",
            }}
          >
            {text}
          </Button>
          <div>
            <Text type="secondary" style={{ fontSize: 12 }}>
              {record.session_id}
            </Text>
          </div>
        </div>
      ),
    },
    {
      title: "Status",
      dataIndex: "status",
      key: "status",
      width: 140,
      render: (status: string) => <StatusBadge status={status} />,
    },
    {
      title: "User",
      dataIndex: "user_id",
      key: "user_id",
      width: 140,
      render: (user: string) => (
        <Text type="secondary" style={{ fontSize: 13 }}>
          {user}
        </Text>
      ),
    },
    {
      title: "",
      key: "actions",
      width: 180,
      align: "right",
      render: (_, record) => (
        <Space size={4}>
          <Button
            type="text"
            size="small"
            icon={<EyeOutlined />}
            onClick={() => navigate(`/sessions/${record.session_id}`)}
          >
            View
          </Button>
          <Popconfirm
            title="Delete this session?"
            description="Cancels any running pipeline and removes all stored state."
            onConfirm={async () => {
              try {
                await deleteMutation.mutateAsync(record.session_id);
                message.success("Session deleted");
              } catch (err) {
                message.error(
                  err instanceof Error ? err.message : "Delete failed",
                );
              }
            }}
            okText="Delete"
            cancelText="Cancel"
            okButtonProps={{ danger: true }}
          >
            <Button
              type="text"
              size="small"
              danger
              icon={<DeleteOutlined />}
              loading={deleteMutation.isPending}
            >
              Delete
            </Button>
          </Popconfirm>
        </Space>
      ),
    },
  ];

  const empty = (
    <Empty
      image={Empty.PRESENTED_IMAGE_SIMPLE}
      description={
        <Text type="secondary">
          No sessions yet. Create one to start a research run.
        </Text>
      }
    >
      <Button
        type="primary"
        icon={<PlusOutlined />}
        onClick={() => navigate("/sessions/new")}
      >
        Start new session
      </Button>
    </Empty>
  );

  return (
    <div>
      <div style={{ marginBottom: 24 }}>
        <Title level={3} style={{ margin: 0, fontWeight: 600 }}>
          Sessions
        </Title>
        <Text type="secondary">
          Create, monitor, and manage research sessions.
        </Text>
      </div>

      <Card
        variant="borderless"
        styles={{ body: { padding: 0 } }}
        style={{ overflow: "hidden" }}
      >
        <div
          style={{
            display: "flex",
            justifyContent: "space-between",
            alignItems: "center",
            padding: "16px 20px",
            borderBottom: "1px solid #efefef",
            gap: 12,
          }}
        >
          <Input
            placeholder="Search by topic, user, or id"
            allowClear
            prefix={<SearchOutlined style={{ color: "#9ca3af" }} />}
            value={filter}
            onChange={(e) => setFilter(e.target.value)}
            style={{ maxWidth: 360 }}
          />
          <Button
            type="primary"
            icon={<PlusOutlined />}
            onClick={() => navigate("/sessions/new")}
          >
            New Session
          </Button>
        </div>

        {error ? (
          <div style={{ padding: 40, textAlign: "center" }}>
            <Text type="danger">
              Failed to load sessions:{" "}
              {error instanceof Error ? error.message : String(error)}
            </Text>
          </div>
        ) : (
          <Table
            rowKey="session_id"
            columns={columns}
            dataSource={filtered}
            loading={isLoading}
            pagination={{ pageSize: 20, hideOnSinglePage: true }}
            locale={{ emptyText: empty }}
          />
        )}
      </Card>
    </div>
  );
}
