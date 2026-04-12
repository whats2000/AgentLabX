import { create } from "zustand";

/**
 * Client-only UI state that doesn't belong in TanStack Query (no server
 * authority) and doesn't belong in URL params (transient, tab-local).
 *
 * Fix E: session list and active session id live in TanStack Query +
 * React Router URL params respectively, not here.
 */

export type DetailTab = "activity" | "artifacts" | "graph" | "cost";

interface UIState {
  sidebarCollapsed: boolean;
  detailTab: DetailTab;
  sessionListFilter: string;

  setSidebarCollapsed: (collapsed: boolean) => void;
  toggleSidebar: () => void;
  setDetailTab: (tab: DetailTab) => void;
  setSessionListFilter: (filter: string) => void;
}

export const useUIStore = create<UIState>((set) => ({
  sidebarCollapsed: false,
  detailTab: "activity",
  sessionListFilter: "",

  setSidebarCollapsed: (sidebarCollapsed) => set({ sidebarCollapsed }),
  toggleSidebar: () =>
    set((state) => ({ sidebarCollapsed: !state.sidebarCollapsed })),
  setDetailTab: (detailTab) => set({ detailTab }),
  setSessionListFilter: (sessionListFilter) => set({ sessionListFilter }),
}));
