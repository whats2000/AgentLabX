import { describe, it, expect, beforeEach, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import { AgentActivityFeed } from "../../src/components/session/AgentActivityFeed";
import { useWSStore } from "../../src/stores/wsStore";
import type { PipelineEvent } from "../../src/types/events";

function seedEvents(sessionId: string, events: PipelineEvent[]) {
  useWSStore.setState({ events: { [sessionId]: events } });
}

describe("AgentActivityFeed", () => {
  beforeEach(() => {
    useWSStore.setState({ events: {} });
  });

  it("renders the empty state when no events", () => {
    render(<AgentActivityFeed sessionId="sess-1" />);
    expect(screen.getByText(/Activity will stream here/i)).toBeInTheDocument();
  });

  it("renders stage_started, stage_completed, stage_failed titles", () => {
    seedEvents("sess-1", [
      {
        type: "stage_started",
        data: { stage: "literature_review" },
        timestamp: new Date().toISOString(),
      },
      {
        type: "stage_completed",
        data: { stage: "literature_review", reason: "3 papers" },
        timestamp: new Date().toISOString(),
      },
      {
        type: "stage_failed",
        data: { stage: "experimentation", message: "boom" },
        timestamp: new Date().toISOString(),
      },
    ]);
    render(<AgentActivityFeed sessionId="sess-1" />);
    expect(
      screen.getByText(/Stage literature_review started/i),
    ).toBeInTheDocument();
    expect(
      screen.getByText(/Stage literature_review completed/i),
    ).toBeInTheDocument();
    expect(
      screen.getByText(/Stage experimentation failed/i),
    ).toBeInTheDocument();
    // subtitle
    expect(screen.getByText(/3 papers/)).toBeInTheDocument();
    expect(screen.getByText(/boom/)).toBeInTheDocument();
  });

  it("orders newest-first by list position (reverses store)", () => {
    const now = new Date();
    seedEvents("sess-1", [
      {
        type: "stage_started",
        data: { stage: "first" },
        timestamp: now.toISOString(),
      },
      {
        type: "stage_started",
        data: { stage: "second" },
        timestamp: new Date(now.getTime() + 1000).toISOString(),
      },
    ]);
    render(<AgentActivityFeed sessionId="sess-1" />);
    const titles = screen.getAllByText(/Stage .* started/i);
    expect(titles[0]).toHaveTextContent("second");
    expect(titles[1]).toHaveTextContent("first");
  });

  it("renders 'just now' for recent timestamps", () => {
    vi.spyOn(Date, "now").mockReturnValue(1_700_000_000_000);
    seedEvents("sess-1", [
      {
        type: "stage_started",
        data: { stage: "x" },
        timestamp: new Date(1_700_000_000_000 - 1000).toISOString(),
      },
    ]);
    render(<AgentActivityFeed sessionId="sess-1" />);
    // 1s delta → "just now"
    expect(screen.getByText(/just now/i)).toBeInTheDocument();
  });

  it("handles missing timestamps without crashing", () => {
    seedEvents("sess-1", [
      {
        type: "stage_started",
        data: { stage: "x" },
      } as PipelineEvent,
    ]);
    render(<AgentActivityFeed sessionId="sess-1" />);
    expect(screen.getByText(/Stage x started/)).toBeInTheDocument();
  });
});
