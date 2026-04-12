# Plan 5: Frontend — React + Ant Design + Vite

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the React frontend for AgentLabX — a research dashboard that lets users create sessions, monitor pipeline execution in real time via WebSocket, steer HITL sessions (approve/redirect/edit), browse plugins, and view artifacts/hypotheses/cost. After Plan 5, `agentlabx serve` delivers a complete browser experience with zero additional setup.

**Architecture:** Vite + React 19 + TypeScript in `web/`. Ant Design 5 for all UI chrome. React Flow for the pipeline graph. Zustand for client state (sessions list cache, active session state, WS event buffer). TanStack Query for server state (REST polling + invalidation). `openapi-typescript` auto-generates types from FastAPI's `/openapi.json` — no hand-written DTOs. WebSocket service with auto-reconnect and per-session subscription. During dev, Vite proxies `/api` and `/ws` to `localhost:8000`. In production, FastAPI serves the built bundle from `web/dist` via a static files mount.

**Tech Stack:**
- React 19 + TypeScript 5.5+ + Vite 6
- Ant Design 5.22+ (Layout, Table, Modal, Form, Steps, Tree, Tabs, Typography)
- @ant-design/plots 2 (CostTracker gauges + time series)
- @xyflow/react 12 (React Flow — pipeline graph)
- zustand 5 (client state)
- @tanstack/react-query 5 (server state)
- react-router-dom 7 (SPA routing)
- openapi-typescript 7 + @hey-api/openapi-ts (typed client codegen)
- vitest 2 + @testing-library/react + jsdom (unit tests)
- MSW 2 (mock service worker for integration tests)

**Spec reference:** `docs/superpowers/specs/2026-04-12-agentlabx-platform-design.md` §8 (Frontend)

**Depends on:** Plan 4 (409 tests passing, full REST + WS API, `agentlabx serve --mock-llm` works)

---

## File Structure

```
web/
  src/
    main.tsx                  # Entry — mount App
    App.tsx                   # Router + providers (QueryClient, AntD ConfigProvider)
    api/
      client.ts               # Typed REST client (openapi-typescript)
      ws.ts                   # WebSocket service (connect, subscribe, reconnect)
      generated.ts            # AUTO-GENERATED from /openapi.json — do not edit
    stores/
      sessionsStore.ts        # Zustand — list of sessions, filters
      activeSessionStore.ts   # Zustand — currently selected session state
      wsStore.ts              # Zustand — streaming event buffer per session
    hooks/
      useSession.ts           # TanStack Query hooks for a single session
      useSessions.ts          # TanStack Query hooks for list
      useWebSocket.ts         # WS subscription hook tied to active session
      usePipelineEvents.ts    # Typed event stream iterator
    pages/
      SessionListPage.tsx
      SessionCreatePage.tsx
      SessionDetailPage.tsx
      PluginBrowserPage.tsx
      SettingsPage.tsx
    components/
      AppShell.tsx            # Sidebar + header + main content area
      session/
        PipelineGraph.tsx     # React Flow graph
        AgentActivityFeed.tsx # WS-driven streaming log
        StageOutputPanel.tsx  # Versioned artifacts viewer
        ControlBar.tsx        # Pause/resume/redirect + mode toggle + stage controls
        CostTracker.tsx       # Budget gauge + history chart
        CheckpointModal.tsx   # HITL approval dialog
        FeedbackInput.tsx     # Human → agent message box
        HypothesisTracker.tsx # Hypothesis status cards
      plugins/
        PluginList.tsx
      common/
        StatusBadge.tsx       # CREATED / RUNNING / PAUSED / ... with color
        LoadingSpinner.tsx
        EmptyState.tsx
    types/
      events.ts               # Typed WS event discriminated unions
      domain.ts               # Re-exports from generated.ts with friendlier names
    theme.ts                  # Ant Design theme tokens
    index.css
  public/
    favicon.svg
  tests/
    setup.ts                  # Vitest setup + jsdom + MSW
    stores/
      sessionsStore.test.ts
      activeSessionStore.test.ts
    components/
      PipelineGraph.test.tsx
      ControlBar.test.tsx
      AgentActivityFeed.test.tsx
    pages/
      SessionListPage.test.tsx
      SessionDetailPage.test.tsx
  vite.config.ts
  tsconfig.json
  tsconfig.node.json
  package.json
  .eslintrc.cjs               # or eslint.config.js (flat config)
  index.html
  README.md                   # Dev setup + build instructions

agentlabx/
  server/
    static.py                 # NEW: mount web/dist at / (serves SPA)
    app.py                    # EXTENDED: call mount_spa(app) in create_app
```

---

### Task 1: Scaffold Vite + React + TypeScript Project

**Files:**
- Create `web/` directory
- `web/package.json`
- `web/vite.config.ts`
- `web/tsconfig.json`
- `web/tsconfig.node.json`
- `web/index.html`
- `web/src/main.tsx`
- `web/src/App.tsx`
- `web/src/index.css`
- `web/README.md`
- `web/.gitignore`

- [ ] **Step 1: Initialize package.json**

```json
{
  "name": "agentlabx-web",
  "private": true,
  "version": "0.1.0",
  "type": "module",
  "scripts": {
    "dev": "vite",
    "build": "tsc -b && vite build",
    "preview": "vite preview",
    "test": "vitest",
    "test:ui": "vitest --ui",
    "lint": "eslint src --ext ts,tsx",
    "typecheck": "tsc --noEmit",
    "codegen": "openapi-typescript http://localhost:8000/openapi.json -o src/api/generated.ts"
  },
  "dependencies": {
    "@ant-design/plots": "^2.3.0",
    "@tanstack/react-query": "^5.56.0",
    "@xyflow/react": "^12.3.0",
    "antd": "^5.22.0",
    "react": "^19.0.0",
    "react-dom": "^19.0.0",
    "react-router-dom": "^7.0.0",
    "zustand": "^5.0.0"
  },
  "devDependencies": {
    "@testing-library/jest-dom": "^6.5.0",
    "@testing-library/react": "^16.0.0",
    "@testing-library/user-event": "^14.5.0",
    "@types/react": "^19.0.0",
    "@types/react-dom": "^19.0.0",
    "@vitejs/plugin-react": "^4.3.0",
    "jsdom": "^25.0.0",
    "msw": "^2.6.0",
    "openapi-typescript": "^7.4.0",
    "typescript": "^5.5.0",
    "vite": "^6.0.0",
    "vitest": "^2.1.0"
  }
}
```

- [ ] **Step 2: vite.config.ts**

```typescript
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import path from "node:path";

export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: { "@": path.resolve(__dirname, "src") },
  },
  server: {
    port: 5173,
    proxy: {
      "/api": "http://localhost:8000",
      "/ws": { target: "ws://localhost:8000", ws: true },
    },
  },
  build: {
    outDir: "dist",
    emptyOutDir: true,
    sourcemap: true,
  },
  test: {
    environment: "jsdom",
    globals: true,
    setupFiles: ["./tests/setup.ts"],
  },
});
```

- [ ] **Step 3: tsconfig files**

`tsconfig.json`:
```json
{
  "compilerOptions": {
    "target": "ES2022",
    "lib": ["ES2022", "DOM", "DOM.Iterable"],
    "module": "ESNext",
    "moduleResolution": "Bundler",
    "jsx": "react-jsx",
    "strict": true,
    "noUnusedLocals": true,
    "noUnusedParameters": true,
    "noFallthroughCasesInSwitch": true,
    "noEmit": true,
    "skipLibCheck": true,
    "esModuleInterop": true,
    "resolveJsonModule": true,
    "isolatedModules": true,
    "allowSyntheticDefaultImports": true,
    "baseUrl": ".",
    "paths": { "@/*": ["src/*"] },
    "types": ["vite/client", "vitest/globals", "@testing-library/jest-dom"]
  },
  "include": ["src", "tests"],
  "references": [{ "path": "./tsconfig.node.json" }]
}
```

`tsconfig.node.json`:
```json
{
  "compilerOptions": {
    "composite": true,
    "skipLibCheck": true,
    "module": "ESNext",
    "moduleResolution": "Bundler",
    "allowSyntheticDefaultImports": true,
    "strict": true
  },
  "include": ["vite.config.ts"]
}
```

- [ ] **Step 4: index.html + main.tsx + App.tsx shells**

`index.html`:
```html
<!DOCTYPE html>
<html lang="en">
  <head>
    <meta charset="UTF-8" />
    <link rel="icon" type="image/svg+xml" href="/favicon.svg" />
    <meta name="viewport" content="width=device-width, initial-scale=1.0" />
    <title>AgentLabX</title>
  </head>
  <body>
    <div id="root"></div>
    <script type="module" src="/src/main.tsx"></script>
  </body>
</html>
```

`src/main.tsx`:
```tsx
import React from "react";
import ReactDOM from "react-dom/client";
import App from "./App";
import "./index.css";

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>,
);
```

`src/App.tsx` (minimal placeholder — Task 5 expands):
```tsx
export default function App() {
  return <div>AgentLabX (scaffold)</div>;
}
```

`src/index.css`:
```css
html, body, #root {
  margin: 0;
  padding: 0;
  height: 100%;
  font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
}
```

- [ ] **Step 5: web/.gitignore + web/README.md**

`.gitignore`:
```
node_modules
dist
.vitest-cache
coverage
src/api/generated.ts
```

`README.md`: quick start notes — `npm install && npm run dev` requires the backend at `localhost:8000`; `npm run codegen` regenerates API types.

- [ ] **Step 6: Install + verify**

```bash
cd web
npm install
npm run typecheck  # Should pass
npm run build  # Should produce dist/
```

- [ ] **Step 7: Commit**

```bash
git add web/
git commit -m "feat(web): scaffold Vite + React 19 + TypeScript + Ant Design project"
```

---

### Task 2: OpenAPI Type Generation + REST Client

**Files:**
- `web/src/api/client.ts`
- `web/src/api/generated.ts` (auto-generated, committed only as stub)
- `web/src/types/domain.ts`
- Update: `web/package.json` (codegen script)

- [ ] **Step 1: Generate types from live backend**

Run the backend (`agentlabx serve --mock-llm`), then from `web/`:

```bash
npm run codegen
```

This writes `src/api/generated.ts` with types for every schema/path in the FastAPI spec.

**Backup plan** if backend isn't available: copy `openapi.json` from a running instance and use `openapi-typescript path/to/openapi.json -o src/api/generated.ts`.

**Important:** `src/api/generated.ts` is gitignored because it's auto-generated. CI re-runs `npm run codegen` against a running backend before building. Keep a small stub committed (`src/api/generated.placeholder.ts`) with minimal types so typecheck passes before first codegen.

Actually — simpler approach: commit the generated file, do NOT gitignore. When the API changes, the diff on `generated.ts` is reviewable and obvious. Remove `src/api/generated.ts` from `.gitignore`.

- [ ] **Step 2: `web/src/api/client.ts`**

Thin wrapper around fetch that uses the generated types. Approach: hand-rolled typed functions rather than a full client library (to keep deps minimal):

```typescript
import type { paths } from "./generated";

const BASE = ""; // Same-origin via Vite proxy or static serving

export class APIError extends Error {
  constructor(public status: number, public body: unknown) {
    super(`API ${status}: ${JSON.stringify(body)}`);
  }
}

async function request<T>(
  method: string,
  path: string,
  body?: unknown,
): Promise<T> {
  const response = await fetch(`${BASE}${path}`, {
    method,
    headers: body ? { "Content-Type": "application/json" } : {},
    body: body ? JSON.stringify(body) : undefined,
  });
  if (!response.ok) {
    let parsed: unknown;
    try {
      parsed = await response.json();
    } catch {
      parsed = await response.text();
    }
    throw new APIError(response.status, parsed);
  }
  // Some endpoints return 202 with no body
  const text = await response.text();
  return (text ? JSON.parse(text) : undefined) as T;
}

// Type helpers
type Get<P extends keyof paths> = paths[P] extends { get: { responses: { 200: { content: { "application/json": infer T } } } } } ? T : never;
type Post<P extends keyof paths> =
  paths[P] extends { post: { responses: infer R } }
    ? R extends { 200: { content: { "application/json": infer T } } }
      ? T
      : R extends { 201: { content: { "application/json": infer T } } }
        ? T
        : R extends { 202: { content: { "application/json": infer T } } }
          ? T
          : unknown
    : unknown;

type Body<P extends keyof paths, M extends "post" | "patch"> =
  paths[P] extends { [K in M]: { requestBody: { content: { "application/json": infer B } } } } ? B : never;

export const api = {
  async listSessions(userId?: string) {
    const query = userId ? `?user_id=${encodeURIComponent(userId)}` : "";
    return request<Get<"/api/sessions">>("GET", `/api/sessions${query}`);
  },
  async createSession(body: Body<"/api/sessions", "post">) {
    return request<Post<"/api/sessions">>("POST", "/api/sessions", body);
  },
  async getSession(sessionId: string) {
    return request<Get<"/api/sessions/{session_id}">>(
      "GET", `/api/sessions/${sessionId}`,
    );
  },
  async startSession(sessionId: string) {
    return request<Post<"/api/sessions/{session_id}/start">>(
      "POST", `/api/sessions/${sessionId}/start`,
    );
  },
  async pauseSession(sessionId: string) {
    return request<Post<"/api/sessions/{session_id}/pause">>(
      "POST", `/api/sessions/${sessionId}/pause`,
    );
  },
  async resumeSession(sessionId: string) {
    return request<Post<"/api/sessions/{session_id}/resume">>(
      "POST", `/api/sessions/${sessionId}/resume`,
    );
  },
  async redirectSession(sessionId: string, body: Body<"/api/sessions/{session_id}/redirect", "post">) {
    return request<Post<"/api/sessions/{session_id}/redirect">>(
      "POST", `/api/sessions/${sessionId}/redirect`, body,
    );
  },
  async updatePreferences(sessionId: string, body: Body<"/api/sessions/{session_id}/preferences", "patch">) {
    return request("PATCH", `/api/sessions/${sessionId}/preferences`, body);
  },
  async getArtifacts(sessionId: string) {
    return request<Get<"/api/sessions/{session_id}/artifacts">>(
      "GET", `/api/sessions/${sessionId}/artifacts`,
    );
  },
  async getTransitions(sessionId: string) {
    return request<Get<"/api/sessions/{session_id}/transitions">>(
      "GET", `/api/sessions/${sessionId}/transitions`,
    );
  },
  async getCost(sessionId: string) {
    return request<Get<"/api/sessions/{session_id}/cost">>(
      "GET", `/api/sessions/${sessionId}/cost`,
    );
  },
  async getHypotheses(sessionId: string) {
    return request<Get<"/api/sessions/{session_id}/hypotheses">>(
      "GET", `/api/sessions/${sessionId}/hypotheses`,
    );
  },
  async listPlugins() {
    return request<Get<"/api/plugins">>("GET", "/api/plugins");
  },
};
```

- [ ] **Step 3: `web/src/types/domain.ts`** — re-export friendly aliases

```typescript
import type { components } from "../api/generated";

export type SessionSummary = components["schemas"]["SessionSummary"];
export type SessionDetail = components["schemas"]["SessionDetail"];
export type SessionCreateRequest = components["schemas"]["SessionCreateRequest"];
export type PreferencesUpdateRequest = components["schemas"]["PreferencesUpdateRequest"];
export type RedirectRequest = components["schemas"]["RedirectRequest"];

// Domain enums as string literal unions (matches FastAPI)
export type SessionStatus =
  | "created" | "running" | "paused" | "completed" | "failed";

export type ControlLevel = "auto" | "notify" | "approve" | "edit";
export type BacktrackControl = "auto" | "notify" | "approve";
export type Mode = "auto" | "hitl";
```

- [ ] **Step 4: Tests**

`web/tests/setup.ts`:
```typescript
import "@testing-library/jest-dom/vitest";
```

No test for `client.ts` yet — Task 4 tests via MSW when stores land.

- [ ] **Step 5: Commit**

```bash
git add web/src/api web/src/types web/package.json
git commit -m "feat(web): add typed REST client with openapi-typescript generation"
```

---

### Task 3: WebSocket Service with Auto-Reconnect

**Files:**
- `web/src/api/ws.ts`
- `web/tests/api/ws.test.ts`

- [ ] **Step 1: Define event types**

`web/src/types/events.ts`:
```typescript
/**
 * WebSocket event types emitted by the backend.
 * Mirrors agentlabx.server.events constants.
 */

export type PipelineEventType =
  | "stage_started"
  | "stage_completed"
  | "stage_failed"
  | "agent_thinking"
  | "agent_tool_call"
  | "agent_dialogue"
  | "transition"
  | "checkpoint_reached"
  | "cost_update"
  | "error";

export interface PipelineEvent<T = unknown> {
  type: PipelineEventType;
  data: T;
  source?: string | null;
}

export interface StageStartedEvent extends PipelineEvent<{ stage: string; session_id: string }> {
  type: "stage_started";
}

export interface StageCompletedEvent extends PipelineEvent<{
  stage: string;
  session_id: string;
  status: string;
  reason: string;
  next_hint: string | null;
}> {
  type: "stage_completed";
}

export interface StageFailedEvent extends PipelineEvent<{
  stage: string;
  session_id: string;
  error_type: string;
  message: string;
}> {
  type: "stage_failed";
}

// Client → server action messages
export type ClientAction =
  | { action: "update_preferences"; mode?: "auto" | "hitl"; stage_controls?: Record<string, string>; backtrack_control?: string }
  | { action: "redirect"; target_stage: string; reason?: string }
  | { action: "inject_feedback"; content: string }
  | { action: "approve" }
  | { action: "edit"; content: string };
```

- [ ] **Step 2: `web/src/api/ws.ts`**

```typescript
import type { PipelineEvent, ClientAction } from "../types/events";

export type EventHandler = (event: PipelineEvent) => void;

export class SessionWebSocket {
  private socket: WebSocket | null = null;
  private handlers = new Set<EventHandler>();
  private reconnectAttempts = 0;
  private reconnectTimer: number | null = null;
  private manuallyClosed = false;

  constructor(
    private readonly sessionId: string,
    private readonly url: string = `${wsScheme()}://${window.location.host}/ws/sessions/${sessionId}`,
  ) {}

  connect(): void {
    this.manuallyClosed = false;
    this.socket = new WebSocket(this.url);
    this.socket.addEventListener("open", () => {
      this.reconnectAttempts = 0;
    });
    this.socket.addEventListener("message", (ev) => {
      try {
        const payload = JSON.parse(ev.data) as PipelineEvent;
        this.handlers.forEach((h) => h(payload));
      } catch (err) {
        console.warn("Failed to parse WS message:", err);
      }
    });
    this.socket.addEventListener("close", (ev) => {
      if (this.manuallyClosed) return;
      // Exponential backoff reconnect, capped at 30s
      const delay = Math.min(1000 * 2 ** this.reconnectAttempts, 30000);
      this.reconnectAttempts += 1;
      this.reconnectTimer = window.setTimeout(() => this.connect(), delay);
    });
  }

  disconnect(): void {
    this.manuallyClosed = true;
    if (this.reconnectTimer !== null) {
      clearTimeout(this.reconnectTimer);
      this.reconnectTimer = null;
    }
    this.socket?.close();
    this.socket = null;
  }

  send(action: ClientAction): void {
    if (this.socket?.readyState === WebSocket.OPEN) {
      this.socket.send(JSON.stringify(action));
    } else {
      console.warn("WS not open, dropping action:", action);
    }
  }

  onEvent(handler: EventHandler): () => void {
    this.handlers.add(handler);
    return () => {
      this.handlers.delete(handler);
    };
  }
}

function wsScheme(): string {
  return window.location.protocol === "https:" ? "wss" : "ws";
}
```

- [ ] **Step 3: Tests**

`web/tests/api/ws.test.ts` — use a mock WebSocket class:

```typescript
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { SessionWebSocket } from "../../src/api/ws";

class MockWebSocket {
  static OPEN = 1;
  readyState = MockWebSocket.OPEN;
  handlers: Record<string, ((ev: unknown) => void)[]> = {};
  sent: string[] = [];
  addEventListener(type: string, handler: (ev: unknown) => void) {
    (this.handlers[type] ??= []).push(handler);
  }
  send(data: string) { this.sent.push(data); }
  close() {
    this.readyState = 3;
    this.handlers["close"]?.forEach((h) => h({ code: 1000 }));
  }
  trigger(type: string, event: unknown) {
    this.handlers[type]?.forEach((h) => h(event));
  }
}

describe("SessionWebSocket", () => {
  let instances: MockWebSocket[] = [];

  beforeEach(() => {
    instances = [];
    vi.stubGlobal("WebSocket", vi.fn().mockImplementation(() => {
      const instance = new MockWebSocket();
      instances.push(instance);
      return instance;
    }));
    Object.defineProperty(WebSocket, "OPEN", { value: 1, configurable: true });
    vi.stubGlobal("window", {
      ...globalThis.window,
      location: { host: "localhost:5173", protocol: "http:" },
      setTimeout: (fn: () => void, _ms: number) => setTimeout(fn, 0),
      clearTimeout: (id: number) => clearTimeout(id),
    });
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("delivers events to subscribers", () => {
    const ws = new SessionWebSocket("sess-1");
    const handler = vi.fn();
    ws.onEvent(handler);
    ws.connect();
    instances[0].trigger("message", {
      data: JSON.stringify({ type: "stage_started", data: { stage: "x" } }),
    });
    expect(handler).toHaveBeenCalledWith({
      type: "stage_started",
      data: { stage: "x" },
    });
  });

  it("sends actions as JSON", () => {
    const ws = new SessionWebSocket("sess-1");
    ws.connect();
    ws.send({ action: "update_preferences", mode: "hitl" });
    expect(instances[0].sent[0]).toBe(
      JSON.stringify({ action: "update_preferences", mode: "hitl" }),
    );
  });

  it("unsubscribes handlers", () => {
    const ws = new SessionWebSocket("sess-1");
    const handler = vi.fn();
    const unsubscribe = ws.onEvent(handler);
    ws.connect();
    unsubscribe();
    instances[0].trigger("message", {
      data: JSON.stringify({ type: "stage_started", data: {} }),
    });
    expect(handler).not.toHaveBeenCalled();
  });

  it("does not reconnect after disconnect()", () => {
    const ws = new SessionWebSocket("sess-1");
    ws.connect();
    ws.disconnect();
    // Close event on the initial socket should NOT schedule reconnect
    const creationCount = (WebSocket as unknown as { mock: { calls: unknown[] } }).mock.calls.length;
    // Since manuallyClosed=true, no new socket should be created
    expect(creationCount).toBe(1);
  });
});
```

- [ ] **Step 4: Commit**

```bash
git add web/src/api/ws.ts web/src/types/events.ts web/tests/api/
git commit -m "feat(web): add SessionWebSocket service with auto-reconnect"
```

---

### Task 4: Zustand Stores

**Files:**
- `web/src/stores/sessionsStore.ts`
- `web/src/stores/activeSessionStore.ts`
- `web/src/stores/wsStore.ts`
- `web/tests/stores/sessionsStore.test.ts`
- `web/tests/stores/activeSessionStore.test.ts`
- `web/tests/stores/wsStore.test.ts`

Store responsibilities:
- **sessionsStore** — cached list + filters (user filter, status filter)
- **activeSessionStore** — selected session id, preferences draft (optimistic update before API returns)
- **wsStore** — ring buffer of recent events per session (max 500), plus latest stage status

Example `wsStore.ts`:
```typescript
import { create } from "zustand";
import type { PipelineEvent } from "../types/events";

interface WSState {
  events: Record<string, PipelineEvent[]>;
  // Cap per-session events to this many; older ones drop.
  MAX_EVENTS: number;
  appendEvent: (sessionId: string, event: PipelineEvent) => void;
  clearEvents: (sessionId: string) => void;
  getEvents: (sessionId: string) => PipelineEvent[];
}

export const useWSStore = create<WSState>((set, get) => ({
  events: {},
  MAX_EVENTS: 500,
  appendEvent: (sessionId, event) => {
    set((state) => {
      const existing = state.events[sessionId] ?? [];
      const next = [...existing, event];
      if (next.length > state.MAX_EVENTS) {
        next.splice(0, next.length - state.MAX_EVENTS);
      }
      return { events: { ...state.events, [sessionId]: next } };
    });
  },
  clearEvents: (sessionId) => {
    set((state) => {
      const next = { ...state.events };
      delete next[sessionId];
      return { events: next };
    });
  },
  getEvents: (sessionId) => get().events[sessionId] ?? [],
}));
```

Tests cover append + cap + clear.

Similarly for sessionsStore (list state + filter setters) and activeSessionStore (current id + optimistic prefs).

Commit: `feat(web): add Zustand stores for sessions, active session, and WS events`

---

### Task 5: App Shell + Routing + Theme + Providers

**Files:**
- `web/src/App.tsx` (real implementation)
- `web/src/components/AppShell.tsx`
- `web/src/theme.ts`
- `web/tests/components/AppShell.test.tsx`

`src/theme.ts` — Ant Design theme tokens:
```typescript
import { theme } from "antd";
import type { ThemeConfig } from "antd";

export const lightTheme: ThemeConfig = {
  token: {
    colorPrimary: "#6366f1",
    borderRadius: 6,
    fontFamily: "-apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif",
  },
};

export const darkTheme: ThemeConfig = {
  algorithm: theme.darkAlgorithm,
  token: { colorPrimary: "#818cf8", borderRadius: 6 },
};
```

`src/App.tsx`:
```tsx
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { ConfigProvider } from "antd";
import { BrowserRouter, Route, Routes, Navigate } from "react-router-dom";
import AppShell from "./components/AppShell";
import SessionListPage from "./pages/SessionListPage";
import SessionDetailPage from "./pages/SessionDetailPage";
import SessionCreatePage from "./pages/SessionCreatePage";
import PluginBrowserPage from "./pages/PluginBrowserPage";
import SettingsPage from "./pages/SettingsPage";
import { lightTheme } from "./theme";

const queryClient = new QueryClient({
  defaultOptions: {
    queries: { staleTime: 5_000, refetchOnWindowFocus: false },
  },
});

export default function App() {
  return (
    <ConfigProvider theme={lightTheme}>
      <QueryClientProvider client={queryClient}>
        <BrowserRouter>
          <Routes>
            <Route element={<AppShell />}>
              <Route index element={<Navigate to="/sessions" replace />} />
              <Route path="sessions" element={<SessionListPage />} />
              <Route path="sessions/new" element={<SessionCreatePage />} />
              <Route path="sessions/:sessionId" element={<SessionDetailPage />} />
              <Route path="plugins" element={<PluginBrowserPage />} />
              <Route path="settings" element={<SettingsPage />} />
            </Route>
          </Routes>
        </BrowserRouter>
      </QueryClientProvider>
    </ConfigProvider>
  );
}
```

`src/components/AppShell.tsx`:
```tsx
import { Layout, Menu } from "antd";
import { Link, Outlet, useLocation } from "react-router-dom";

const { Sider, Content, Header } = Layout;

export default function AppShell() {
  const location = useLocation();
  const selectedKey = location.pathname.split("/")[1] || "sessions";

  return (
    <Layout style={{ minHeight: "100vh" }}>
      <Sider collapsible>
        <div style={{ color: "white", padding: 16, fontWeight: 700 }}>
          🔬 AgentLabX
        </div>
        <Menu
          theme="dark"
          mode="inline"
          selectedKeys={[selectedKey]}
          items={[
            { key: "sessions", label: <Link to="/sessions">Sessions</Link> },
            { key: "plugins", label: <Link to="/plugins">Plugins</Link> },
            { key: "settings", label: <Link to="/settings">Settings</Link> },
          ]}
        />
      </Sider>
      <Layout>
        <Header style={{ background: "#fff", padding: "0 24px" }}>
          <h1 style={{ margin: 0, fontSize: 18 }}>AgentLabX</h1>
        </Header>
        <Content style={{ padding: 24 }}>
          <Outlet />
        </Content>
      </Layout>
    </Layout>
  );
}
```

Create stub pages that just render a Typography title so routing compiles.

Tests verify routing renders the correct shell.

Commit: `feat(web): add App shell, routing, Ant Design theme, and provider setup`

---

### Task 6: Session List Page (Dashboard)

**Files:**
- `web/src/pages/SessionListPage.tsx`
- `web/src/hooks/useSessions.ts`
- `web/src/components/common/StatusBadge.tsx`
- `web/tests/pages/SessionListPage.test.tsx`

Shows all sessions in an Ant Design Table with:
- Topic
- Status (StatusBadge with color: created=gray, running=blue, paused=amber, completed=green, failed=red)
- Current stage
- Iteration count
- Cost
- Action buttons (View, Delete)

Top bar: "New Session" primary button + user filter dropdown.

`useSessions` TanStack Query hook:
```typescript
import { useQuery } from "@tanstack/react-query";
import { api } from "../api/client";

export function useSessions(userId?: string) {
  return useQuery({
    queryKey: ["sessions", userId],
    queryFn: () => api.listSessions(userId),
    refetchInterval: 3000,  // Poll for session status updates
  });
}
```

Tests with MSW mock backend — render the page, assert rows appear, clicking row navigates.

Commit: `feat(web): add session list page with status badges and polling`

---

### Task 7: Session Create Wizard

**Files:**
- `web/src/pages/SessionCreatePage.tsx`
- `web/tests/pages/SessionCreatePage.test.tsx`

Multi-step Ant Design `Steps` wizard:
1. **Topic** — research topic (required)
2. **LLM configuration** — model override, cost ceiling
3. **Pipeline configuration** — skip stages checkboxes, iteration limits
4. **Agent selection** — multi-select from available agents (from `/api/plugins`)
5. **Stage controls** — per-stage select: auto/notify/approve/edit + mode (auto/HITL)
6. **Review** — show JSON preview of the POST body, then submit

On submit: POST `/api/sessions` with the constructed config, then navigate to `/sessions/{id}`.

Use `useMutation` from TanStack Query for the POST; invalidate the sessions list query on success.

Commit: `feat(web): add session creation wizard with multi-step config`

---

### Task 8: Session Detail Page Layout

**Files:**
- `web/src/pages/SessionDetailPage.tsx`
- `web/src/hooks/useSession.ts`
- `web/src/hooks/useWebSocket.ts`
- `web/tests/pages/SessionDetailPage.test.tsx`

3-panel layout with Ant Design Layout + Tabs:
- **Left (Sider, 260px)** — pipeline progress tracker (Task 9 renders content) + ControlBar (Task 12)
- **Center (Content)** — Tabs: Agent Activity (Task 10) | Artifacts (Task 11) | Pipeline Graph (Task 9) | Cost (Task 13)
- **Right (Sider, 280px)** — current stage output summary + PI agent assessment + CostTracker gauge (Task 13)
- **Bottom (sticky)** — FeedbackInput (Task 13)

`useSession`:
```typescript
export function useSession(sessionId: string) {
  return useQuery({
    queryKey: ["session", sessionId],
    queryFn: () => api.getSession(sessionId),
    refetchInterval: 2000,
    enabled: !!sessionId,
  });
}
```

`useWebSocket`:
```typescript
export function useWebSocket(sessionId: string) {
  const appendEvent = useWSStore((s) => s.appendEvent);
  useEffect(() => {
    if (!sessionId) return;
    const ws = new SessionWebSocket(sessionId);
    const unsub = ws.onEvent((event) => appendEvent(sessionId, event));
    ws.connect();
    return () => {
      unsub();
      ws.disconnect();
    };
  }, [sessionId, appendEvent]);
}
```

Tests: render with mock session data, verify panels render, verify WS hook attaches.

Commit: `feat(web): add session detail page with 3-panel layout`

---

### Task 9: Pipeline Graph Visualization

**Files:**
- `web/src/components/session/PipelineGraph.tsx`
- `web/tests/components/PipelineGraph.test.tsx`

React Flow node-link graph of the pipeline:
- 8 stage nodes positioned in a zone-based layout (per spec §3 — Discovery, Implementation, Synthesis zones)
- Edges showing `default_sequence` order
- Animated edge highlighting current stage (pulsing border)
- Completed stages: green fill
- Backtracks: dashed red edges from current_stage to target
- Click a node → panel opens with stage's output

Data source: `useTransitions(sessionId)` hook calling `/api/sessions/{id}/transitions`.

Use `@xyflow/react`:
```tsx
import { ReactFlow, Background, Controls } from "@xyflow/react";
import "@xyflow/react/dist/style.css";

export function PipelineGraph({ sessionId }: { sessionId: string }) {
  const { data } = useTransitions(sessionId);
  const nodes = buildNodes(data);
  const edges = buildEdges(data);
  return (
    <div style={{ width: "100%", height: 500 }}>
      <ReactFlow nodes={nodes} edges={edges} fitView>
        <Background />
        <Controls />
      </ReactFlow>
    </div>
  );
}
```

Tests verify graph renders with default 8 stages, active stage shows pulse class, backtrack edges appear when state has backtracks.

Commit: `feat(web): add pipeline graph with React Flow zone-based layout`

---

### Task 10: Agent Activity Feed

**Files:**
- `web/src/components/session/AgentActivityFeed.tsx`
- `web/tests/components/AgentActivityFeed.test.tsx`

Real-time event feed showing WS events:
- stage_started → "▶ Stage lit_review started"
- stage_completed → "✓ Stage lit_review completed (3 papers found)"
- stage_failed → "✗ Stage experimentation failed: TypeError ..."
- agent_thinking / agent_tool_call / agent_dialogue — once these land in a later plan, they'll stream in here too.

Render as an Ant Design `List` in virtual-scroll mode (use `rc-virtual-list` via Ant Design's built-in), newest at the top, auto-scroll to top on new events unless user has scrolled.

Source: `useWSStore((s) => s.events[sessionId])`.

Tests: inject fake events into the store, verify they render with correct icons and timestamps.

Commit: `feat(web): add real-time agent activity feed from WebSocket events`

---

### Task 11: Stage Output Panel + Hypothesis Tracker

**Files:**
- `web/src/components/session/StageOutputPanel.tsx`
- `web/src/components/session/HypothesisTracker.tsx`
- `web/src/hooks/useArtifacts.ts`
- `web/src/hooks/useHypotheses.ts`
- `web/tests/components/StageOutputPanel.test.tsx`

**StageOutputPanel:** Ant Design Tabs, one per stage output type (Literature Review | Plan | Data Exploration | Dataset Code | Experiments | Interpretation | Report | Review). Each tab shows the latest entry with version navigation (prev/next buttons when there are multiple).

For each artifact type render appropriately:
- LitReviewResult → Table of papers + collapsible summary
- ResearchPlan → Goals list + methodology paragraph + hypotheses list
- ExperimentResult → metrics Card grid + reproducibility details (collapsible)
- ReportResult → LaTeX source in a `<pre>` block with copy button
- ReviewResult → scores table + decision badge + feedback text

**HypothesisTracker:** Card list showing each hypothesis with:
- Status badge (active=blue, supported=green, refuted=red, abandoned=gray)
- Statement text
- Evidence links (click to jump to experiment)

Uses `active_hypotheses` via `/api/sessions/{id}/hypotheses` (backend already applies helper).

Commit: `feat(web): add stage output panel and hypothesis tracker`

---

### Task 12: ControlBar + FeedbackInput

**Files:**
- `web/src/components/session/ControlBar.tsx`
- `web/src/components/session/FeedbackInput.tsx`
- `web/tests/components/ControlBar.test.tsx`

**ControlBar** — vertical stack in the left sidebar:
- Status badge (via StatusBadge)
- Start button (visible when created)
- Pause button (visible when running)
- Resume button (visible when paused)
- Mode toggle (Segmented): Auto / HITL — calls `/preferences` PATCH
- Per-stage controls: a small grid, each stage row with a 4-value Segmented: auto / notify / approve / edit
- Backtrack control: Segmented auto / notify / approve
- "Redirect..." button → opens a modal with stage selector + reason field → POST `/redirect`

Actions use `useMutation` and invalidate session query on success.

**FeedbackInput** — sticky bottom bar with TextArea + Send button. Sends `{action: "inject_feedback", content}` via the WS.

Tests: click pause → mutation fires; select redirect target → confirmation → POST fires; mode toggle → PATCH fires.

Commit: `feat(web): add control bar and feedback input with live actions`

---

### Task 13: CostTracker + CheckpointModal

**Files:**
- `web/src/components/session/CostTracker.tsx`
- `web/src/components/session/CheckpointModal.tsx`
- `web/src/hooks/useCost.ts`
- `web/tests/components/CostTracker.test.tsx`

**CostTracker:**
- Ant Design `Statistic` for total_cost, total_tokens_in, total_tokens_out
- `@ant-design/plots` Gauge showing cost / cost_ceiling as a percentage (warning at 70%, critical at 90%)
- Time series chart: cost over time (track in wsStore if cost_update events arrive — for now, poll `/cost` every 3s)

**CheckpointModal:**
- Opens on `checkpoint_reached` WS event
- Shows PI agent's recommendation, stage output preview, and three buttons: Approve / Edit / Redirect
- Approve → send `{action: "approve"}` via WS
- Edit → open a nested form with the stage output, Save sends `{action: "edit", content}`
- Redirect → opens the redirect modal (reuse ControlBar's redirect dialog)

Note: server-side handling for `approve`/`edit` is deferred per Plan 4. The modal ships the UI; the backend will route these to real HITL interrupts in a later plan.

Commit: `feat(web): add cost tracker gauge and checkpoint approval modal`

---

### Task 14: Plugin Browser + Settings Pages

**Files:**
- `web/src/pages/PluginBrowserPage.tsx`
- `web/src/pages/SettingsPage.tsx`
- `web/src/components/plugins/PluginList.tsx`
- `web/tests/pages/PluginBrowserPage.test.tsx`

**PluginBrowserPage:** Tabs for Agents / Stages / Tools / Providers. Each tab is a table with name + description (pulled from plugin list). Clicking a row expands to show full schema / memory scope / config (if the backend exposes it — MVP: just names, expand in future plans).

Uses `/api/plugins` (Plan 4 endpoint).

**SettingsPage:** Form with tabs for:
- LLM defaults (default_model, temperature, max_retries, cost_ceiling)
- Execution backend (subprocess / docker radio + timeout)
- Storage (backend display only — SQLite path shown read-only)
- Budget policy (warning/critical/hard_ceiling thresholds)

Settings changes post to a future `/api/settings` endpoint — for Plan 5 just render the form and show "Coming soon" toast on save. This gives users the UI shape; persistence lands in a later plan.

Commit: `feat(web): add plugin browser and settings pages`

---

### Task 15: FastAPI Static File Serving

**Files:**
- `agentlabx/server/static.py`
- Update: `agentlabx/server/app.py`
- Update: `agentlabx/cli/main.py` (optionally add `--web-dir` flag)
- Create: `tests/server/test_static.py`

Mount the built React bundle at `/` so `agentlabx serve` delivers the UI without a separate server.

`agentlabx/server/static.py`:
```python
"""Serve the built React SPA from web/dist."""

from __future__ import annotations

import logging
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

logger = logging.getLogger(__name__)


def mount_spa(app: FastAPI, web_dist: Path | None = None) -> None:
    """Mount the built React bundle at /.

    If web_dist is None, auto-detect at <repo_root>/web/dist. If the directory
    does not exist (no build has been run), skip the mount with a warning so
    the API-only mode still works.

    SPA routing: unknown paths under / that are not API/WS should serve index.html
    so React Router can handle them client-side.
    """
    if web_dist is None:
        web_dist = Path(__file__).resolve().parents[2] / "web" / "dist"
    if not web_dist.exists() or not (web_dist / "index.html").exists():
        logger.info("No web/dist found at %s — running API-only.", web_dist)
        return

    # Static assets (JS/CSS/images) under /assets/
    app.mount("/assets", StaticFiles(directory=web_dist / "assets"), name="assets")

    # Root-level files (favicon.svg, index.html)
    @app.get("/favicon.svg", include_in_schema=False)
    async def favicon() -> FileResponse:
        return FileResponse(web_dist / "favicon.svg")

    @app.get("/", include_in_schema=False)
    async def spa_root() -> FileResponse:
        return FileResponse(web_dist / "index.html")

    # Catch-all for SPA routes (sessions, plugins, settings, etc.)
    # Must be LAST so API routes take precedence.
    @app.get("/{full_path:path}", include_in_schema=False)
    async def spa_catchall(request: Request, full_path: str) -> FileResponse:
        # Skip paths that would conflict with API/WS — those are caught by earlier routers
        if full_path.startswith(("api/", "ws/", "assets/", "openapi.json", "docs", "redoc")):
            # Let FastAPI's 404 handler take it
            from fastapi import HTTPException
            raise HTTPException(status_code=404)
        return FileResponse(web_dist / "index.html")
```

Update `app.py` to call `mount_spa(app)` AT THE END of `create_app` (after all API/WS routers, because catchall must be last):

```python
# At the very end of create_app, after all router includes:
from agentlabx.server.static import mount_spa
mount_spa(app)
```

Tests (`tests/server/test_static.py`):
- Build a fake `dist/` in tmp_path with an `index.html`, pass it via `mount_spa(app, web_dist=...)`
- Verify GET `/` returns the index content
- Verify GET `/sessions/abc` (unknown SPA route) also returns index content
- Verify GET `/api/sessions` still returns JSON (API takes precedence)
- Verify GET `/openapi.json` still works
- Verify without dist present, health endpoint still works

Commit: `feat(server): serve built React SPA from web/dist via static mount`

---

### Task 16: Vitest Configuration + Final Test Pass

**Files:**
- `web/tests/setup.ts` (finalize)
- `web/.eslintrc.cjs` (or `eslint.config.js`)
- Update: Python lint + test commands to cover the web/ build

- [ ] **Step 1: MSW setup for integration tests**

`web/tests/mocks/handlers.ts`:
```typescript
import { http, HttpResponse } from "msw";

export const handlers = [
  http.get("/api/sessions", () => HttpResponse.json([])),
  http.post("/api/sessions", async ({ request }) => {
    const body = (await request.json()) as { topic: string };
    return HttpResponse.json(
      {
        session_id: "sess-test",
        user_id: "default",
        research_topic: body.topic,
        status: "created",
        preferences: { mode: "auto", stage_controls: {}, backtrack_control: "auto" },
        config_overrides: {},
      },
      { status: 201 },
    );
  }),
  http.get("/api/plugins", () =>
    HttpResponse.json({
      agent: ["phd_student", "postdoc"],
      stage: ["literature_review"],
      tool: ["arxiv_search"],
      llm_provider: [],
      execution_backend: [],
      storage_backend: [],
      code_agent: [],
    }),
  ),
];
```

`web/tests/mocks/server.ts`:
```typescript
import { setupServer } from "msw/node";
import { handlers } from "./handlers";
export const server = setupServer(...handlers);
```

`web/tests/setup.ts`:
```typescript
import "@testing-library/jest-dom/vitest";
import { afterAll, afterEach, beforeAll } from "vitest";
import { server } from "./mocks/server";

beforeAll(() => server.listen({ onUnhandledRequest: "warn" }));
afterEach(() => server.resetHandlers());
afterAll(() => server.close());
```

- [ ] **Step 2: ESLint flat config**

`web/eslint.config.js`:
```js
import js from "@eslint/js";
import tseslint from "typescript-eslint";
import react from "eslint-plugin-react";
import reactHooks from "eslint-plugin-react-hooks";

export default [
  js.configs.recommended,
  ...tseslint.configs.recommended,
  {
    files: ["src/**/*.{ts,tsx}"],
    plugins: { react, "react-hooks": reactHooks },
    rules: {
      "react-hooks/rules-of-hooks": "error",
      "react-hooks/exhaustive-deps": "warn",
      "@typescript-eslint/no-unused-vars": ["error", { argsIgnorePattern: "^_" }],
    },
  },
  { ignores: ["dist/**", "src/api/generated.ts"] },
];
```

Add ESLint deps to package.json:
```json
"@eslint/js": "^9.0.0",
"eslint": "^9.0.0",
"eslint-plugin-react": "^7.35.0",
"eslint-plugin-react-hooks": "^5.0.0",
"typescript-eslint": "^8.0.0"
```

- [ ] **Step 3: Run everything**

```bash
cd web
npm run typecheck
npm run lint
npm test -- --run
npm run build
```

- [ ] **Step 4: Verify end-to-end in a browser**

```bash
# Terminal 1
uv run agentlabx serve --mock-llm

# Terminal 2
cd web && npm run dev
```

Open http://localhost:5173 — should show the dashboard. Create a session, start it, watch WS events stream in the activity feed, wait for completion.

Alternative prod mode:
```bash
cd web && npm run build
uv run agentlabx serve --mock-llm
# Open http://localhost:8000 — full SPA served from FastAPI
```

- [ ] **Step 5: Commit**

```bash
git add web/tests web/eslint.config.js web/package.json
git commit -m "test(web): add Vitest setup with MSW and ESLint flat config"
```

---

## Summary

After completing all 16 tasks:

**Frontend scaffolding:**
- Vite + React 19 + TypeScript + Ant Design 5 + Zustand + TanStack Query + React Flow
- OpenAPI-driven typed REST client (no hand-written DTOs)
- WebSocket service with auto-reconnect
- Vitest + MSW + Testing Library + ESLint flat config

**Pages:**
- Session List (Dashboard) with polling and status badges
- Session Create wizard (multi-step config)
- Session Detail with 3-panel layout + live WS stream
- Plugin Browser
- Settings (form shell — persistence deferred)

**Session Detail components:**
- PipelineGraph (React Flow, zone-based, active/backtrack highlighting)
- AgentActivityFeed (WS-driven virtual list)
- StageOutputPanel (tabbed per-stage artifacts)
- HypothesisTracker (status badges + evidence links)
- ControlBar (mode/stage/backtrack controls + pause/resume/redirect)
- FeedbackInput (WS inject_feedback)
- CostTracker (Statistic + Gauge + time series)
- CheckpointModal (approve/edit/redirect UI — backend handling deferred)

**Integration:**
- Vite dev server proxies `/api` and `/ws` to FastAPI during development
- FastAPI serves built `web/dist` at `/` in production via `mount_spa`
- `agentlabx serve` delivers complete UX when the build is present
- `openapi.json` source-of-truth means backend changes automatically flow into frontend types on next `npm run codegen`

**What this enables:**
- A researcher can create a session in the browser, watch it execute live, pause it, redirect the pipeline, and view artifacts — all without touching the CLI or API directly.

**What's deferred (post-Plan 5):**
- OAuth/JWT login flow (no login screen — single-user mode)
- Real-time LLM token streaming in AgentActivityFeed (requires backend agent_thinking events)
- Full HITL interrupt flow (approve/edit modal UI ships as observable — records action but backend execution lands later; see Fix B)
- PostgreSQL + MinIO migration (architecture supports it, no UI changes needed)
- Session sharing / export / archive UI
- Dark mode toggle (theme config exists; add UI switch)
- i18n
- Mobile-responsive layouts (desktop-only in Plan 5)

---

## Addendum: Review Fixes (apply during execution)

Fourteen issues surfaced during review. Fixes are grouped by severity; apply
to the specific tasks noted.

### CRITICAL

**Fix A (Task 0 — new, apply before Task 6): DELETE /api/sessions/{id} endpoint**

Plan 4 didn't ship a delete endpoint and Plan 5 Task 6 assumed one. Backport
a simple DELETE to Plan 4 as a prerequisite task for Plan 5 execution.

Add to `agentlabx/server/routes/sessions.py`:

```python
@router.delete("/{session_id}", status_code=204)
async def delete_session(request: Request, session_id: str):
    """Remove a session from memory and storage. Cancels running task if active."""
    context = request.app.state.context
    manager = context.session_manager
    try:
        session = manager.get_session(session_id)
    except KeyError:
        raise HTTPException(status_code=404, detail="Session not found")

    # Cancel running task if any
    if context.executor is not None:
        running = context.executor.get_running(session_id)
        if running is not None:
            await context.executor.cancel_session(session_id)

    # Remove from in-memory registry
    manager._sessions.pop(session_id, None)

    # Remove persisted metadata (best-effort)
    if manager._storage is not None and hasattr(manager._storage, "delete_state"):
        try:
            await manager._storage.delete_state(session_id, "session_metadata")
        except Exception:
            pass

    return None  # 204 No Content
```

Add a `delete_state` method to `BaseStorageBackend` and `SQLiteBackend` — one
row DELETE matching session_id + stage. Write a basic test that creates a
session, DELETEs it, and verifies `/api/sessions/{id}` returns 404.

Plan 5 Task 6: add a Delete button with Ant Design `Popconfirm` — confirms
before firing `api.deleteSession(id)`, then invalidates the sessions list
query on success.

**Fix B (Task 13): CheckpointModal ships as "observable"**

The modal will ship with working UI but the backend won't execute the
approve/edit actions yet. Chosen strategy from the review's three options:
**observable — send WS action, backend logs, UI shows toast.**

Concrete behavior:
- Approve button → sends `{"action": "approve"}` via WS. On success, UI
  shows a subtle Ant Design `message.info("Action recorded. Full HITL
  execution ships in a later release.")` and dismisses the modal.
- Edit button → opens nested form with stage output. On save, sends
  `{"action": "edit", "content": "..."}` and shows same toast.
- Redirect button inside CheckpointModal → reuses the working redirect
  flow (POST /redirect is already functional).

The WS handler in Plan 4 already logs these actions via `logger.info`. The
user sees immediate feedback and doesn't experience a broken button. The
future HITL interrupt plan swaps the log line for real LangGraph interrupt
resume; the frontend doesn't change.

**Fix C (Plan 1 + Plan 4 backport): Event timestamp**

Add `timestamp: datetime` to `Event` model in `agentlabx/core/events.py`.
Default via `Field(default_factory=lambda: datetime.now(timezone.utc))` so
existing callers don't break. Update Plan 4's WS forwarder to include it:

```python
await self.event_forwarder(session.session_id, {
    "type": event.type,
    "data": event.data,
    "source": event.source,
    "timestamp": event.timestamp.isoformat(),
})
```

Plan 5 `PipelineEvent` type gains `timestamp?: string` (ISO-8601).
AgentActivityFeed uses this for consistent ordering — WS reconnect + buffered
events replay in the right order.

**Fix D (Task 3 + new WS provider): WebSocket singleton with refcount**

Plan 5 Task 3's `useWebSocket(sessionId)` opens a fresh connection per hook
call. Under React 19 StrictMode double-invocation this triples WS traffic;
with multiple components observing the same session, it explodes.

Replace the hook with a provider-based singleton:

```typescript
// web/src/api/wsRegistry.ts
import { SessionWebSocket } from "./ws";

interface Entry {
  socket: SessionWebSocket;
  refcount: number;
}

class WebSocketRegistry {
  private entries = new Map<string, Entry>();

  acquire(sessionId: string): SessionWebSocket {
    let entry = this.entries.get(sessionId);
    if (!entry) {
      const socket = new SessionWebSocket(sessionId);
      socket.connect();
      entry = { socket, refcount: 0 };
      this.entries.set(sessionId, entry);
    }
    entry.refcount += 1;
    return entry.socket;
  }

  release(sessionId: string): void {
    const entry = this.entries.get(sessionId);
    if (!entry) return;
    entry.refcount -= 1;
    if (entry.refcount <= 0) {
      entry.socket.disconnect();
      this.entries.delete(sessionId);
    }
  }
}

export const wsRegistry = new WebSocketRegistry();
```

`useWebSocket`:
```typescript
export function useWebSocket(sessionId: string) {
  const appendEvent = useWSStore((s) => s.appendEvent);
  const queryClient = useQueryClient();

  useEffect(() => {
    if (!sessionId) return;
    const socket = wsRegistry.acquire(sessionId);
    const unsubscribe = socket.onEvent((event) => {
      appendEvent(sessionId, event);
      // Fix H: invalidate relevant cache entries on state-changing events
      if (event.type === "stage_completed" || event.type === "stage_failed" || event.type === "transition") {
        queryClient.invalidateQueries({ queryKey: ["session", sessionId] });
        queryClient.invalidateQueries({ queryKey: ["artifacts", sessionId] });
        queryClient.invalidateQueries({ queryKey: ["transitions", sessionId] });
      }
      if (event.type === "cost_update") {
        queryClient.invalidateQueries({ queryKey: ["cost", sessionId] });
      }
    });
    return () => {
      unsubscribe();
      wsRegistry.release(sessionId);
    };
  }, [sessionId, appendEvent, queryClient]);
}
```

Multiple components calling `useWebSocket("sess-1")` now share one socket.
On last unmount, refcount hits zero and the socket closes. StrictMode's
double-invocation is safe because refcount handles it correctly (connect in
first render, second render bumps to 2, then first cleanup drops to 1, second
cleanup drops to 0 → disconnect).

### IMPORTANT

**Fix E (Task 4): Drop `activeSessionStore`**

TanStack Query already handles optimistic preference updates via `onMutate`
+ `onError` rollback. Keeping a parallel Zustand copy causes sync drift.

Revised store inventory:
- **Keep**: `wsStore` (event ring buffer — pure client state, not server data)
- **Keep**: `uiStore` (client-only UI state — active tab, sidebar collapsed,
  local filter text inputs, edit-mode toggles)
- **Drop**: `sessionsStore` — the list IS server data; use
  `useSessions(userId)` TanStack Query hook
- **Drop**: `activeSessionStore` — the active session id comes from URL
  params (`useParams<{sessionId: string}>()`) via React Router

Optimistic preference updates — example:
```typescript
const mutation = useMutation({
  mutationFn: (update: PreferencesUpdate) =>
    api.updatePreferences(sessionId, update),
  onMutate: async (update) => {
    await queryClient.cancelQueries({ queryKey: ["session", sessionId] });
    const previous = queryClient.getQueryData(["session", sessionId]);
    queryClient.setQueryData(["session", sessionId], (old: SessionDetail) => ({
      ...old,
      preferences: { ...old.preferences, ...update },
    }));
    return { previous };
  },
  onError: (_err, _update, ctx) => {
    if (ctx?.previous) {
      queryClient.setQueryData(["session", sessionId], ctx.previous);
    }
  },
  onSettled: () => {
    queryClient.invalidateQueries({ queryKey: ["session", sessionId] });
  },
});
```

**Fix F (Task 2): Switch to openapi-fetch**

Hand-rolled `Get<P>`/`Post<P>` types only handle 200 responses; Plan 4's
`/start`, `/pause`, `/resume`, `/redirect` all return 202. Also `/preferences`
is typed as `Promise<unknown>` due to a missed generic.

Replace the hand-rolled client with [openapi-fetch](https://openapi-ts.dev/openapi-fetch/)
(~3 KB runtime, same `openapi-typescript` ecosystem):

```bash
npm install openapi-fetch
```

```typescript
// web/src/api/client.ts
import createClient from "openapi-fetch";
import type { paths } from "./generated";

const client = createClient<paths>({ baseUrl: "" });

export const api = {
  async listSessions(userId?: string) {
    const { data, error } = await client.GET("/api/sessions", {
      params: { query: userId ? { user_id: userId } : {} },
    });
    if (error) throw error;
    return data;
  },
  async createSession(body: Body<"/api/sessions", "post">) {
    const { data, error } = await client.POST("/api/sessions", { body });
    if (error) throw error;
    return data;
  },
  // ... etc — openapi-fetch correctly infers 200/201/202 responses
};
```

Drop ~50 lines of type-helper boilerplate. Every endpoint's return type flows
from the generated schema automatically, including multi-status responses.

**Fix G (Task 1): Commit generated.ts, not ignore it**

Contradiction between Task 1 Step 5 (gitignore includes `src/api/generated.ts`)
and Task 2 Step 1 (commented "commit it"). Pick committing. Remove
`src/api/generated.ts` from `web/.gitignore`. Diffs of the generated file
are reviewable signals of backend API changes — useful in PRs.

**Fix H (Task 8): WS invalidates TanStack cache**

Implemented as part of Fix D above. Drop polling intervals from 2s to 15-30s
as backstop only — WS invalidation is the primary refresh channel.

Revised `useSession`:
```typescript
export function useSession(sessionId: string) {
  return useQuery({
    queryKey: ["session", sessionId],
    queryFn: () => api.getSession(sessionId),
    refetchInterval: 30_000, // Backstop — primary refresh via WS invalidation
    enabled: !!sessionId,
  });
}
```

### MEDIUM

**Fix I (Task 15): Simplify SPA catchall**

`startswith("docs")` matches `/documents` too. Rely on FastAPI route
precedence (real routes are registered first, so they take priority over the
catchall). Drop the defensive check:

```python
@app.get("/{full_path:path}", include_in_schema=False)
async def spa_catchall(request: Request, full_path: str) -> FileResponse:
    # No startswith filter — real API/WS/docs routes are registered earlier
    # and take precedence. Only unmatched paths reach here.
    return FileResponse(web_dist / "index.html")
```

If a real route raises 404 (e.g., `/api/sessions/nonexistent`), FastAPI's
handler runs before the catchall — the catchall never sees it.

### MINOR

**Fix J (Task 9): Limit backtrack edge rendering**

Render only the 3 most recent backtracks. Older ones fade to 20% opacity.
Add a toggle "Show all backtracks (N)" in the graph toolbar. Prevents
spaghetti graphs after many iterations.

**Fix K (Task 8): Document layout DOM structure**

Add to Task 8's implementation note:

```
Layout structure (outer → inner):
  <div flex-column 100vh>
    <Layout>  (AntD — has Sider + Content + Sider)
      <Sider left>  ControlBar, pipeline tracker
      <Content>     Tabs (Activity | Artifacts | Graph | Cost)
      <Sider right> Stage output summary, PI assessment, CostTracker gauge
    </Layout>
    <div sticky-bottom>  FeedbackInput  (spans full width)
  </div>
```

The AntD Layout doesn't trivially span a bottom bar across Sider + Content
columns. The outer flex column wrapping gives the sticky bottom its own row.

**Fix L (Task 5): Add error boundaries**

In `App.tsx`, wrap each route with an error boundary:

```typescript
import { Component, ErrorInfo, ReactNode } from "react";
import { Result, Button } from "antd";

class ErrorBoundary extends Component<
  { children: ReactNode; fallbackLabel?: string },
  { error: Error | null }
> {
  state = { error: null as Error | null };
  static getDerivedStateFromError(error: Error) { return { error }; }
  componentDidCatch(error: Error, info: ErrorInfo) {
    console.error("Route error:", error, info);
  }
  render() {
    if (this.state.error) {
      return (
        <Result
          status="error"
          title={this.props.fallbackLabel || "Something went wrong"}
          subTitle={this.state.error.message}
          extra={
            <Button type="primary" onClick={() => this.setState({ error: null })}>
              Retry
            </Button>
          }
        />
      );
    }
    return this.props.children;
  }
}
```

Wrap each `<Route element={...}>` children in `<ErrorBoundary>`. A single
component crash now scopes to its route instead of blanking the entire app.

**Fix M (Plan 5 prerequisites): React 19 + AntD 5 risk**

React 19 + AntD 5.22+ compatibility is stated but new. If Form components,
Select portals, or other features break during Task 5-8, pin to React 18.3:

```json
"react": "^18.3.0",
"react-dom": "^18.3.0",
"@types/react": "^18.3.0",
"@types/react-dom": "^18.3.0"
```

This is a ~5-minute downgrade. No code changes needed in the plan —
React 19's new features aren't used anywhere. Document the pin decision in
`web/README.md` if it triggers.

---

## Updated Summary

Plan 5 remains 16 numbered tasks. Addendum applies to specific tasks:

- **Task 0 (new, before Task 6)**: Backport DELETE endpoint to Plan 4 (Fix A).
- **Task 1**: Commit `generated.ts` (Fix G), React 19 risk note (Fix M).
- **Task 2**: Use `openapi-fetch` (Fix F).
- **Task 3**: Include `timestamp` in `PipelineEvent` (Fix C — requires Plan 1/4 backport too).
- **Task 4**: Drop `sessionsStore` + `activeSessionStore`; keep only `wsStore` + `uiStore` (Fix E).
- **Task 5**: Wrap routes in `ErrorBoundary` (Fix L).
- **Task 8**: Document layout DOM structure (Fix K), wire WS → TanStack invalidation via Fix D's singleton (Fix H).
- **Task 9**: Fade backtrack edges beyond N=3 (Fix J).
- **Task 13**: CheckpointModal as "observable" with toast (Fix B).
- **Task 15**: Drop catchall startswith guard (Fix I).
- **New**: `web/src/api/wsRegistry.ts` singleton with refcount (Fix D).

Backports required before Plan 5 execution:
- Add `timestamp` to `agentlabx/core/events.py::Event` (Plan 1 file, 1 line).
- Update Plan 4's WS forwarder to include timestamp in the broadcast payload
  (Plan 4 file, ~3 lines in `executor.py::start_session`).
- Add `DELETE /api/sessions/{id}` route + `delete_state` on storage backend
  (Plan 4 files).

These backports are small and can be applied as a single prep commit before
Plan 5 Task 1. Total effort: ~30 minutes.
