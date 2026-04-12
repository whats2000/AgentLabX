import { useMutation, useQueryClient } from "@tanstack/react-query";
import { api } from "../api/client";
import type { paths } from "../api/generated";

type PrefsBody = NonNullable<
  paths["/api/sessions/{session_id}/preferences"]["patch"]["requestBody"]
>["content"]["application/json"];

type RedirectBody = NonNullable<
  paths["/api/sessions/{session_id}/redirect"]["post"]["requestBody"]
>["content"]["application/json"];

export function useStartSession(sessionId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: () => api.startSession(sessionId),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["session", sessionId] }),
  });
}

export function usePauseSession(sessionId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: () => api.pauseSession(sessionId),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["session", sessionId] }),
  });
}

export function useResumeSession(sessionId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: () => api.resumeSession(sessionId),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["session", sessionId] }),
  });
}

export function useRedirectSession(sessionId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: RedirectBody) => api.redirectSession(sessionId, body),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["session", sessionId] });
      qc.invalidateQueries({ queryKey: ["transitions", sessionId] });
    },
  });
}

/**
 * Optimistic preferences update. The PATCH /preferences endpoint is a
 * shallow merge on the server, so we mirror that on the client so the
 * UI reflects the toggle immediately; onError rolls back if the server
 * rejects the change, and onSettled reconciles with the authoritative
 * session payload.
 */
export function useUpdatePreferences(sessionId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: PrefsBody) => api.updatePreferences(sessionId, body),
    onMutate: async (update) => {
      await qc.cancelQueries({ queryKey: ["session", sessionId] });
      const previous = qc.getQueryData(["session", sessionId]);
      qc.setQueryData(["session", sessionId], (old: unknown) => {
        if (!old || typeof old !== "object") return old;
        const prev = old as Record<string, unknown>;
        const prefs = (prev.preferences ?? {}) as Record<string, unknown>;
        return { ...prev, preferences: { ...prefs, ...update } };
      });
      return { previous };
    },
    onError: (_err, _update, ctx) => {
      if (ctx?.previous !== undefined) {
        qc.setQueryData(["session", sessionId], ctx.previous);
      }
    },
    onSettled: () => qc.invalidateQueries({ queryKey: ["session", sessionId] }),
  });
}
