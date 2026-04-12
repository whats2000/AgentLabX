import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import SettingsPage from "../../src/pages/SettingsPage";

describe("SettingsPage", () => {
  it("renders tabs for LLM/Execution/Storage/Budget", () => {
    render(<SettingsPage />);
    expect(screen.getByRole("tab", { name: /LLM/ })).toBeInTheDocument();
    expect(screen.getByRole("tab", { name: /Execution/ })).toBeInTheDocument();
    expect(screen.getByRole("tab", { name: /Storage/ })).toBeInTheDocument();
    expect(screen.getByRole("tab", { name: /Budget/ })).toBeInTheDocument();
  });

  it("Save changes button is present and clickable", async () => {
    const user = userEvent.setup();
    render(<SettingsPage />);
    const btn = screen.getByRole("button", { name: /Save changes/ });
    expect(btn).toBeInTheDocument();
    await user.click(btn);
    // message is a portal toast — just check we didn't throw
    // (observing the toast requires antd App context, skipping)
  });

  it("LLM default_model field renders", () => {
    render(<SettingsPage />);
    expect(screen.getByLabelText(/Default model/)).toBeInTheDocument();
  });
});
