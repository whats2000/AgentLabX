import { useMutation, useQueryClient } from "@tanstack/react-query"
import {
  AlertTriangle,
  CheckCircle2,
  ChevronRight,
  Cpu,
  Globe,
  Network,
  Package,
  ShieldCheck,
  Trash2,
  User as UserIcon,
  XCircle,
} from "lucide-react"
import * as React from "react"
import { useTranslation } from "react-i18next"
import { toast } from "sonner"

import { api, type MCPServerDto } from "@/api/client"
import { ConfirmDialog } from "@/components/confirm-dialog"
import { MCPToolRow } from "@/components/mcp/MCPToolRow"
import { SlotsPanel } from "@/components/mcp/SlotsPanel"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Label } from "@/components/ui/label"

interface Props {
  server: MCPServerDto
  isAdmin: boolean
}

function transportIcon(transport: MCPServerDto["transport"]): React.JSX.Element {
  if (transport === "stdio") return <Cpu className="h-3.5 w-3.5" />
  if (transport === "http") return <Globe className="h-3.5 w-3.5" />
  return <Network className="h-3.5 w-3.5" />
}

export function MCPServerCard({ server, isAdmin }: Props): React.JSX.Element {
  const { t } = useTranslation()
  const qc = useQueryClient()
  const [toolsOpen, setToolsOpen] = React.useState(false)
  // Defer mounting the tool rows (each with their own form + hooks) until
  // the user first opens this card. Stays mounted after that so the
  // collapse animation completes and per-row state survives.
  const [toolsEverOpened, setToolsEverOpened] = React.useState(false)

  const canMutate = isAdmin || server.scope === "user"

  const patch = useMutation({
    mutationFn: (next: boolean) => api.patchMCPServer(server.id, next),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ["mcp-servers"] })
      toast.success(t("mcp.toggleOk"))
    },
    onError: (err: Error) => {
      toast.error(err.message)
    },
  })

  const del = useMutation({
    mutationFn: () => api.deleteMCPServer(server.id),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ["mcp-servers"] })
      toast.success(t("mcp.deleteOk"))
    },
    onError: (err: Error) => {
      toast.error(err.message)
    },
  })

  return (
    <Card>
      <CardHeader>
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div className="min-w-0 space-y-1.5">
            <CardTitle className="flex items-center gap-2 truncate">
              <span className="truncate">{server.name}</span>
              {server.scope === "admin" ? (
                <span className="inline-flex items-center gap-1 rounded-full border border-border bg-muted px-2 py-0.5 text-[10px] font-medium uppercase tracking-wide text-muted-foreground">
                  <ShieldCheck className="h-3 w-3" /> {t("mcp.scopeAdmin")}
                </span>
              ) : (
                <span className="inline-flex items-center gap-1 rounded-full border border-border bg-muted px-2 py-0.5 text-[10px] font-medium uppercase tracking-wide text-muted-foreground">
                  <UserIcon className="h-3 w-3" /> {t("mcp.scopeUser")}
                </span>
              )}
              <span className="inline-flex items-center gap-1 rounded-full border border-border bg-muted px-2 py-0.5 text-[10px] font-medium uppercase tracking-wide text-muted-foreground">
                {transportIcon(server.transport)} {server.transport}
              </span>
              {server.bundled ? (
                <span
                  className="inline-flex items-center gap-1 rounded-full border border-border bg-muted px-2 py-0.5 text-[10px] font-medium uppercase tracking-wide text-muted-foreground"
                  title={t("mcp.bundledHint")}
                >
                  <Package className="h-3 w-3" /> {t("mcp.bundled")}
                </span>
              ) : null}
            </CardTitle>
            <div className="flex flex-wrap items-center gap-2 text-xs text-muted-foreground">
              {server.enabled ? (
                <span className="inline-flex items-center gap-1 text-emerald-600 dark:text-emerald-400">
                  <CheckCircle2 className="h-3.5 w-3.5" /> {t("mcp.enabled")}
                </span>
              ) : (
                <span className="inline-flex items-center gap-1 text-amber-600 dark:text-amber-400">
                  <XCircle className="h-3.5 w-3.5" /> {t("mcp.disabled")}
                </span>
              )}
              <span>·</span>
              <span>{t("mcp.toolCount", { count: server.tools.length })}</span>
              {server.declared_capabilities.length > 0 ? (
                <>
                  <span>·</span>
                  <span className="flex flex-wrap gap-1">
                    {server.declared_capabilities.map((c) => (
                      <span
                        key={c}
                        className="rounded bg-muted px-1.5 py-0.5 font-mono text-[10px] text-muted-foreground"
                      >
                        {c}
                      </span>
                    ))}
                  </span>
                </>
              ) : null}
            </div>
          </div>

          <div className="flex shrink-0 items-center gap-2">
            {canMutate ? (
              <Button
                type="button"
                variant="outline"
                size="sm"
                disabled={patch.isPending}
                onClick={() => {
                  patch.mutate(!server.enabled)
                }}
              >
                {server.enabled ? t("mcp.disable") : t("mcp.enable")}
              </Button>
            ) : null}
            {canMutate && !server.bundled ? (
              <ConfirmDialog
                trigger={
                  <Button type="button" variant="outline" size="sm" disabled={del.isPending}>
                    <Trash2 className="h-4 w-4" />
                  </Button>
                }
                title={t("mcp.deleteTitle")}
                description={<>{t("mcp.deleteDesc", { name: server.name })}</>}
                confirmLabel={t("common.delete")}
                destructive
                onConfirm={() => {
                  del.mutate()
                }}
              />
            ) : null}
          </div>
        </div>
      </CardHeader>

      <CardContent className="space-y-3">
        {server.last_startup_error ? (
          <div className="flex gap-2 rounded border border-red-300 bg-red-50 p-2 text-xs text-red-800 dark:border-red-800 dark:bg-red-950 dark:text-red-300">
            <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" />
            <div className="min-w-0 space-y-1">
              <div className="font-semibold uppercase tracking-wide text-[10px]">
                {t("mcp.lastStartupError")}
              </div>
              <div className="break-words font-mono">{server.last_startup_error}</div>
              <div className="text-[10px] opacity-75">{t("mcp.lastStartupErrorHint")}</div>
            </div>
          </div>
        ) : null}

        {server.transport === "stdio" && server.command ? (
          <div className="space-y-1">
            <Label className="text-xs">{t("mcp.commandLabel")}</Label>
            <code className="block rounded bg-muted px-2 py-1 text-xs font-mono break-all">
              {server.command.join(" ")}
            </code>
          </div>
        ) : null}

        {server.transport === "http" && server.url ? (
          <div className="space-y-1">
            <Label className="text-xs">{t("mcp.urlLabel")}</Label>
            <code className="block rounded bg-muted px-2 py-1 text-xs font-mono break-all">
              {server.url}
            </code>
          </div>
        ) : null}

        {server.transport === "inprocess" && server.inprocess_key ? (
          <div className="space-y-1">
            <Label className="text-xs">{t("mcp.inprocessKeyLabel")}</Label>
            <code className="block rounded bg-muted px-2 py-1 text-xs font-mono break-all">
              {server.inprocess_key}
            </code>
          </div>
        ) : null}

        <SlotsPanel slotRefs={server.env_slot_refs} scope={server.scope} isAdmin={isAdmin} />

        <button
          type="button"
          className="alx-press group flex w-full items-center gap-2 rounded border border-dashed border-border bg-muted/30 px-2 py-1.5 text-left text-sm text-muted-foreground transition-all duration-200 ease-out-soft hover:border-border/80 hover:bg-muted/60 hover:text-foreground"
          onClick={() => {
            setToolsOpen((v) => {
              if (!v) setToolsEverOpened(true)
              return !v
            })
          }}
          aria-expanded={toolsOpen}
        >
          <ChevronRight
            className={
              "h-4 w-4 transition-transform duration-300 ease-out-snap " +
              (toolsOpen ? "rotate-90" : "group-hover:translate-x-0.5")
            }
          />
          {toolsOpen ? t("mcp.hideTools") : t("mcp.showTools", { count: server.tools.length })}
        </button>

        {/* Drawer — grid-rows 0fr → 1fr animates both open and close.
            Keeps content mounted so collapse animates too. */}
        <div
          className={
            "grid transition-[grid-template-rows,opacity] duration-300 ease-out-snap " +
            (toolsOpen ? "grid-rows-[1fr] opacity-100" : "grid-rows-[0fr] opacity-0")
          }
          inert={!toolsOpen}
        >
          <div className="min-h-0 overflow-hidden">
            {toolsEverOpened ? (
              server.tools.length > 0 ? (
                <ul className="space-y-2 pt-1">
                  {server.tools.map((tool) => (
                    <MCPToolRow key={`${tool.server_id}::${tool.tool_name}`} tool={tool} />
                  ))}
                </ul>
              ) : (
                <p className="pt-1 text-xs text-muted-foreground">{t("mcp.noTools")}</p>
              )
            ) : null}
          </div>
        </div>
      </CardContent>
    </Card>
  )
}
