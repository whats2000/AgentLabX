import { useQuery } from "@tanstack/react-query";
import { api } from "../api/client";
import type { GraphTopology } from "../types/domain";

export function useGraph(sessionId: string) {
  return useQuery<GraphTopology>({
    queryKey: ["graph", sessionId],
    queryFn: () => api.getGraph(sessionId),
    enabled: !!sessionId,
  });
}
