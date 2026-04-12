import { Empty, Table, Typography } from "antd";

const { Text } = Typography;

export interface PluginEntry {
  name: string;
  description?: string;
  [k: string]: unknown;
}

interface Props {
  plugins: PluginEntry[];
  kind: string;
}

export function PluginList({ plugins, kind }: Props) {
  if (plugins.length === 0) {
    return (
      <Empty
        image={Empty.PRESENTED_IMAGE_SIMPLE}
        description={
          <Text type="secondary">No {kind} registered.</Text>
        }
      />
    );
  }
  return (
    <Table
      rowKey="name"
      pagination={false}
      size="middle"
      dataSource={plugins}
      columns={[
        {
          title: "Name",
          dataIndex: "name",
          key: "name",
          render: (v: string) => <Text strong>{v}</Text>,
        },
        {
          title: "Description",
          dataIndex: "description",
          key: "description",
          render: (v: string | undefined) =>
            v ? (
              <Text type="secondary">{v}</Text>
            ) : (
              <Text type="secondary" style={{ fontStyle: "italic" }}>
                —
              </Text>
            ),
        },
      ]}
    />
  );
}
