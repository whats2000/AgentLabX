import { describe, it, expect } from "vitest";
import { render } from "@testing-library/react";
import { LabMeetingOverlay } from "../../src/components/session/LabMeetingOverlay";
import type { GraphSubgraph } from "../../src/types/domain";

const meetingSubgraph: GraphSubgraph = {
  id: "lab_meeting",
  kind: "invocable_only",
  label: "lab_meeting",
  nodes: [
    { id: "__start__", type: "internal" },
    { id: "enter", type: "internal" },
    { id: "discuss", type: "internal" },
    { id: "synthesize", type: "internal" },
    { id: "exit", type: "internal" },
    { id: "__end__", type: "internal" },
  ],
  edges: [
    { from: "__start__", to: "enter" },
    { from: "enter", to: "discuss" },
    { from: "discuss", to: "synthesize" },
    { from: "synthesize", to: "exit" },
    { from: "exit", to: "__end__" },
  ],
};

describe("LabMeetingOverlay", () => {
  it("renders nothing when subgraph is null", () => {
    const { container } = render(
      <LabMeetingOverlay subgraph={null} cursorMeetingNode={null} />,
    );
    expect(container.firstChild).toBeNull();
  });

  it("renders meeting nodes (excluding __start__/__end__) when subgraph given", () => {
    const { getByText, queryByText } = render(
      <LabMeetingOverlay
        subgraph={meetingSubgraph}
        cursorMeetingNode="discuss"
      />,
    );
    ["enter", "discuss", "synthesize", "exit"].forEach((id) => {
      expect(getByText(new RegExp(id, "i"))).toBeInTheDocument();
    });
    expect(queryByText("__start__")).toBeNull();
    expect(queryByText("__end__")).toBeNull();
  });

  it("highlights the cursorMeetingNode", () => {
    const { container } = render(
      <LabMeetingOverlay
        subgraph={meetingSubgraph}
        cursorMeetingNode="synthesize"
      />,
    );
    const active = container.querySelector(
      "[data-meeting-node='synthesize'].active",
    );
    expect(active).not.toBeNull();
  });

  it("renders nodes in topological order", () => {
    const { container } = render(
      <LabMeetingOverlay
        subgraph={meetingSubgraph}
        cursorMeetingNode={null}
      />,
    );
    const nodes = Array.from(
      container.querySelectorAll("[data-meeting-node]"),
    ) as HTMLElement[];
    const ids = nodes.map((el) => el.getAttribute("data-meeting-node"));
    expect(ids).toEqual(["enter", "discuss", "synthesize", "exit"]);
  });
});
