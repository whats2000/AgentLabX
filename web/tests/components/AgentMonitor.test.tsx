import { render, screen } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { vi, describe, it, expect } from "vitest";
import { AgentMonitor } from "../../src/components/session/AgentMonitor";

vi.mock("../../src/api/client", () => ({
  api: {
    listAgents: vi.fn().mockResolvedValue([
      {name: "postdoc", role: "postdoc", turn_count: 4, last_active_stage: "plan_formulation"},
      {name: "phd_student", role: "phd", turn_count: 2, last_active_stage: "literature_review"},
    ]),
    getAgentContext: vi.fn().mockResolvedValue({
      keys: ["plan", "hypotheses"],
      preview: {plan: [{goals: []}]},
      scope: {read: ["plan"], summarize: {}, write: ["plan"]},
    }),
    getAgentMemory: vi.fn().mockResolvedValue({
      working_memory: {},
      notes: [],
      last_active_stage: "",
      turn_count: 0,
    }),
    getAgentHistory: vi.fn().mockResolvedValue({turns: [], next_cursor: null}),
  },
}));

describe("AgentMonitor", () => {
  it("renders a tab per agent", async () => {
    const qc = new QueryClient({defaultOptions: {queries: {retry: false}}});
    render(
      <QueryClientProvider client={qc}>
        <AgentMonitor sessionId="s1" />
      </QueryClientProvider>
    );
    expect(await screen.findByText("postdoc")).toBeInTheDocument();
    expect(screen.getByText("phd_student")).toBeInTheDocument();
  });
});
