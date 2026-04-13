import { useQuery } from "@tanstack/react-query";
import { api } from "../api/client";
import type { ExperimentsResponse } from "../types/domain";

export function useExperiments(sessionId: string) {
  return useQuery<ExperimentsResponse>({
    queryKey: ["experiments", sessionId],
    queryFn: () => api.getExperiments(sessionId),
    enabled: !!sessionId,
  });
}
