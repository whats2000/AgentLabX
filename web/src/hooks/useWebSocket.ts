import { useEffect, useRef } from "react";
import { useQueryClient } from "@tanstack/react-query";
import type { PipelineEvent } from "../types/events";
import { wsRegistry } from "../api/wsRegistry";
import { useWSStore } from "../stores/wsStore";

export interface UseWebSocketOptions {
  onEvent?: (event: PipelineEvent) => void;
}

/**
 * Acquires a shared SessionWebSocket from the registry. For every event:
 *   1. Appends to the wsStore ring buffer (infrastructure for future debug tooling)
 *   2. Invalidates relevant TanStack caches on state-changing events (Fix H)
 *   3. Calls the caller's onEvent handler (via ref — no dependency churn)
 *
 * Multiple components calling useWebSocket(id) share one socket through the
 * registry; the 50ms debounced teardown absorbs React 19 StrictMode's
 * mount -> cleanup -> mount cycle without network churn.
 */
export function useWebSocket(
  sessionId: string,
  options: UseWebSocketOptions = {},
): void {
  const onEventRef = useRef(options.onEvent);
  onEventRef.current = options.onEvent;

  const appendEvent = useWSStore((s) => s.appendEvent);
  const queryClient = useQueryClient();

  useEffect(() => {
    if (!sessionId) return undefined;
    const socket = wsRegistry.acquire(sessionId);
    const unsubscribe = socket.onEvent((event) => {
      appendEvent(sessionId, event);

      // Fix H: invalidate cache on events that change server-authoritative state.
      switch (event.type) {
        case "stage_completed":
        case "stage_failed":
        case "transition":
          queryClient.invalidateQueries({ queryKey: ["session", sessionId] });
          queryClient.invalidateQueries({ queryKey: ["artifacts", sessionId] });
          queryClient.invalidateQueries({ queryKey: ["transitions", sessionId] });
          queryClient.invalidateQueries({ queryKey: ["hypotheses", sessionId] });
          break;
        case "cost_update":
          queryClient.invalidateQueries({ queryKey: ["cost", sessionId] });
          break;
        default:
          break;
      }

      onEventRef.current?.(event);
    });
    return () => {
      unsubscribe();
      wsRegistry.release(sessionId);
    };
  }, [sessionId, appendEvent, queryClient]);
}
