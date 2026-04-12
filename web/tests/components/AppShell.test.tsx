import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import AppShell from "../../src/components/AppShell";
import SessionListPage from "../../src/pages/SessionListPage";
import PluginBrowserPage from "../../src/pages/PluginBrowserPage";

function renderAt(initialPath: string) {
  return render(
    <MemoryRouter initialEntries={[initialPath]}>
      <Routes>
        <Route element={<AppShell />}>
          <Route path="sessions" element={<SessionListPage />} />
          <Route path="plugins" element={<PluginBrowserPage />} />
        </Route>
      </Routes>
    </MemoryRouter>,
  );
}

describe("AppShell", () => {
  it("renders the sessions stub under /sessions", () => {
    renderAt("/sessions");
    expect(screen.getByText(/Sessions \(stub\)/i)).toBeInTheDocument();
  });

  it("renders the plugins stub under /plugins", () => {
    renderAt("/plugins");
    expect(screen.getByText(/Plugins \(stub\)/i)).toBeInTheDocument();
  });

  it("renders the AgentLabX header", () => {
    renderAt("/sessions");
    expect(screen.getAllByText(/AgentLabX/i).length).toBeGreaterThan(0);
  });
});
