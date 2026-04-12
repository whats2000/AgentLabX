import { useQuery } from "@tanstack/react-query";
import { api } from "../api/client";

/**
 * Shape of a transition record returned by /api/sessions/{id}/transitions.
 * The OpenAPI response is currently typed as `unknown` (schema gap), so we
 * declare the expected fields here. Task 16 should regenerate once the
 * backend exposes the concrete Transition schema.
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
      return (raw ?? []) as Transition[];
    },
    enabled: !!sessionId,
  });
}
