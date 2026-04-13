import { useQuery } from "@tanstack/react-query";
import { api } from "../api/client";
import type { AgentMemoryRecord } from "../types/domain";

export function useAgentMemory(sessionId: string, agent: string) {
  return useQuery<AgentMemoryRecord>({
    queryKey: ["agent-memory", sessionId, agent],
    queryFn: () => api.getAgentMemory(sessionId, agent),
    enabled: !!sessionId && !!agent,
  });
}
