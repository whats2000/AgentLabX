import {
  Activity,
  FlaskConical,
  KeyRound,
  ListChecks,
  LogOut,
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
import i18n from "@/i18n"

function navClass(isActive: boolean): string {
  return (
    "flex items-center gap-2 rounded px-2 py-1.5 text-sm transition-colors " +
    (isActive
      ? "bg-slate-100 text-slate-900"
      : "text-slate-600 hover:bg-slate-50")
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
      <aside className="flex w-60 flex-col border-r bg-white">
        {/* Header — app branding */}
        <div className="flex items-center gap-2 px-4 py-4 border-b">
          <FlaskConical className="h-5 w-5 text-slate-700" />
          <span className="text-sm font-semibold text-slate-800">{t("nav.appName")}</span>
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
              <NavLink
                to="/admin/activity"
                className={({ isActive }) => navClass(isActive)}
              >
                <Activity className="h-4 w-4" /> {t("nav.activity")}
              </NavLink>
            </>
          )}
        </nav>

        {/* Bottom: user button + popup */}
        <div className="border-t p-2">
          <DropdownMenu>
            <DropdownMenuTrigger asChild>
              <button
                type="button"
                className="flex w-full items-center gap-3 rounded px-2 py-2 text-left hover:bg-slate-50 focus:outline-none focus-visible:ring-2 focus-visible:ring-slate-300"
              >
                <span className="flex h-8 w-8 items-center justify-center rounded-full bg-slate-900 text-xs font-medium text-white">
                  {initial}
                </span>
                <span className="flex-1 overflow-hidden">
                  <span className="block truncate text-sm font-medium text-slate-800">
                    {identity.display_name}
                  </span>
                  <span className="block truncate text-xs text-slate-400">
                    {identity.email}
                  </span>
                </span>
              </button>
            </DropdownMenuTrigger>
            <DropdownMenuContent side="top" align="start" className="w-56">
              <DropdownMenuLabel>{identity.email}</DropdownMenuLabel>
              <DropdownMenuSeparator />
              <DropdownMenuItem onSelect={() => { nav("/profile") }}>
                <User className="h-4 w-4" /> {t("nav.profile")}
              </DropdownMenuItem>
              <DropdownMenuItem onSelect={() => { nav("/settings") }}>
                <KeyRound className="h-4 w-4" /> {t("nav.credentials")}
              </DropdownMenuItem>
              <DropdownMenuSeparator />
              <DropdownMenuLabel>{t("nav.language")}</DropdownMenuLabel>
              <DropdownMenuItem onSelect={() => { void i18n.changeLanguage("en") }}>
                English {i18n.language === "en" ? "✓" : ""}
              </DropdownMenuItem>
              <DropdownMenuItem onSelect={() => { void i18n.changeLanguage("zh-TW") }}>
                繁體中文 {i18n.language.startsWith("zh") ? "✓" : ""}
              </DropdownMenuItem>
              <DropdownMenuSeparator />
              <DropdownMenuItem
                onSelect={() => { void logout() }}
                className="text-red-600 focus:bg-red-50 focus:text-red-700"
              >
                <LogOut className="h-4 w-4" /> {t("nav.logout")}
              </DropdownMenuItem>
            </DropdownMenuContent>
          </DropdownMenu>
        </div>
      </aside>

      <main className="flex-1 overflow-auto bg-slate-50 p-8">
        <Outlet />
      </main>
    </div>
  )
}
