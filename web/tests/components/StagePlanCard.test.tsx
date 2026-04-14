import { describe, it, expect } from "vitest";
import { render } from "@testing-library/react";
import { StagePlanCard } from "../../src/components/session/StagePlanCard";
import type { StagePlan } from "../../src/types/domain";

const samplePlan: StagePlan = {
  items: [
    {
      id: "i1",
      description: "Survey topic",
      status: "done",
      source: "prior",
      existing_artifact_ref: "lit_review[0]",
      edit_note: null,
      removed_reason: null,
    },
    {
      id: "i2",
      description: "Gather recent papers",
      status: "todo",
      source: "contract",
      existing_artifact_ref: null,
      edit_note: null,
      removed_reason: null,
    },
    {
      id: "i3",
      description: "Address feedback",
      status: "edit",
      source: "feedback",
      existing_artifact_ref: "lit_review[0]",
      edit_note: "add RL methods",
      removed_reason: null,
    },
    {
      id: "i4",
      description: "Old plan item",
      status: "removed",
      source: "prior",
      existing_artifact_ref: null,
      edit_note: null,
      removed_reason: "plan pivoted",
    },
  ],
  rationale: "Literature review plan for cot math",
  hash_of_consumed_inputs: "abc123",
};

describe("StagePlanCard", () => {
  it("renders each item with its status chip", () => {
    const { getByText } = render(<StagePlanCard plan={samplePlan} />);
    expect(getByText("Survey topic")).toBeInTheDocument();
    expect(getByText("Gather recent papers")).toBeInTheDocument();
    expect(getByText("Address feedback")).toBeInTheDocument();
    expect(getByText("Old plan item")).toBeInTheDocument();
    expect(getByText("done")).toBeInTheDocument();
    expect(getByText("todo")).toBeInTheDocument();
    expect(getByText("edit")).toBeInTheDocument();
    expect(getByText("removed")).toBeInTheDocument();
  });

  it("shows the rationale", () => {
    const { getByText } = render(<StagePlanCard plan={samplePlan} />);
    expect(getByText(/Literature review plan for cot math/)).toBeInTheDocument();
  });

  it("shows the edit_note when present", () => {
    const { getByText } = render(<StagePlanCard plan={samplePlan} />);
    expect(getByText(/add RL methods/)).toBeInTheDocument();
  });

  it("shows the removed_reason when present", () => {
    const { getByText } = render(<StagePlanCard plan={samplePlan} />);
    expect(getByText(/plan pivoted/)).toBeInTheDocument();
  });

  it("renders empty state when no items", () => {
    const emptyPlan: StagePlan = {
      items: [],
      rationale: "Nothing to do",
      hash_of_consumed_inputs: "",
    };
    const { getByText } = render(<StagePlanCard plan={emptyPlan} />);
    expect(getByText(/Nothing to do/)).toBeInTheDocument();
    // No item rows — just the rationale + an empty list
  });

  it("renders null-safe when plan is null", () => {
    const { container } = render(<StagePlanCard plan={null} />);
    // Either nothing or a placeholder — either is acceptable; assert no crash
    expect(container).toBeTruthy();
  });
});
