import { useQuery } from "@tanstack/react-query";
import { api } from "../api/client";
import type { PIDecisionRecord } from "../types/domain";

export function usePIHistory(sessionId: string) {
  return useQuery<PIDecisionRecord[]>({
    queryKey: ["pi-history", sessionId],
    queryFn: () => api.getPIHistory(sessionId),
    enabled: !!sessionId,
  });
}
