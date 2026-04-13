import { useMutation, useQueryClient } from "@tanstack/react-query";
import { api } from "../api/client";

export type ControlLevel = "auto" | "notify" | "approve" | "edit";

export function useUpdateStagePreference(sessionId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (vars: { stage: string; level: ControlLevel }) =>
      api.updatePreferences(sessionId, {
        stage_controls: { [vars.stage]: vars.level },
      }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["session", sessionId] });
    },
  });
}
