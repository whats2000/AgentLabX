import { useQuery } from "@tanstack/react-query";
import { api } from "../api/client";
import type { AgentHistoryResponse } from "../types/domain";

export function useAgentHistory(
  sessionId: string,
  agent: string,
  params?: { limit?: number; after_ts?: string | null },
) {
  return useQuery<AgentHistoryResponse>({
    queryKey: ["agent-history", sessionId, agent, params?.limit, params?.after_ts],
    queryFn: () => api.getAgentHistory(sessionId, agent, params),
    enabled: !!sessionId && !!agent,
  });
}
