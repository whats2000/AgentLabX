import { useQuery } from "@tanstack/react-query";
import { api } from "../api/client";
import type { AgentContextResponse } from "../types/domain";

export function useAgentContext(sessionId: string, agent: string) {
  return useQuery<AgentContextResponse>({
    queryKey: ["agent-context", sessionId, agent],
    queryFn: () => api.getAgentContext(sessionId, agent),
    enabled: !!sessionId && !!agent,
  });
}
