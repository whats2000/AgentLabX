import { useQuery } from "@tanstack/react-query";
import { api } from "../api/client";

/**
 * Fix H: 30s polling is a backstop — primary refresh comes from the
 * WebSocket → TanStack invalidation wired in useWebSocket when
 * cost_update events arrive.
 */
export function useCost(sessionId: string) {
  return useQuery({
    queryKey: ["cost", sessionId],
    queryFn: () => api.getCost(sessionId),
    refetchInterval: 30_000,
    enabled: !!sessionId,
  });
}
