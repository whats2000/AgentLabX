import { useQuery } from "@tanstack/react-query";
import { api } from "../api/client";

/**
 * Shape of a transition record returned by /api/sessions/{id}/transitions.
 * The generated TransitionsResponse types the outer envelope, but the inner
 * transition records are `{ [key: string]: unknown }` so we narrow here.
 */
export interface Transition {
  from_stage: string;
  to_stage: string;
  reason?: string | null;
  triggered_by?: string | null;
  timestamp?: string | null;
}

export function useTransitions(sessionId: string) {
  return useQuery<Transition[]>({
    queryKey: ["transitions", sessionId],
    queryFn: async () => {
      const raw = await api.getTransitions(sessionId);
      return (raw?.transitions ?? []) as unknown as Transition[];
    },
    enabled: !!sessionId,
  });
}
