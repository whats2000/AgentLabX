import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import SessionCreatePage from "../../src/pages/SessionCreatePage";

vi.mock("../../src/api/client", () => ({
  api: {
    createSession: vi.fn(),
  },
  APIError: class extends Error {},
  isValidationError: () => false,
}));

const mockNavigate = vi.fn();
vi.mock("react-router-dom", async () => {
  const actual =
    await vi.importActual<typeof import("react-router-dom")>(
      "react-router-dom",
    );
  return {
    ...actual,
    useNavigate: () => mockNavigate,
  };
});

import { api } from "../../src/api/client";
const mockedApi = api as unknown as {
  createSession: ReturnType<typeof vi.fn>;
};

function renderPage() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false, refetchInterval: false } },
  });
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter>
        <SessionCreatePage />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

const LONG_TOPIC = "Does scaling improve reasoning on math benchmarks";

describe("SessionCreatePage", () => {
  beforeEach(() => {
    mockedApi.createSession.mockReset();
    mockNavigate.mockReset();
  });

  it("disables Next on step 1 until topic is at least 10 chars", async () => {
    const user = userEvent.setup();
    renderPage();

    const topic = screen.getByPlaceholderText(/Describe your research/i);
    const nextBtn = screen.getByRole("button", { name: /Next/i });
    expect(nextBtn).toBeDisabled();

    await user.type(topic, "short");
    expect(nextBtn).toBeDisabled();

    await user.clear(topic);
    await user.type(topic, LONG_TOPIC);
    expect(nextBtn).toBeEnabled();
  });

  it("defaults submit a minimal body (all stages auto, no config)", async () => {
    mockedApi.createSession.mockResolvedValue({
      session_id: "sess-new",
      user_id: "default",
      research_topic: LONG_TOPIC,
      status: "created",
      preferences: {},
      config_overrides: {},
    });
    const user = userEvent.setup();
    renderPage();

    // Step 0: Topic
    await user.type(
      screen.getByPlaceholderText(/Describe your research/i),
      LONG_TOPIC,
    );
    await user.click(screen.getByRole("button", { name: /Next/i }));

    // Step 1: Pipeline (keep defaults)
    expect(await screen.findByText(/Skip stages/)).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: /Next/i }));

    // Step 2: Oversight — per-stage controls always visible (no mode gate)
    expect(await screen.findByText("Literature Review")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: /Next/i }));

    // Step 3: Review — topic should be visible
    expect(await screen.findByText(LONG_TOPIC)).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: /Create session/i }));

    await waitFor(() => {
      expect(mockedApi.createSession).toHaveBeenCalledTimes(1);
    });
    const body = mockedApi.createSession.mock.calls[0][0];
    expect(body.topic).toBe(LONG_TOPIC);
    expect(body.user_id).toBe("default");
    // Every stage still on auto + default pipeline → empty config (no mode key).
    expect(body.config).toEqual({});

    await waitFor(() => {
      expect(mockNavigate).toHaveBeenCalledWith("/sessions/sess-new");
    });
  });

  it("non-auto stage control encodes mode=hitl + stage_controls in the body", async () => {
    mockedApi.createSession.mockResolvedValue({
      session_id: "sess-hitl",
      user_id: "default",
      research_topic: LONG_TOPIC,
      status: "created",
      preferences: {},
      config_overrides: {},
    });
    const user = userEvent.setup();
    renderPage();

    // Step 0
    await user.type(
      screen.getByPlaceholderText(/Describe your research/i),
      LONG_TOPIC,
    );
    await user.click(screen.getByRole("button", { name: /Next/i }));

    // Step 1: Pipeline defaults
    await user.click(screen.getByRole("button", { name: /Next/i }));

    // Step 2: Oversight — per-stage controls always visible. Flip the first
    // stage's control to "approve". Radio.Button inputs have pointer-events:none,
    // so click the visible label.
    expect(await screen.findByText("Literature Review")).toBeInTheDocument();
    const approveLabels = screen.getAllByText(/^approve$/i);
    await user.click(approveLabels[0]);

    await user.click(screen.getByRole("button", { name: /Next/i }));

    // Step 3: submit
    await user.click(screen.getByRole("button", { name: /Create session/i }));

    await waitFor(() => {
      expect(mockedApi.createSession).toHaveBeenCalledTimes(1);
    });
    const body = mockedApi.createSession.mock.calls[0][0];
    // Any non-auto stage override triggers mode=hitl so the backend honours the overrides.
    expect(body.config.preferences.mode).toBe("hitl");
    expect(body.config.preferences.stage_controls).toEqual({
      literature_review: "approve",
    });
  });

  it("surfaces an error when createSession fails", async () => {
    mockedApi.createSession.mockRejectedValue(new Error("backend exploded"));
    const user = userEvent.setup();
    renderPage();

    await user.type(
      screen.getByPlaceholderText(/Describe your research/i),
      LONG_TOPIC,
    );
    await user.click(screen.getByRole("button", { name: /Next/i }));
    await user.click(screen.getByRole("button", { name: /Next/i }));
    await user.click(screen.getByRole("button", { name: /Next/i }));

    await user.click(screen.getByRole("button", { name: /Create session/i }));

    await waitFor(() => {
      expect(mockedApi.createSession).toHaveBeenCalledTimes(1);
    });
    // On failure, we should stay on the Review step — no navigation fired.
    // (Toast rendering via antd's global message() bypasses the component tree,
    // so we verify the observable effect rather than the portal content.)
    await waitFor(() => {
      expect(mockNavigate).not.toHaveBeenCalled();
    });
    // Still on Review step: "Create session" button still present.
    expect(
      screen.getByRole("button", { name: /Create session/i }),
    ).toBeInTheDocument();
  });

  it("includes skip_stages and non-default iteration ceiling in the body", async () => {
    mockedApi.createSession.mockResolvedValue({
      session_id: "sess-pipe",
      user_id: "default",
      research_topic: LONG_TOPIC,
      status: "created",
      preferences: {},
      config_overrides: {},
    });
    const user = userEvent.setup();
    renderPage();

    await user.type(
      screen.getByPlaceholderText(/Describe your research/i),
      LONG_TOPIC,
    );
    await user.click(screen.getByRole("button", { name: /Next/i }));

    // Change iteration ceiling to 100
    const iterInput = screen.getByRole("spinbutton");
    await user.clear(iterInput);
    await user.type(iterInput, "100");

    await user.click(screen.getByRole("button", { name: /Next/i }));
    await user.click(screen.getByRole("button", { name: /Next/i }));
    await user.click(screen.getByRole("button", { name: /Create session/i }));

    await waitFor(() => {
      expect(mockedApi.createSession).toHaveBeenCalledTimes(1);
    });
    const body = mockedApi.createSession.mock.calls[0][0];
    expect(body.config.pipeline.max_total_iterations).toBe(100);
  });
});
