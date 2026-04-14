import { describe, it, expect } from "vitest";
import { topoSort } from "../../src/utils/topoSort";

describe("topoSort", () => {
  it("sorts a linear chain in execution order", () => {
    const nodes = [{ id: "a" }, { id: "b" }, { id: "c" }];
    const edges = [
      { from: "a", to: "b" },
      { from: "b", to: "c" },
    ];
    expect(topoSort(nodes, edges)).toEqual(["a", "b", "c"]);
  });

  it("handles branching correctly (Kahn's algorithm)", () => {
    // Mirrors the stage subgraph: stage_plan branches to work OR decide;
    // decide has in-degree 2 (from stage_plan AND from evaluate)
    const nodes = [
      { id: "enter" },
      { id: "stage_plan" },
      { id: "work" },
      { id: "evaluate" },
      { id: "decide" },
    ];
    const edges = [
      { from: "enter", to: "stage_plan" },
      { from: "stage_plan", to: "work" },
      { from: "stage_plan", to: "decide" },
      { from: "work", to: "evaluate" },
      { from: "evaluate", to: "decide" },
    ];
    const result = topoSort(nodes, edges);
    // decide must be last (in-degree 2, both dependencies must complete first)
    expect(result[result.length - 1]).toBe("decide");
    // enter must be first
    expect(result[0]).toBe("enter");
    // work must come before evaluate
    expect(result.indexOf("work")).toBeLessThan(result.indexOf("evaluate"));
  });

  it("falls back to insertion order on cycles", () => {
    const nodes = [{ id: "a" }, { id: "b" }];
    const edges = [
      { from: "a", to: "b" },
      { from: "b", to: "a" },
    ];
    // No node has in-degree 0; queue stays empty initially.
    // Fallback appends remaining nodes in original order.
    const result = topoSort(nodes, edges);
    expect(result).toEqual(["a", "b"]);
  });

  it("ignores edges referencing unknown nodes", () => {
    const nodes = [{ id: "a" }, { id: "b" }];
    const edges = [
      { from: "a", to: "b" },
      { from: "b", to: "phantom" },
    ];
    const result = topoSort(nodes, edges);
    expect(result).toEqual(["a", "b"]);
  });
});
