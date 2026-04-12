import { create } from "zustand";
import type { PipelineEvent } from "../types/events";

/**
 * Per-session ring buffer of streaming WebSocket events.
 *
 * The buffer is client-only state — no server authority, so it does not
 * belong in TanStack Query. Newer events are appended; once the buffer
 * exceeds MAX_EVENTS the oldest entries drop. AgentActivityFeed reads
 * from this store via `getEvents(sessionId)`.
 */
export const MAX_EVENTS = 500;

interface WSState {
  events: Record<string, PipelineEvent[]>;
  appendEvent: (sessionId: string, event: PipelineEvent) => void;
  clearEvents: (sessionId: string) => void;
  getEvents: (sessionId: string) => PipelineEvent[];
}

export const useWSStore = create<WSState>((set, get) => ({
  events: {},
  appendEvent: (sessionId, event) => {
    set((state) => {
      const existing = state.events[sessionId] ?? [];
      const next =
        existing.length >= MAX_EVENTS
          ? [...existing.slice(existing.length - MAX_EVENTS + 1), event]
          : [...existing, event];
      return { events: { ...state.events, [sessionId]: next } };
    });
  },
  clearEvents: (sessionId) => {
    set((state) => {
      if (!(sessionId in state.events)) return state;
      const next = { ...state.events };
      delete next[sessionId];
      return { events: next };
    });
  },
  getEvents: (sessionId) => get().events[sessionId] ?? [],
}));
