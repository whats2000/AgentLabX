import { Alert, Card, Skeleton, Tabs, Typography } from "antd";
import { usePlugins } from "../hooks/usePlugins";
import { PluginList, type PluginEntry } from "../components/plugins/PluginList";

const { Title, Text } = Typography;

// Keys match the backend's singular PluginType.value form
// (agentlabx/core/registry.py::PluginType). Each entry is an explicit label
// so acronyms like "LLM" survive — the title-case fallback would otherwise
// produce "Llm Provider".
const KIND_LABELS: Record<string, string> = {
  agent: "Agents",
  stage: "Stages",
  tool: "Tools",
  llm_provider: "LLM Providers",
  execution_backend: "Execution Backends",
  storage_backend: "Storage Backends",
  code_agent: "Code Agents",
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

// Preferred display order for the tabs. Unknown keys (e.g. future plugin
// types added to the backend before the frontend knows about them) sort to
// the end in their natural order.
const KIND_ORDER = [
  "agent",
  "stage",
  "tool",
  "llm_provider",
  "execution_backend",
  "storage_backend",
  "code_agent",
];

function kindOrder(kind: string): number {
  const idx = KIND_ORDER.indexOf(kind);
  return idx === -1 ? KIND_ORDER.length : idx;
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
  const entries = Object.entries(payload)
    .filter(([, v]) => Array.isArray(v))
    .sort(([a], [b]) => kindOrder(a) - kindOrder(b));

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
