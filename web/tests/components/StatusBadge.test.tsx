import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import { StatusBadge } from "../../src/components/common/StatusBadge";

describe("StatusBadge", () => {
  it.each([
    ["created", "Created"],
    ["running", "Running"],
    ["paused", "Paused"],
    ["completed", "Completed"],
    ["failed", "Failed"],
  ] as const)("renders %s status as %s label", (status, label) => {
    render(<StatusBadge status={status} />);
    expect(screen.getByText(label)).toBeInTheDocument();
  });

  it("falls back to raw string for unknown status", () => {
    render(<StatusBadge status="mystery" />);
    expect(screen.getByText("mystery")).toBeInTheDocument();
  });
});
