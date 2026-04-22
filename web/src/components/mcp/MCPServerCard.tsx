import { useMutation, useQueryClient } from "@tanstack/react-query"
import {
  CheckCircle2,
  ChevronDown,
  ChevronRight,
  Cpu,
  Globe,
  Network,
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
            {canMutate ? (
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
        {server.transport === "stdio" ? (
          <div className="space-y-1">
            <Label className="text-xs">{t("mcp.commandLabel")}</Label>
            <code className="block rounded bg-muted px-2 py-1 text-xs font-mono break-all">
              {/* The /api/mcp/servers response doesn't include command in MCPServerResponse;
                  surface a placeholder so the slot is visible — operators look this up via
                  the backend logs / pyproject. */}
              {t("mcp.commandHidden")}
            </code>
          </div>
        ) : null}

        <SlotsPanel slotRefs={server.env_slot_refs} scope={server.scope} isAdmin={isAdmin} />

        <button
          type="button"
          className="flex w-full items-center gap-2 rounded border border-dashed border-border bg-muted/30 px-2 py-1.5 text-left text-sm text-muted-foreground transition-colors hover:bg-muted/60 hover:text-foreground"
          onClick={() => {
            setToolsOpen((v) => !v)
          }}
        >
          {toolsOpen ? <ChevronDown className="h-4 w-4" /> : <ChevronRight className="h-4 w-4" />}
          {toolsOpen ? t("mcp.hideTools") : t("mcp.showTools", { count: server.tools.length })}
        </button>

        {toolsOpen ? (
          server.tools.length > 0 ? (
            <ul className="space-y-2">
              {server.tools.map((tool) => (
                <MCPToolRow key={`${tool.server_id}::${tool.tool_name}`} tool={tool} />
              ))}
            </ul>
          ) : (
            <p className="text-xs text-muted-foreground">{t("mcp.noTools")}</p>
          )
        ) : null}
      </CardContent>
    </Card>
  )
}
