import {
  Activity,
  FlaskConical,
  KeyRound,
  ListChecks,
  LogOut,
  Settings,
  User,
  Users,
} from "lucide-react"
import * as React from "react"
import { useTranslation } from "react-i18next"
import { NavLink, Outlet, useNavigate } from "react-router-dom"
import { toast } from "sonner"

import { useAuth } from "@/auth/AuthProvider"
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu"

function navClass(isActive: boolean): string {
  return (
    "flex items-center gap-2 rounded px-2 py-1.5 text-sm transition-colors " +
    (isActive
      ? "bg-sidebar-active text-sidebar-foreground"
      : "text-muted-foreground hover:bg-sidebar-hover hover:text-sidebar-foreground")
  )
}

export function Layout(): React.JSX.Element {
  const { t } = useTranslation()
  const { identity, refresh } = useAuth()
  const nav = useNavigate()

  if (!identity) return <Outlet />

  const initial = identity.display_name.trim().charAt(0).toUpperCase() || "?"

  async function logout(): Promise<void> {
    try {
      await fetch("/api/auth/logout", { method: "POST", credentials: "include" })
      await refresh()
      toast.success(t("logout.success"))
      nav("/login")
    } catch {
      toast.error(t("logout.failed"))
    }
  }

  return (
    <div className="flex h-full">
      <aside className="flex w-60 flex-col border-r border-sidebar-border bg-sidebar">
        {/* Header — app branding */}
        <div className="flex items-center gap-2 px-4 py-4 border-b border-sidebar-border">
          <FlaskConical className="h-5 w-5 text-sidebar-foreground" />
          <span className="text-sm font-semibold text-sidebar-foreground">{t("nav.appName")}</span>
        </div>

        {/* Primary nav */}
        <nav className="flex-1 overflow-auto p-2 space-y-1">
          <NavLink to="/runs" className={({ isActive }) => navClass(isActive)}>
            <ListChecks className="h-4 w-4" /> {t("nav.runs")}
          </NavLink>
          {identity.capabilities.includes("admin") && (
            <>
              <NavLink to="/admin" className={({ isActive }) => navClass(isActive)}>
                <Users className="h-4 w-4" /> {t("nav.adminUsers")}
              </NavLink>
              <NavLink to="/admin/activity" className={({ isActive }) => navClass(isActive)}>
                <Activity className="h-4 w-4" /> {t("nav.activity")}
              </NavLink>
            </>
          )}
        </nav>

        {/* Bottom: user button + popup */}
        <div className="border-t border-sidebar-border p-2">
          <DropdownMenu>
            <DropdownMenuTrigger asChild>
              <button
                type="button"
                className="flex w-full items-center gap-3 rounded px-2 py-2 text-left hover:bg-sidebar-hover focus:outline-none focus-visible:ring-2 focus-visible:ring-ring"
              >
                <span className="flex h-8 w-8 items-center justify-center rounded-full bg-foreground text-xs font-medium text-background">
                  {initial}
                </span>
                <span className="flex-1 overflow-hidden">
                  <span className="block truncate text-sm font-medium text-sidebar-foreground">
                    {identity.display_name}
                  </span>
                  <span className="block truncate text-xs text-muted-foreground">
                    {identity.email}
                  </span>
                </span>
              </button>
            </DropdownMenuTrigger>
            <DropdownMenuContent side="top" align="start" className="w-56">
              <DropdownMenuLabel>{identity.email}</DropdownMenuLabel>
              <DropdownMenuSeparator />
              <DropdownMenuItem
                onSelect={() => {
                  nav("/profile")
                }}
              >
                <User className="h-4 w-4" /> {t("nav.profile")}
              </DropdownMenuItem>
              <DropdownMenuItem
                onSelect={() => {
                  nav("/settings")
                }}
              >
                <KeyRound className="h-4 w-4" /> {t("nav.credentials")}
              </DropdownMenuItem>
              <DropdownMenuItem
                onSelect={() => {
                  nav("/preferences")
                }}
              >
                <Settings className="h-4 w-4" /> {t("preferences.title")}
              </DropdownMenuItem>
              <DropdownMenuSeparator />
              <DropdownMenuItem
                onSelect={() => {
                  void logout()
                }}
                className="text-red-600 focus:bg-red-50 focus:text-red-700"
              >
                <LogOut className="h-4 w-4" /> {t("nav.logout")}
              </DropdownMenuItem>
            </DropdownMenuContent>
          </DropdownMenu>
        </div>
      </aside>

      <main className="flex-1 overflow-auto bg-background p-8">
        <Outlet />
      </main>
    </div>
  )
}
