import { useEffect, useRef } from "react";
import { useQueryClient } from "@tanstack/react-query";
import type { PipelineEvent } from "../types/events";
import { wsRegistry } from "../api/wsRegistry";
import { useWSStore } from "../stores/wsStore";

export interface UseWebSocketOptions {
  onEvent?: (event: PipelineEvent) => void;
}

// session_id → (turn_id → agent name).  Keyed by session so per-session maps
// can be wiped independently without touching other sessions' state.
const turnIdToAgent = new Map<string, Map<string, string>>();

function getSessionTurnMap(sid: string): Map<string, string> {
  let m = turnIdToAgent.get(sid);
  if (!m) {
    m = new Map();
    turnIdToAgent.set(sid, m);
  }
  return m;
}

/** INTERNAL: clear the turn→agent map for a session. Also exported for tests. */
export function _clearTurnMapForSession(sid: string): void {
  turnIdToAgent.delete(sid);
}

/** Test-only: wipe all per-session turn maps. Called from vitest setup. */
export function _clearAllTurnMaps(): void {
  turnIdToAgent.clear();
}

type EventData = Record<string, unknown>;
type InvalidatorFn = (sid: string, data: EventData) => Array<readonly unknown[]>;

const INVALIDATE: Record<string, InvalidatorFn> = {
  agent_turn_started: (sid, d) => {
    const agent = d.agent as string | undefined;
    const turnId = d.turn_id as string | undefined;
    if (agent && turnId) getSessionTurnMap(sid).set(turnId, agent);
    return agent
      ? [["agent-history", sid, agent], ["agents", sid]]
      : [["agents", sid]];
  },
  agent_turn_completed: (sid, d) => {
    const agent = d.agent as string | undefined;
    const turnId = d.turn_id as string | undefined;
    if (turnId) turnIdToAgent.get(sid)?.delete(turnId);
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
      turnIdToAgent.get(sid)?.get(d.turn_id as string);
    return agent ? [["agent-history", sid, agent]] : [];
  },
  agent_llm_response: (sid, d) => {
    const agent =
      (d.agent as string | undefined) ??
      turnIdToAgent.get(sid)?.get(d.turn_id as string);
    return agent ? [["agent-history", sid, agent]] : [];
  },
  agent_tool_call: (sid, d) => {
    const agent =
      (d.agent as string | undefined) ??
      turnIdToAgent.get(sid)?.get(d.turn_id as string);
    return agent ? [["agent-history", sid, agent]] : [];
  },
  agent_tool_result: (sid, d) => {
    const agent =
      (d.agent as string | undefined) ??
      turnIdToAgent.get(sid)?.get(d.turn_id as string);
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
  stage_started: (sid) => [["graph", sid], ["stage-plans", sid]],
  stage_completed: (sid) => [
    ["graph", sid],
    ["experiments", sid],
    ["session", sid],
    ["artifacts", sid],
    ["transitions", sid],
    ["hypotheses", sid],
    ["stage-plans", sid],
  ],
  stage_failed: (sid) => [
    ["graph", sid],
    ["session", sid],
    ["artifacts", sid],
    ["transitions", sid],
  ],
  stage_internal_node_changed: (sid) => [["graph", sid]],
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
      _clearTurnMapForSession(sessionId);
      wsRegistry.release(sessionId);
    };
  }, [sessionId, appendEvent, queryClient]);
}
