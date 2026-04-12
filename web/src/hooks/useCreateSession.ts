import { useMutation, useQueryClient } from "@tanstack/react-query";
import { api } from "../api/client";
import type { paths } from "../api/generated";

type CreateBody = NonNullable<
  paths["/api/sessions"]["post"]["requestBody"]
>["content"]["application/json"];

export function useCreateSession() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (body: CreateBody) => api.createSession(body),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["sessions"] });
    },
  });
}
