import { create } from "zustand";

/**
 * Client-only UI state that doesn't belong in TanStack Query (no server
 * authority) and doesn't belong in URL params (transient, tab-local).
 *
 * Fix E: session list and active session id live in TanStack Query +
 * React Router URL params respectively, not here.
 */

export type DetailTab =
  | "conversation"
  | "artifacts"
  | "experiments"
  | "cost"
  | "hypotheses"
  | "requests"
  | "pi";

const VALID_TABS = new Set<string>([
  "conversation",
  "artifacts",
  "experiments",
  "cost",
  "hypotheses",
  "requests",
  "pi",
]);

/** Normalize stale persisted tab values to a valid DetailTab. */
function normalizeTab(tab: string): DetailTab {
  if (tab === "conversations") return "conversation";
  if (VALID_TABS.has(tab)) return tab as DetailTab;
  return "conversation";
}

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
  detailTab: "conversation",
  sessionListFilter: "",

  setSidebarCollapsed: (sidebarCollapsed) => set({ sidebarCollapsed }),
  toggleSidebar: () =>
    set((state) => ({ sidebarCollapsed: !state.sidebarCollapsed })),
  setDetailTab: (tab) => {
    set({ detailTab: normalizeTab(tab as string) });
  },
  setSessionListFilter: (sessionListFilter) => set({ sessionListFilter }),
}));
