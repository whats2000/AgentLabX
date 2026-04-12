import { useQuery } from "@tanstack/react-query";
import { api } from "../api/client";
import type { Hypothesis } from "../types/artifacts";

/**
 * Backend wraps hypotheses in a `{hypotheses, total_records}` envelope.
 * Consumers want the flat list; flatten here so every caller doesn't
 * re-implement the unwrap.
 */
export function useHypotheses(sessionId: string) {
  return useQuery<Hypothesis[]>({
    queryKey: ["hypotheses", sessionId],
    queryFn: async () => {
      const raw = await api.getHypotheses(sessionId);
      const envelope = raw as unknown as { hypotheses?: Hypothesis[] } | null;
      return envelope?.hypotheses ?? [];
    },
    enabled: !!sessionId,
  });
}
