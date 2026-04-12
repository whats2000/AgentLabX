import { Alert, Card, Skeleton, Tabs, Typography } from "antd";
import { usePlugins } from "../hooks/usePlugins";
import { PluginList, type PluginEntry } from "../components/plugins/PluginList";

const { Title, Text } = Typography;

const KIND_LABELS: Record<string, string> = {
  agents: "Agents",
  stages: "Stages",
  tools: "Tools",
  llm_providers: "LLM Providers",
  execution_backends: "Execution Backends",
  storage_backends: "Storage Backends",
  code_agents: "Code Agents",
};

function labelFor(kind: string): string {
  return (
    KIND_LABELS[kind] ??
    kind
      .split("_")
      .map((w) => w.charAt(0).toUpperCase() + w.slice(1))
      .join(" ")
  );
}

export default function PluginBrowserPage() {
  const { data, isLoading, error } = usePlugins();

  if (error) {
    return (
      <Alert
        type="error"
        showIcon
        message="Failed to load plugins"
        description={error instanceof Error ? error.message : String(error)}
      />
    );
  }

  if (isLoading || !data) {
    return (
      <Card variant="borderless">
        <Skeleton active paragraph={{ rows: 4 }} />
      </Card>
    );
  }

  // The response is typed unknown; cast to a Record<string, PluginEntry[]>
  const payload = data as unknown as Record<string, PluginEntry[]>;
  const entries = Object.entries(payload).filter(
    ([, v]) => Array.isArray(v),
  );

  return (
    <div>
      <div style={{ marginBottom: 24 }}>
        <Title level={3} style={{ margin: 0, fontWeight: 600 }}>
          Plugins
        </Title>
        <Text type="secondary">
          Browse registered agents, stages, tools, and providers.
        </Text>
      </div>
      <Card variant="borderless" styles={{ body: { padding: 0 } }}>
        <Tabs
          tabBarStyle={{ padding: "0 20px", margin: 0 }}
          size="small"
          items={entries.map(([kind, list]) => ({
            key: kind,
            label: `${labelFor(kind)} (${list.length})`,
            children: (
              <div style={{ padding: 20 }}>
                <PluginList plugins={list} kind={labelFor(kind).toLowerCase()} />
              </div>
            ),
          }))}
        />
      </Card>
    </div>
  );
}
