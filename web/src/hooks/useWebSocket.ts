import { useEffect } from "react";
import type { PipelineEvent } from "../types/events";
import { wsRegistry } from "../api/wsRegistry";

export interface UseWebSocketOptions {
  onEvent?: (event: PipelineEvent) => void;
}

/**
 * Acquires a shared SessionWebSocket from the registry, subscribes the
 * given handler, and releases on unmount. Task 8 will extend this to also
 * invalidate TanStack Query caches on state-changing events (Fix H).
 *
 * Note: this hook currently returns `undefined` intentionally — Tasks 11/12
 * may change this to expose `socket.send` if needed. Do not import Zustand
 * or TanStack Query here yet; that wiring belongs in Task 4/8 once the
 * queryClient provider is mounted.
 */
export function useWebSocket(
  sessionId: string,
  options: UseWebSocketOptions = {},
): void {
  const { onEvent } = options;

  useEffect(() => {
    if (!sessionId) return undefined;
    const socket = wsRegistry.acquire(sessionId);
    const unsubscribe = onEvent ? socket.onEvent(onEvent) : () => undefined;
    return () => {
      unsubscribe();
      wsRegistry.release(sessionId);
    };
  }, [sessionId, onEvent]);
}
