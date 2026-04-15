import { KeyRound, ListChecks, Users } from "lucide-react"
import * as React from "react"
import { NavLink, Outlet } from "react-router-dom"

import { useAuth } from "@/auth/AuthProvider"
import { Button } from "@/components/ui/button"

export function Layout(): React.JSX.Element {
  const { identity, refresh } = useAuth()
  if (!identity) return <Outlet />

  return (
    <div className="flex h-full">
      <aside className="w-60 border-r bg-white p-4 space-y-1">
        <div className="px-2 pb-4">
          <div className="text-sm font-medium text-slate-700">{identity.display_name}</div>
          <div className="text-xs text-slate-400">{identity.email}</div>
        </div>
        <NavLink to="/settings" className={({ isActive }) => navClass(isActive)}>
          <KeyRound className="h-4 w-4" /> Credentials
        </NavLink>
        {identity.capabilities.includes("admin") && (
          <NavLink to="/admin" className={({ isActive }) => navClass(isActive)}>
            <Users className="h-4 w-4" /> Admin users
          </NavLink>
        )}
        <NavLink to="/runs" className={({ isActive }) => navClass(isActive)}>
          <ListChecks className="h-4 w-4" /> Runs
        </NavLink>
        <div className="pt-6">
          <Button
            variant="outline"
            onClick={() => {
              void fetch("/api/auth/logout", { method: "POST", credentials: "include" }).then(
                () => { refresh() }
              )
            }}
          >
            Log out
          </Button>
        </div>
      </aside>
      <main className="flex-1 overflow-auto p-8">
        <Outlet />
      </main>
    </div>
  )
}

function navClass(isActive: boolean): string {
  return (
    "flex items-center gap-2 rounded px-2 py-1.5 text-sm " +
    (isActive ? "bg-slate-100 text-slate-900" : "text-slate-600 hover:bg-slate-50")
  )
}
