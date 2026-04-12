import { Form, Input, Modal, Select, message } from "antd";
import { STAGE_LABELS, STAGE_SEQUENCE } from "../../lib/pipelineStages";
import { useRedirectSession } from "../../hooks/useSessionMutations";

interface Props {
  sessionId: string;
  open: boolean;
  onClose: () => void;
  defaultReason?: string;
}

interface FormValues {
  target_stage: string;
  reason?: string;
}

export function RedirectModal({
  sessionId,
  open,
  onClose,
  defaultReason,
}: Props) {
  const [form] = Form.useForm<FormValues>();
  const redirect = useRedirectSession(sessionId);

  const handleOk = async () => {
    try {
      const values = await form.validateFields();
      await redirect.mutateAsync({
        target_stage: values.target_stage,
        reason: values.reason ?? "",
      });
      message.success("Redirect sent");
      form.resetFields();
      onClose();
    } catch (err) {
      // AntD Form.validateFields rejects with {errorFields: ...} when the
      // form is invalid — that path is handled by the Form UI itself and
      // we don't want to surface it as a toast. Only surface genuine
      // Errors (e.g. API failures) here.
      if (err instanceof Error) {
        message.error(err.message);
      }
    }
  };

  return (
    <Modal
      open={open}
      title="Redirect pipeline"
      onCancel={onClose}
      onOk={handleOk}
      okText="Send redirect"
      confirmLoading={redirect.isPending}
      okButtonProps={{ type: "primary" }}
      destroyOnHidden
    >
      <Form
        form={form}
        layout="vertical"
        initialValues={{ reason: defaultReason ?? "" }}
      >
        <Form.Item
          name="target_stage"
          label="Target stage"
          rules={[{ required: true, message: "Pick a stage" }]}
        >
          <Select
            placeholder="Pick a stage to jump to"
            options={STAGE_SEQUENCE.map((s) => ({
              value: s,
              label: STAGE_LABELS[s],
            }))}
          />
        </Form.Item>
        <Form.Item name="reason" label="Reason (optional)">
          <Input.TextArea
            rows={3}
            placeholder="Why are you redirecting? This is logged."
          />
        </Form.Item>
      </Form>
    </Modal>
  );
}
