import { renderHook, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { describe, it, expect, vi } from "vitest";
import { useAgentHistory } from "../../src/hooks/useAgentHistory";

vi.mock("../../src/api/client", () => ({
  api: {
    getAgentHistory: vi.fn().mockResolvedValue({
      turns: [
        {
          turn_id: "t1",
          agent: "phd_student",
          stage: "lit",
          kind: "llm_request",
          payload: {},
          is_mock: true,
          tokens_in: null,
          tokens_out: null,
          cost_usd: null,
          system_prompt_hash: null,
          parent_turn_id: null,
          ts: "2026-04-13T00:00:00",
        },
      ],
      next_cursor: null,
    }),
  },
}));

describe("useAgentHistory", () => {
  it("returns turns array from the API", async () => {
    const qc = new QueryClient({
      defaultOptions: { queries: { retry: false } },
    });
    const wrapper = ({ children }: { children: React.ReactNode }) => (
      <QueryClientProvider client={qc}>{children}</QueryClientProvider>
    );
    const { result } = renderHook(() => useAgentHistory("s1", "phd_student"), { wrapper });
    await waitFor(() => expect(result.current.data).toBeDefined());
    expect(result.current.data?.turns[0].turn_id).toBe("t1");
  });
});
