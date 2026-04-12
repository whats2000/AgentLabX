import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

const sendMock = vi.fn();
const getSocketMock = vi.fn();

vi.mock("../../src/api/wsRegistry", () => ({
  wsRegistry: {
    getSocket: (id: string) => getSocketMock(id),
  },
}));

import { FeedbackInput } from "../../src/components/session/FeedbackInput";

describe("FeedbackInput", () => {
  beforeEach(() => {
    sendMock.mockReset();
    getSocketMock.mockReset();
  });

  it("sends on Send button click", async () => {
    const user = userEvent.setup();
    getSocketMock.mockReturnValue({ send: sendMock });
    render(<FeedbackInput sessionId="sess-1" />);
    const input = screen.getByPlaceholderText(/Send a message/i);
    await user.type(input, "hello");
    await user.click(screen.getByRole("button", { name: /Send/i }));
    expect(sendMock).toHaveBeenCalledWith({
      action: "inject_feedback",
      content: "hello",
    });
  });

  it("sends on Enter, newline on Shift+Enter", async () => {
    const user = userEvent.setup();
    getSocketMock.mockReturnValue({ send: sendMock });
    render(<FeedbackInput sessionId="sess-1" />);
    const input = screen.getByPlaceholderText(
      /Send a message/i,
    ) as HTMLTextAreaElement;
    await user.type(input, "one");
    await user.keyboard("{Shift>}{Enter}{/Shift}");
    await user.type(input, "two");
    expect(input.value).toBe("one\ntwo");
    await user.keyboard("{Enter}");
    await waitFor(() => {
      expect(sendMock).toHaveBeenCalledWith({
        action: "inject_feedback",
        content: "one\ntwo",
      });
    });
  });

  it("warns and skips when socket is missing", async () => {
    const user = userEvent.setup();
    getSocketMock.mockReturnValue(null);
    render(<FeedbackInput sessionId="sess-1" />);
    const input = screen.getByPlaceholderText(/Send a message/i);
    await user.type(input, "x");
    await user.click(screen.getByRole("button", { name: /Send/i }));
    expect(sendMock).not.toHaveBeenCalled();
  });

  it("disables Send when empty", () => {
    getSocketMock.mockReturnValue({ send: sendMock });
    render(<FeedbackInput sessionId="sess-1" />);
    const btn = screen.getByRole("button", { name: /Send/i });
    expect(btn).toBeDisabled();
  });
});
