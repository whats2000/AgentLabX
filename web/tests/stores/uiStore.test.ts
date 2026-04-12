import { beforeEach, describe, expect, it } from "vitest";
import { useUIStore } from "../../src/stores/uiStore";

describe("uiStore", () => {
  beforeEach(() => {
    useUIStore.setState({
      sidebarCollapsed: false,
      detailTab: "activity",
      sessionListFilter: "",
    });
  });

  it("toggles sidebar", () => {
    const { toggleSidebar } = useUIStore.getState();
    toggleSidebar();
    expect(useUIStore.getState().sidebarCollapsed).toBe(true);
    toggleSidebar();
    expect(useUIStore.getState().sidebarCollapsed).toBe(false);
  });

  it("sets detail tab", () => {
    useUIStore.getState().setDetailTab("graph");
    expect(useUIStore.getState().detailTab).toBe("graph");
  });

  it("updates session list filter", () => {
    useUIStore.getState().setSessionListFilter("neural");
    expect(useUIStore.getState().sessionListFilter).toBe("neural");
  });

  it("setSidebarCollapsed overrides toggle", () => {
    const { setSidebarCollapsed, toggleSidebar } = useUIStore.getState();
    toggleSidebar(); // now true
    setSidebarCollapsed(false);
    expect(useUIStore.getState().sidebarCollapsed).toBe(false);
  });
});
