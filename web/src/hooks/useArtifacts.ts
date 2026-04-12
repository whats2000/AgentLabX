import { useQuery } from "@tanstack/react-query";
import { api } from "../api/client";

export function useArtifacts(sessionId: string) {
  return useQuery({
    queryKey: ["artifacts", sessionId],
    queryFn: () => api.getArtifacts(sessionId),
    enabled: !!sessionId,
  });
}
