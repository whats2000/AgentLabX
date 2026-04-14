import { describe, it, expect, vi } from "vitest";
import { render } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { StageSubgraphDrawer } from "../../src/components/session/StageSubgraphDrawer";
import type { GraphSubgraph } from "../../src/types/domain";

const stageSubgraph: GraphSubgraph = {
  id: "experimentation",
  kind: "stage_subgraph",
  label: "experimentation",
  nodes: [
    { id: "__start__", type: "internal" },
    { id: "enter", type: "internal" },
    { id: "stage_plan", type: "internal" },
    { id: "work", type: "internal" },
    { id: "evaluate", type: "internal" },
    { id: "decide", type: "internal" },
    { id: "__end__", type: "internal" },
  ],
  edges: [
    { from: "__start__", to: "enter" },
    { from: "enter", to: "stage_plan" },
    { from: "stage_plan", to: "work" },
    { from: "stage_plan", to: "decide" },
    { from: "work", to: "evaluate" },
    { from: "evaluate", to: "decide" },
    { from: "decide", to: "__end__" },
  ],
};

describe("StageSubgraphDrawer", () => {
  it("renders nothing when activeStage is null", () => {
    const { container } = render(
      <StageSubgraphDrawer
        activeStage={null}
        subgraph={null}
        cursorInternalNode={null}
        meetingActive={false}
        onWorkClick={() => {}}
      />,
    );
    expect(container.firstChild).toBeNull();
  });

  it("renders nothing when subgraph is null", () => {
    const { container } = render(
      <StageSubgraphDrawer
        activeStage="experimentation"
        subgraph={null}
        cursorInternalNode={null}
        meetingActive={false}
        onWorkClick={() => {}}
      />,
    );
    expect(container.firstChild).toBeNull();
  });

  it("renders internal nodes (excluding __start__ and __end__) when open", () => {
    const { getByText, queryByText } = render(
      <StageSubgraphDrawer
        activeStage="experimentation"
        subgraph={stageSubgraph}
        cursorInternalNode="work"
        meetingActive={false}
        onWorkClick={() => {}}
      />,
    );
    ["enter", "stage_plan", "work", "evaluate", "decide"].forEach((nodeId) => {
      expect(getByText(new RegExp(nodeId.replace(/_/g, "[ _]"), "i"))).toBeInTheDocument();
    });
    // LangGraph pseudo-nodes are filtered out
    expect(queryByText("__start__")).toBeNull();
    expect(queryByText("__end__")).toBeNull();
  });

  it("highlights the cursorInternalNode with active styling", () => {
    const { container } = render(
      <StageSubgraphDrawer
        activeStage="experimentation"
        subgraph={stageSubgraph}
        cursorInternalNode="evaluate"
        meetingActive={false}
        onWorkClick={() => {}}
      />,
    );
    const activeEl = container.querySelector("[data-internal-node='evaluate'].active");
    expect(activeEl).not.toBeNull();
  });

  it("work node is clickable when meetingActive=true; fires onWorkClick", async () => {
    const onWorkClick = vi.fn();
    const { getByText } = render(
      <StageSubgraphDrawer
        activeStage="experimentation"
        subgraph={stageSubgraph}
        cursorInternalNode="work"
        meetingActive={true}
        onWorkClick={onWorkClick}
      />,
    );
    // the work node should include a click affordance (▾) and be clickable
    const workNode = getByText(/work/i);
    await userEvent.click(workNode);
    expect(onWorkClick).toHaveBeenCalled();
  });

  it("work node is NOT clickable when meetingActive=false", async () => {
    const onWorkClick = vi.fn();
    const { getByText } = render(
      <StageSubgraphDrawer
        activeStage="experimentation"
        subgraph={stageSubgraph}
        cursorInternalNode="work"
        meetingActive={false}
        onWorkClick={onWorkClick}
      />,
    );
    const workNode = getByText(/work/i);
    await userEvent.click(workNode);
    expect(onWorkClick).not.toHaveBeenCalled();
  });

  it("renders nodes in topological order derived from edges", () => {
    // nodes should appear enter → stage_plan → work → evaluate → decide
    const { container } = render(
      <StageSubgraphDrawer
        activeStage="experimentation"
        subgraph={stageSubgraph}
        cursorInternalNode={null}
        meetingActive={false}
        onWorkClick={() => {}}
      />,
    );
    const nodeEls = Array.from(
      container.querySelectorAll("[data-internal-node]"),
    ) as HTMLElement[];
    const ids = nodeEls.map((el) => el.getAttribute("data-internal-node"));
    expect(ids).toEqual(["enter", "stage_plan", "work", "evaluate", "decide"]);
  });
});
