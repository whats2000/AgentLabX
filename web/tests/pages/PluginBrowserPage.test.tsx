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

  it("renders tabs for each plugin kind using singular backend keys", async () => {
    // Backend returns singular PluginType.value keys (agent, stage, tool,
    // llm_provider, execution_backend, storage_backend, code_agent).
    mocked.listPlugins.mockResolvedValue({
      agent: [{ name: "phd_student", description: "PhD student agent" }],
      stage: [{ name: "literature_review", description: "" }],
      tool: [{ name: "arxiv_search", description: "" }],
      llm_provider: [{ name: "litellm", description: "" }],
      execution_backend: [],
      storage_backend: [{ name: "sqlite", description: "" }],
      code_agent: [],
    });
    render_();
    await waitFor(() =>
      expect(
        screen.getByRole("tab", { name: /Agents \(1\)/ }),
      ).toBeInTheDocument(),
    );
    expect(screen.getByRole("tab", { name: /Stages \(1\)/ })).toBeInTheDocument();
    expect(screen.getByRole("tab", { name: /Tools \(1\)/ })).toBeInTheDocument();
    // Fix 2: acronym survives the label map instead of becoming "Llm Providers"
    expect(
      screen.getByRole("tab", { name: /LLM Providers \(1\)/ }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("tab", { name: /Execution Backends \(0\)/ }),
    ).toBeInTheDocument();
  });

  it("renders rows with name and description in the active tab", async () => {
    mocked.listPlugins.mockResolvedValue({
      agent: [{ name: "phd_student", description: "PhD student agent" }],
      stage: [],
      tool: [],
      llm_provider: [],
      execution_backend: [],
      storage_backend: [],
      code_agent: [],
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
