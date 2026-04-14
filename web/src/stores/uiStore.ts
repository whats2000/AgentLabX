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

export type DrawerTab =
  | "monitor"
  | "plan"
  | "hypotheses"
  | "pi"
  | "cost"
  | "artifacts"
  | "experiments";

interface UIState {
  sidebarCollapsed: boolean;
  detailTab: DetailTab;
  sessionListFilter: string;

  // Option A layout panel state
  innerPanelOpen: boolean;
  meetingPanelOpen: boolean;
  drawerOpen: boolean;
  drawerTab: DrawerTab;

  setSidebarCollapsed: (collapsed: boolean) => void;
  toggleSidebar: () => void;
  setDetailTab: (tab: DetailTab) => void;
  setSessionListFilter: (filter: string) => void;

  toggleInnerPanel: () => void;
  toggleMeetingPanel: () => void;
  toggleDrawer: () => void;
  setDrawerTab: (tab: DrawerTab) => void;
  /** Reset session-specific panel state when navigating between sessions. */
  resetPanelState: () => void;
}

export const useUIStore = create<UIState>((set) => ({
  sidebarCollapsed: false,
  detailTab: "conversation",
  sessionListFilter: "",

  innerPanelOpen: false,
  meetingPanelOpen: false,
  drawerOpen: false,
  drawerTab: "monitor",

  setSidebarCollapsed: (sidebarCollapsed) => set({ sidebarCollapsed }),
  toggleSidebar: () =>
    set((state) => ({ sidebarCollapsed: !state.sidebarCollapsed })),
  setDetailTab: (tab) => {
    set({ detailTab: normalizeTab(tab as string) });
  },
  setSessionListFilter: (sessionListFilter) => set({ sessionListFilter }),

  toggleInnerPanel: () =>
    set((state) => ({ innerPanelOpen: !state.innerPanelOpen })),
  toggleMeetingPanel: () =>
    set((state) => ({ meetingPanelOpen: !state.meetingPanelOpen })),
  toggleDrawer: () =>
    set((state) => ({ drawerOpen: !state.drawerOpen })),
  setDrawerTab: (tab) => set({ drawerTab: tab }),
  resetPanelState: () => set({ innerPanelOpen: false, meetingPanelOpen: false }),
}));
