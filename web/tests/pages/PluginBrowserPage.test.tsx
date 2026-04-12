import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import PluginBrowserPage from "../../src/pages/PluginBrowserPage";

vi.mock("../../src/api/client", () => ({
  api: { listPlugins: vi.fn() },
  APIError: class extends Error {},
  isValidationError: () => false,
}));

import { api } from "../../src/api/client";
const mocked = api as unknown as { listPlugins: ReturnType<typeof vi.fn> };

function render_() {
  const qc = new QueryClient({
    defaultOptions: { queries: { retry: false, refetchInterval: false } },
  });
  return render(
    <QueryClientProvider client={qc}>
      <PluginBrowserPage />
    </QueryClientProvider>,
  );
}

describe("PluginBrowserPage", () => {
  beforeEach(() => {
    mocked.listPlugins.mockReset();
  });

  it("renders tabs for each plugin kind", async () => {
    mocked.listPlugins.mockResolvedValue({
      agents: [{ name: "phd_student", description: "PhD student agent" }],
      stages: [{ name: "literature_review" }],
      tools: [{ name: "arxiv_search" }],
      llm_providers: [{ name: "litellm" }],
      execution_backends: [],
      storage_backends: [{ name: "sqlite" }],
      code_agents: [],
    });
    render_();
    await waitFor(() =>
      expect(screen.getByRole("tab", { name: /Agents \(1\)/ })).toBeInTheDocument(),
    );
    expect(screen.getByRole("tab", { name: /Stages \(1\)/ })).toBeInTheDocument();
    expect(screen.getByRole("tab", { name: /Tools \(1\)/ })).toBeInTheDocument();
    expect(screen.getByRole("tab", { name: /Execution Backends \(0\)/ })).toBeInTheDocument();
  });

  it("renders rows for plugins of the active tab", async () => {
    mocked.listPlugins.mockResolvedValue({
      agents: [{ name: "phd_student", description: "PhD student agent" }],
      stages: [],
      tools: [],
      llm_providers: [],
      execution_backends: [],
      storage_backends: [],
      code_agents: [],
    });
    render_();
    expect(await screen.findByText("phd_student")).toBeInTheDocument();
    expect(screen.getByText("PhD student agent")).toBeInTheDocument();
  });

  it("error alert on failure", async () => {
    mocked.listPlugins.mockRejectedValue(new Error("boom"));
    render_();
    expect(
      await screen.findByText(/Failed to load plugins/i),
    ).toBeInTheDocument();
    expect(screen.getByText(/boom/)).toBeInTheDocument();
  });
});
