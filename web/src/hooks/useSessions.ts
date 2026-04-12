import { useQuery } from "@tanstack/react-query";
import { api } from "../api/client";

/**
 * Fix H: 30s poll is a backstop — the primary refresh channel is the
 * WebSocket → TanStack invalidation wiring (Task 8). Without any running
 * session there is nothing to invalidate, so the slow poll keeps the list
 * reasonably fresh when the user is idle.
 */
export function useSessions(userId?: string) {
  return useQuery({
    queryKey: ["sessions", userId],
    queryFn: () => api.listSessions(userId),
    refetchInterval: 30_000,
  });
}
