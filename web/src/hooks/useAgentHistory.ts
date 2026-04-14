import { useQuery } from "@tanstack/react-query";
import { api } from "../api/client";
import type { AgentHistoryResponse } from "../types/domain";

/**
 * Overload 1 – legacy per-agent fetch (used by ChatView stage groups, etc.)
 */
export function useAgentHistory(
  sessionId: string,
  agent: string,
  params?: { limit?: number; after_ts?: string | null },
): ReturnType<typeof useQuery<AgentHistoryResponse>>;

/**
 * Overload 2 – stage-based fetch (used by StageGroup for lazy-load per Collapse panel).
 * Calls `/api/sessions/{sessionId}/stages/{stage}/history` — a logical endpoint
 * that returns all turns for a stage across agents. Gated by `enabled`.
 */
export function useAgentHistory(
  sessionId: string,
  opts: { stage: string; enabled?: boolean },
): ReturnType<typeof useQuery<AgentHistoryResponse>>;

export function useAgentHistory(
  sessionId: string,
  agentOrOpts: string | { stage: string; enabled?: boolean },
  params?: { limit?: number; after_ts?: string | null },
) {
  // Overload 2: stage-based
  if (typeof agentOrOpts === "object") {
    const { stage, enabled = true } = agentOrOpts;
    return useQuery<AgentHistoryResponse>({
      queryKey: ["agent-history", sessionId, { stage }],
      queryFn: async () => {
        const url = `/api/sessions/${sessionId}/stages/${stage}/history`;
        const res = await fetch(url);
        if (!res.ok) {
          throw new Error(`Failed to fetch stage history: ${res.status}`);
        }
        return res.json() as Promise<AgentHistoryResponse>;
      },
      enabled: enabled && Boolean(sessionId),
    });
  }

  // Overload 1: legacy per-agent
  const agent = agentOrOpts;
  return useQuery<AgentHistoryResponse>({
    queryKey: ["agent-history", sessionId, agent, params?.limit, params?.after_ts],
    queryFn: () => api.getAgentHistory(sessionId, agent, params),
    enabled: !!sessionId && !!agent,
  });
}
