import { useEffect, useRef } from "react";
import { useQueryClient } from "@tanstack/react-query";
import type { PipelineEvent } from "../types/events";
import { wsRegistry } from "../api/wsRegistry";
import { useWSStore } from "../stores/wsStore";

export interface UseWebSocketOptions {
  onEvent?: (event: PipelineEvent) => void;
}

// Map turn_id → agent name, populated on agent_turn_started, consumed by
// subsequent llm_*/tool_* events that don't carry agent in their payload.
// Module-scope is fine: turn_id values are UUIDs so no cross-session collisions.
const turnIdToAgent = new Map<string, string>();

type EventData = Record<string, unknown>;
type InvalidatorFn = (sid: string, data: EventData) => Array<readonly unknown[]>;

const INVALIDATE: Record<string, InvalidatorFn> = {
  agent_turn_started: (sid, d) => {
    const agent = d.agent as string | undefined;
    const turnId = d.turn_id as string | undefined;
    if (agent && turnId) turnIdToAgent.set(turnId, agent);
    return agent
      ? [["agent-history", sid, agent], ["agents", sid]]
      : [["agents", sid]];
  },
  agent_turn_completed: (sid, d) => {
    const agent = d.agent as string | undefined;
    const turnId = d.turn_id as string | undefined;
    if (turnId) turnIdToAgent.delete(turnId); // cleanup to keep memory bounded
    return agent
      ? [
          ["agent-history", sid, agent],
          ["agent-memory", sid, agent],
          ["agent-context", sid, agent],
          ["agents", sid],
        ]
      : [["agents", sid]];
  },
  agent_llm_request: (sid, d) => {
    const agent =
      (d.agent as string | undefined) ??
      turnIdToAgent.get(d.turn_id as string);
    return agent ? [["agent-history", sid, agent]] : [];
  },
  agent_llm_response: (sid, d) => {
    const agent =
      (d.agent as string | undefined) ??
      turnIdToAgent.get(d.turn_id as string);
    return agent ? [["agent-history", sid, agent]] : [];
  },
  agent_tool_call: (sid, d) => {
    const agent =
      (d.agent as string | undefined) ??
      turnIdToAgent.get(d.turn_id as string);
    return agent ? [["agent-history", sid, agent]] : [];
  },
  agent_tool_result: (sid, d) => {
    const agent =
      (d.agent as string | undefined) ??
      turnIdToAgent.get(d.turn_id as string);
    return agent ? [["agent-history", sid, agent]] : [];
  },
  agent_dialogue: (sid, d) => {
    const agent =
      (d.from_agent as string | undefined) ?? (d.agent as string | undefined);
    return agent ? [["agent-history", sid, agent]] : [];
  },
  pi_decision: (sid) => [["pi-history", sid]],
  hypothesis_update: (sid) => [["hypotheses", sid]],
  // stage_* also carried the old "Fix H" invalidations; keep them plus the new graph key
  stage_started: (sid) => [["graph", sid]],
  stage_completed: (sid) => [
    ["graph", sid],
    ["experiments", sid],
    ["session", sid],
    ["artifacts", sid],
    ["transitions", sid],
    ["hypotheses", sid],
  ],
  stage_failed: (sid) => [
    ["graph", sid],
    ["session", sid],
    ["artifacts", sid],
    ["transitions", sid],
  ],
  transition: (sid) => [
    ["session", sid],
    ["artifacts", sid],
    ["transitions", sid],
    ["hypotheses", sid],
  ],
  cost_update: (sid) => [["cost", sid]],
};

/**
 * Acquires a shared SessionWebSocket from the registry. For every event:
 *   1. Appends to the wsStore ring buffer (infrastructure for future debug tooling)
 *   2. Invalidates relevant TanStack caches on state-changing events (Fix H + C10)
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

      // C10: table-driven invalidation — covers Fix H events plus all new
      // observability stream events from Plan 6B.
      const keys =
        INVALIDATE[event.type]?.(sessionId, (event.data ?? {}) as EventData) ??
        [];
      for (const k of keys) {
        queryClient.invalidateQueries({ queryKey: k });
      }

      onEventRef.current?.(event);
    });
    return () => {
      unsubscribe();
      wsRegistry.release(sessionId);
    };
  }, [sessionId, appendEvent, queryClient]);
}
