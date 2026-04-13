import { useQuery } from "@tanstack/react-query";
import { api } from "../api/client";
import type { SessionAgentInfo } from "../types/domain";

export function useAgents(sessionId: string) {
  return useQuery<SessionAgentInfo[]>({
    queryKey: ["agents", sessionId],
    queryFn: () => api.listAgents(sessionId),
    enabled: !!sessionId,
  });
}
