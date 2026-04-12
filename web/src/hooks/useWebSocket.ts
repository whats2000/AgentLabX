import { useEffect, useRef } from "react";
import type { PipelineEvent } from "../types/events";
import { wsRegistry } from "../api/wsRegistry";

export interface UseWebSocketOptions {
  onEvent?: (event: PipelineEvent) => void;
}

/**
 * Acquires a shared SessionWebSocket from the registry, subscribes a
 * stable dispatcher that reads from a ref, and releases on unmount.
 * The ref pattern means callers do not need to memoize `onEvent` — the
 * effect only depends on `sessionId`, so an inline arrow handler on every
 * render will not churn acquire/release or refcount arithmetic.
 *
 * Task 8 will extend this to also invalidate TanStack Query caches on
 * state-changing events (Fix H).
 */
export function useWebSocket(
  sessionId: string,
  options: UseWebSocketOptions = {},
): void {
  const onEventRef = useRef(options.onEvent);
  onEventRef.current = options.onEvent;

  useEffect(() => {
    if (!sessionId) return undefined;
    const socket = wsRegistry.acquire(sessionId);
    const unsubscribe = socket.onEvent((event) => {
      onEventRef.current?.(event);
    });
    return () => {
      unsubscribe();
      wsRegistry.release(sessionId);
    };
  }, [sessionId]);
}
