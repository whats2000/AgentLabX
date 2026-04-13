import { useQuery } from "@tanstack/react-query";
import { api } from "../api/client";
import type { RequestsResponse } from "../types/domain";

export function useCrossStageRequests(sessionId: string) {
  return useQuery<RequestsResponse>({
    queryKey: ["requests", sessionId],
    queryFn: () => api.getRequests(sessionId),
    enabled: !!sessionId,
  });
}
