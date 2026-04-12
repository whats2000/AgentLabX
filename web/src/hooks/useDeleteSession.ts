import { useMutation, useQueryClient } from "@tanstack/react-query";
import { api } from "../api/client";

export function useDeleteSession() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (sessionId: string) => api.deleteSession(sessionId),
    onSuccess: () => {
      // Invalidate all variants ({sessions, undefined}, {sessions, "alice"}, ...)
      queryClient.invalidateQueries({ queryKey: ["sessions"] });
    },
  });
}
