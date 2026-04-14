import { describe, it, expect, vi } from "vitest";
import { renderHook, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import type { ReactNode } from "react";
import { useStagePlans } from "../../src/hooks/useStagePlans";

function wrapper() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={qc}>{children}</QueryClientProvider>
  );
}

describe("useStagePlans", () => {
  it("fetches stage plans for a given stage", async () => {
    const mockResponse = {
      stage_name: "literature_review",
      plans: [
        {
          items: [
            {
              id: "lit:topic-survey",
              description: "Survey X",
              status: "todo",
              source: "contract",
              existing_artifact_ref: null,
              edit_note: null,
              removed_reason: null,
            },
          ],
          rationale: "Default plan",
          hash_of_consumed_inputs: "abc",
        },
      ],
    };
    vi.spyOn(globalThis, "fetch").mockResolvedValueOnce({
      ok: true,
      json: () => Promise.resolve(mockResponse),
    } as Response);

    const { result } = renderHook(
      () => useStagePlans("sess-1", "literature_review"),
      { wrapper: wrapper() },
    );

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(result.current.data).toEqual(mockResponse);
  });

  it("returns empty plans list for a stage that has no history yet", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValueOnce({
      ok: true,
      json: () =>
        Promise.resolve({ stage_name: "experimentation", plans: [] }),
    } as Response);

    const { result } = renderHook(
      () => useStagePlans("sess-2", "experimentation"),
      { wrapper: wrapper() },
    );

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(result.current.data?.plans).toEqual([]);
  });
});
