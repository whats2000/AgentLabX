import { useQuery } from "@tanstack/react-query";
import type { StagePlan } from "../types/domain";

export interface StagePlansResponse {
  stage_name: string;
  plans: StagePlan[];
}

export function useStagePlans(sessionId: string, stageName: string) {
  return useQuery<StagePlansResponse>({
    queryKey: ["stage-plans", sessionId, stageName],
    queryFn: async () => {
      const r = await fetch(
        `/api/sessions/${sessionId}/stage_plans/${stageName}`,
      );
      if (!r.ok) throw new Error(`Failed to fetch stage plans: ${r.status}`);
      return r.json();
    },
    enabled: Boolean(sessionId && stageName),
  });
}
