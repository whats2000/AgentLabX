import { useQuery } from "@tanstack/react-query";
import { api } from "../api/client";

export function useHypotheses(sessionId: string) {
  return useQuery({
    queryKey: ["hypotheses", sessionId],
    queryFn: () => api.getHypotheses(sessionId),
    enabled: !!sessionId,
  });
}
