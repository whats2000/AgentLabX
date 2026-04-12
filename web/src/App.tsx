import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { ConfigProvider } from "antd";
import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom";
import AppShell from "./components/AppShell";
import { ErrorBoundary } from "./components/common/ErrorBoundary";
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
              <Route
                path="sessions"
                element={
                  <ErrorBoundary fallbackLabel="Session list failed">
                    <SessionListPage />
                  </ErrorBoundary>
                }
              />
              <Route
                path="sessions/new"
                element={
                  <ErrorBoundary fallbackLabel="Create session failed">
                    <SessionCreatePage />
                  </ErrorBoundary>
                }
              />
              <Route
                path="sessions/:sessionId"
                element={
                  <ErrorBoundary fallbackLabel="Session detail failed">
                    <SessionDetailPage />
                  </ErrorBoundary>
                }
              />
              <Route
                path="plugins"
                element={
                  <ErrorBoundary fallbackLabel="Plugins failed">
                    <PluginBrowserPage />
                  </ErrorBoundary>
                }
              />
              <Route
                path="settings"
                element={
                  <ErrorBoundary fallbackLabel="Settings failed">
                    <SettingsPage />
                  </ErrorBoundary>
                }
              />
            </Route>
          </Routes>
        </BrowserRouter>
      </QueryClientProvider>
    </ConfigProvider>
  );
}
