import { useQuery } from "@tanstack/react-query";
import { api } from "../api/client";

/**
 * Fix H: 30s polling is a backstop — primary refresh comes from the
 * WebSocket → TanStack invalidation wired in useWebSocket.
 */
export function useSession(sessionId: string) {
  return useQuery({
    queryKey: ["session", sessionId],
    queryFn: () => api.getSession(sessionId),
    refetchInterval: 30_000,
    enabled: !!sessionId,
  });
}
