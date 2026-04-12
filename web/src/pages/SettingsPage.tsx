import {
  Button,
  Card,
  Form,
  Input,
  InputNumber,
  Radio,
  Select,
  Space,
  Tabs,
  Typography,
  message,
} from "antd";

const { Title, Text } = Typography;

interface SettingsFormValues {
  llm: {
    default_model: string;
    temperature: number;
    max_retries: number;
    cost_ceiling: number;
  };
  execution: {
    backend: "subprocess" | "docker";
    timeout_seconds: number;
  };
  budget: {
    warning_threshold_pct: number;
    critical_threshold_pct: number;
    hard_ceiling_action: "pause" | "stop" | "notify";
  };
}

const DEFAULT_VALUES: SettingsFormValues = {
  llm: {
    default_model: "gpt-5-mini",
    temperature: 0.7,
    max_retries: 3,
    cost_ceiling: 10,
  },
  execution: {
    backend: "subprocess",
    timeout_seconds: 120,
  },
  budget: {
    warning_threshold_pct: 70,
    critical_threshold_pct: 90,
    hard_ceiling_action: "pause",
  },
};

export default function SettingsPage() {
  const [form] = Form.useForm<SettingsFormValues>();

  const handleSave = async () => {
    try {
      await form.validateFields();
      message.info("Settings persistence ships in a later release.");
    } catch {
      // Ant validation shows inline errors; nothing else to do.
    }
  };

  return (
    <div>
      <div style={{ marginBottom: 24 }}>
        <Title level={3} style={{ margin: 0, fontWeight: 600 }}>
          Settings
        </Title>
        <Text type="secondary">
          Configure LLM defaults, execution, storage, and budget policies.
        </Text>
      </div>
      <Card variant="borderless">
        <Form
          form={form}
          layout="vertical"
          initialValues={DEFAULT_VALUES}
          size="middle"
        >
          <Tabs
            size="small"
            items={[
              {
                key: "llm",
                label: "LLM",
                children: (
                  <Space direction="vertical" size={0} style={{ width: "100%" }}>
                    <Form.Item
                      name={["llm", "default_model"]}
                      label="Default model"
                      rules={[{ required: true }]}
                    >
                      <Input placeholder="e.g. gpt-5-mini" />
                    </Form.Item>
                    <Form.Item
                      name={["llm", "temperature"]}
                      label="Temperature"
                    >
                      <InputNumber min={0} max={2} step={0.1} style={{ width: 160 }} />
                    </Form.Item>
                    <Form.Item
                      name={["llm", "max_retries"]}
                      label="Max retries"
                    >
                      <InputNumber min={0} max={10} style={{ width: 160 }} />
                    </Form.Item>
                    <Form.Item
                      name={["llm", "cost_ceiling"]}
                      label="Cost ceiling per session"
                    >
                      <InputNumber
                        min={0}
                        max={1000}
                        step={0.5}
                        addonBefore="$"
                        style={{ width: 200 }}
                      />
                    </Form.Item>
                  </Space>
                ),
              },
              {
                key: "execution",
                label: "Execution",
                children: (
                  <Space direction="vertical" size={0} style={{ width: "100%" }}>
                    <Form.Item
                      name={["execution", "backend"]}
                      label="Backend"
                    >
                      <Radio.Group
                        options={[
                          { value: "subprocess", label: "Subprocess" },
                          { value: "docker", label: "Docker" },
                        ]}
                      />
                    </Form.Item>
                    <Form.Item
                      name={["execution", "timeout_seconds"]}
                      label="Timeout (seconds)"
                    >
                      <InputNumber min={10} max={600} style={{ width: 200 }} />
                    </Form.Item>
                  </Space>
                ),
              },
              {
                key: "storage",
                label: "Storage",
                children: (
                  <div style={{ padding: "8px 0" }}>
                    <Form.Item label="Backend">
                      <Text type="secondary">SQLite (local)</Text>
                    </Form.Item>
                    <Form.Item label="Database path">
                      <Text type="secondary">data/agentlabx.db</Text>
                    </Form.Item>
                    <Text type="secondary" style={{ fontSize: 12 }}>
                      Storage settings are read-only in this build.
                    </Text>
                  </div>
                ),
              },
              {
                key: "budget",
                label: "Budget",
                children: (
                  <Space direction="vertical" size={0} style={{ width: "100%" }}>
                    <Form.Item
                      name={["budget", "warning_threshold_pct"]}
                      label="Warning threshold (%)"
                    >
                      <InputNumber min={0} max={100} style={{ width: 160 }} />
                    </Form.Item>
                    <Form.Item
                      name={["budget", "critical_threshold_pct"]}
                      label="Critical threshold (%)"
                    >
                      <InputNumber min={0} max={100} style={{ width: 160 }} />
                    </Form.Item>
                    <Form.Item
                      name={["budget", "hard_ceiling_action"]}
                      label="Hard ceiling action"
                    >
                      <Select
                        style={{ width: 200 }}
                        options={[
                          { value: "pause", label: "Pause session" },
                          { value: "stop", label: "Stop session" },
                          { value: "notify", label: "Notify only" },
                        ]}
                      />
                    </Form.Item>
                  </Space>
                ),
              },
            ]}
          />
          <div style={{ marginTop: 24, display: "flex", justifyContent: "flex-end" }}>
            <Button type="primary" onClick={handleSave}>
              Save changes
            </Button>
          </div>
        </Form>
      </Card>
    </div>
  );
}
