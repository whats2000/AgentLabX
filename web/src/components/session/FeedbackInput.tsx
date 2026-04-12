import { useState } from "react";
import { Button, Input, Space, message } from "antd";
import { MessageOutlined, SendOutlined } from "@ant-design/icons";
import { wsRegistry } from "../../api/wsRegistry";

interface Props {
  sessionId: string;
}

export function FeedbackInput({ sessionId }: Props) {
  const [content, setContent] = useState("");

  const send = () => {
    const trimmed = content.trim();
    if (!trimmed) return;
    const socket = wsRegistry.getSocket(sessionId);
    if (!socket) {
      message.warning("Not connected — try again in a moment.");
      return;
    }
    try {
      socket.send({ action: "inject_feedback", content: trimmed });
      setContent("");
      message.success("Message sent");
    } catch (err) {
      message.error(err instanceof Error ? err.message : "Send failed");
    }
  };

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      send();
    }
  };

  return (
    <Space.Compact style={{ width: "100%" }}>
      <span
        style={{
          display: "inline-flex",
          alignItems: "center",
          padding: "0 12px",
          color: "#9ca3af",
          background: "#fafafa",
          border: "1px solid #efefef",
          borderRight: "none",
          borderTopLeftRadius: 10,
          borderBottomLeftRadius: 10,
        }}
      >
        <MessageOutlined />
      </span>
      <Input.TextArea
        autoSize={{ minRows: 1, maxRows: 4 }}
        placeholder="Send a message to the agents..."
        value={content}
        onChange={(e) => setContent(e.target.value)}
        onKeyDown={handleKeyDown}
        style={{
          resize: "none",
          borderLeft: "none",
          borderRadius: 0,
        }}
      />
      <Button
        type="primary"
        icon={<SendOutlined />}
        onClick={send}
        disabled={!content.trim()}
        style={{ borderTopLeftRadius: 0, borderBottomLeftRadius: 0 }}
      >
        Send
      </Button>
    </Space.Compact>
  );
}
