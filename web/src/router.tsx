import * as React from "react"
import { createBrowserRouter, Navigate } from "react-router-dom"

import { AuthProvider, useAuth } from "@/auth/AuthProvider"
import { LoginPage } from "@/auth/LoginPage"
import { Layout } from "@/components/Layout"
import { AdminActivityPage } from "@/pages/AdminActivityPage"
import { AdminPage } from "@/pages/AdminPage"
import { RunsPage } from "@/pages/RunsPage"
import { SettingsPage } from "@/pages/SettingsPage"

function RequireAuth({ children }: { children: React.JSX.Element }): React.JSX.Element {
  const { identity, isLoading } = useAuth()
  if (isLoading) return <div className="p-8 text-sm text-slate-500">Loading…</div>
  if (!identity) return <Navigate to="/login" replace />
  return children
}

function RequireAdmin({ children }: { children: React.JSX.Element }): React.JSX.Element {
  const { identity } = useAuth()
  if (!identity) return <Navigate to="/login" replace />
  if (!identity.capabilities.includes("admin"))
    return <Navigate to="/settings" replace />
  return children
}

export const router = createBrowserRouter([
  {
    path: "/",
    element: (
      <AuthProvider>
        <Layout />
      </AuthProvider>
    ),
    children: [
      { index: true, element: <Navigate to="/settings" replace /> },
      { path: "login", element: <LoginPage /> },
      { path: "settings", element: <RequireAuth><SettingsPage /></RequireAuth> },
      { path: "admin", element: <RequireAdmin><AdminPage /></RequireAdmin> },
      { path: "admin/activity", element: <RequireAdmin><AdminActivityPage /></RequireAdmin> },
      { path: "runs", element: <RequireAuth><RunsPage /></RequireAuth> },
    ],
  },
])
