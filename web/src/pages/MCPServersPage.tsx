import { useQuery } from "@tanstack/react-query"
import { Plus, RefreshCw } from "lucide-react"
import * as React from "react"
import { useTranslation } from "react-i18next"

import { api, type MCPServerDto } from "@/api/client"
import { useAuth } from "@/auth/AuthProvider"
import { MCPServerCard } from "@/components/mcp/MCPServerCard"
import { RegisterMCPServerForm } from "@/components/mcp/RegisterMCPServerForm"
import { Button } from "@/components/ui/button"

function sortServers(rows: MCPServerDto[]): MCPServerDto[] {
  return [...rows].sort((a, b) => {
    if (a.scope !== b.scope) return a.scope === "admin" ? -1 : 1
    return a.name.localeCompare(b.name)
  })
}

export function MCPServersPage(): React.JSX.Element {
  const { t } = useTranslation()
  const { identity } = useAuth()
  const [showRegister, setShowRegister] = React.useState(false)
  // hasOpened defers the form's first mount until the user actually clicks
  // "Register" — otherwise every page load would pay the mount cost of a
  // form most visits never touch. After the first open it stays mounted
  // across open/close cycles so the drawer can animate both directions and
  // in-progress inputs survive an accidental close.
  const [hasOpened, setHasOpened] = React.useState(false)

  const servers = useQuery<MCPServerDto[]>({
    queryKey: ["mcp-servers"],
    queryFn: api.listMCPServers,
    refetchOnWindowFocus: true,
  })

  const isAdmin = identity?.capabilities.includes("admin") ?? false
  const rows = sortServers(servers.data ?? [])

  return (
    <div className="max-w-5xl space-y-6">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="space-y-1">
          <h1 className="text-2xl font-semibold">{t("mcp.title")}</h1>
          <p className="text-sm text-muted-foreground">{t("mcp.intro")}</p>
        </div>
        <div className="flex gap-2">
          <Button
            type="button"
            variant="outline"
            onClick={() => {
              void servers.refetch()
            }}
            disabled={servers.isFetching}
          >
            <RefreshCw className={servers.isFetching ? "h-4 w-4 animate-spin" : "h-4 w-4"} />
            {t("mcp.refresh")}
          </Button>
          <Button
            type="button"
            onClick={() => {
              setShowRegister((v) => {
                if (!v) setHasOpened(true)
                return !v
              })
            }}
          >
            <Plus className="h-4 w-4" />
            {showRegister ? t("mcp.hideRegister") : t("mcp.register")}
          </Button>
        </div>
      </div>

      <div
        className={
          "grid transition-[grid-template-rows,opacity,margin] duration-300 ease-out-snap " +
          (showRegister ? "grid-rows-[1fr] opacity-100" : "-mt-6 grid-rows-[0fr] opacity-0")
        }
        // inert (not aria-hidden) so the browser moves focus out of the
        // collapsing form. aria-hidden on a focused subtree is an a11y
        // violation Chrome flags loudly; inert hides from AT *and*
        // suppresses focus, which is what we want here.
        inert={!showRegister}
      >
        <div className="min-h-0 overflow-hidden">
          {hasOpened ? (
            <RegisterMCPServerForm
              isAdmin={isAdmin}
              onClose={() => {
                setShowRegister(false)
              }}
            />
          ) : null}
        </div>
      </div>

      {servers.isLoading ? (
        <p className="text-sm text-muted-foreground">{t("common.loading")}</p>
      ) : servers.error ? (
        <div className="rounded border border-red-300 bg-red-50 p-3 text-sm text-red-700 dark:border-red-800 dark:bg-red-950 dark:text-red-400">
          {servers.error.message}
        </div>
      ) : rows.length > 0 ? (
        <div className="space-y-4 alx-stagger">
          {rows.map((server) => (
            <MCPServerCard key={server.id} server={server} isAdmin={isAdmin} />
          ))}
        </div>
      ) : (
        <p className="text-sm text-muted-foreground">{t("mcp.empty")}</p>
      )}
    </div>
  )
}
