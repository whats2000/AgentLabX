import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import type { ReactNode } from "react";
import { ChatView } from "../../src/components/session/ChatView";

function wrapper() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={qc}>{children}</QueryClientProvider>
  );
}

describe("ChatView stage-grouped lazy-load", () => {
  beforeEach(() => {
    vi.resetAllMocks();
  });

  it("renders a panel for each stage in the default sequence", () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue({
      ok: true,
      json: () => Promise.resolve({ turns: [] }),
    } as Response);

    render(<ChatView sessionId="s1" activeStage="literature_review" />, {
      wrapper: wrapper(),
    });

    // Headers for all 8 stages visible
    [
      "literature_review",
      "plan_formulation",
      "experimentation",
      "peer_review",
    ].forEach((name) => {
      expect(
        screen.getByText(new RegExp(name.replace(/_/g, " "), "i")),
      ).toBeInTheDocument();
    });
  });

  it("auto-expands only the activeStage section on first render", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue({
      ok: true,
      json: () => Promise.resolve({ turns: [] }),
    } as Response);

    const fetchSpy = globalThis.fetch as ReturnType<typeof vi.fn>;
    render(<ChatView sessionId="s1" activeStage="experimentation" />, {
      wrapper: wrapper(),
    });

    // Give TanStack Query time to trigger the enabled query
    await waitFor(() => {
      const calls = fetchSpy.mock.calls.map((c) => String(c[0]));
      expect(calls.filter((u) => u.includes("experimentation")).length).toBeGreaterThan(0);
    });

    // literature_review panel is collapsed by default; lazy-load hasn't fired
    const calls = fetchSpy.mock.calls.map((c) => String(c[0]));
    const literatureCalls = calls.filter((u) => u.includes("literature_review"));
    expect(literatureCalls.length).toBe(0);
  });

  it("expanding a previously-collapsed panel triggers its lazy-load", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue({
      ok: true,
      json: () => Promise.resolve({ turns: [] }),
    } as Response);

    const fetchSpy = globalThis.fetch as ReturnType<typeof vi.fn>;
    render(<ChatView sessionId="s1" activeStage="experimentation" />, {
      wrapper: wrapper(),
    });

    // Initial: no literature_review fetch
    const initialCalls = fetchSpy.mock.calls.map((c) => String(c[0]));
    expect(initialCalls.filter((u) => u.includes("literature_review")).length).toBe(0);

    // User clicks literature_review panel header to expand
    const header = screen.getByText(/literature[ _]review/i);
    await userEvent.click(header);

    // Now a fetch for literature_review should have fired
    await waitFor(() => {
      const calls = fetchSpy.mock.calls.map((c) => String(c[0]));
      expect(
        calls.filter((u) => u.includes("literature_review")).length,
      ).toBeGreaterThan(0);
    });
  });
});
