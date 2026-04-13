import { render, screen } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { vi, describe, it, expect } from "vitest";
import { ChatView } from "../../src/components/session/ChatView";

vi.mock("../../src/api/client", () => ({
  api: {
    listAgents: vi.fn().mockResolvedValue([
      {name: "postdoc", role: "postdoc", turn_count: 2, last_active_stage: "plan_formulation"},
    ]),
    getAgentHistory: vi.fn().mockImplementation((_sid: string, agent: string) =>
      Promise.resolve({
        turns: agent === "postdoc" ? [
          {turn_id: "T1", agent: "postdoc", stage: "plan_formulation",
           kind: "llm_request", payload: {prompt: "go", system_prompt: "sp"},
           is_mock: true, tokens_in: null, tokens_out: null, cost_usd: null,
           system_prompt_hash: null, parent_turn_id: null, ts: "2026-04-13T00:00:00"},
          {turn_id: "T1", agent: "postdoc", stage: "plan_formulation",
           kind: "llm_response", payload: {content: "Proposed plan"},
           is_mock: true, tokens_in: 5, tokens_out: 8, cost_usd: 0.01,
           system_prompt_hash: null, parent_turn_id: null, ts: "2026-04-13T00:00:01"},
        ] : [],
        next_cursor: null,
      })),
  },
}));

describe("ChatView", () => {
  it("groups by stage and shows asst response inline under request", async () => {
    const qc = new QueryClient({defaultOptions: {queries: {retry: false}}});
    render(
      <QueryClientProvider client={qc}>
        <ChatView sessionId="s1" />
      </QueryClientProvider>
    );
    expect(await screen.findByText("Plan Formulation")).toBeInTheDocument();
    expect(screen.getByText(/Proposed plan/)).toBeInTheDocument();
    // The [mock] tag should appear somewhere visible
    expect(screen.getByText(/mock/i)).toBeInTheDocument();
  });

  it("shows empty state when no agents have any turns", async () => {
    const api = await import("../../src/api/client");
    (api.api.listAgents as any).mockResolvedValueOnce([]);
    const qc = new QueryClient({defaultOptions: {queries: {retry: false}}});
    render(
      <QueryClientProvider client={qc}>
        <ChatView sessionId="s1" />
      </QueryClientProvider>
    );
    expect(await screen.findByText(/no agent turns yet/i)).toBeInTheDocument();
  });
});
