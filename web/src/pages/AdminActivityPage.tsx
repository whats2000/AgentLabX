import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import * as React from "react"
import { useTranslation } from "react-i18next"
import { toast } from "sonner"

import { api, type AuditEventDto } from "@/api/client"
import i18n from "@/i18n"
import { ConfirmDialog } from "@/components/confirm-dialog"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"

// ---------------------------------------------------------------------------
// Payload summary helpers
// ---------------------------------------------------------------------------

type Payload = Record<string, string | number | boolean | null>

function str(v: string | number | boolean | null | undefined): string {
  if (v === null || v === undefined) return ""
  return String(v)
}

function shortId(id: string | number | boolean | null | undefined): string {
  const s = str(id)
  return s.length > 12 ? `${s.slice(0, 8)}…` : s
}

function fmtCost(v: string | number | boolean | null | undefined): string {
  if (v === null || v === undefined || v === "") return "0.0000"
  const n = typeof v === "number" ? v : Number(v)
  if (!Number.isFinite(n)) return str(v)
  return n.toFixed(4)
}

const SUMMARY: Record<string, (p: Payload) => string> = {
  "auth.registered": (p) =>
    i18n.t("activity.auth_registered", {
      actor: str(p.actor_email),
      display_name: str(p.display_name),
    }),
  "auth.login_success": (p) => i18n.t("activity.auth_login_success", { actor: str(p.actor_email) }),
  "auth.login_failed": (p) =>
    i18n.t("activity.auth_login_failed", { email: str(p.attempted_email) }),
  "auth.logout": (p) =>
    p.actor_email
      ? i18n.t("activity.auth_logout", { actor: str(p.actor_email) })
      : i18n.t("activity.auth_logout_anon"),
  "auth.display_name_updated": (p) =>
    i18n.t("activity.auth_display_name_updated", {
      actor: str(p.actor_email),
      new_display_name: str(p.new_display_name),
    }),
  "auth.email_updated": (p) =>
    i18n.t("activity.auth_email_updated", {
      old_email: str(p.old_email),
      new_email: str(p.new_email),
    }),
  "auth.passphrase_updated": (p) =>
    i18n.t("activity.auth_passphrase_updated", { actor: str(p.actor_email) }),
  "credential.stored": (p) =>
    i18n.t("activity.credential_stored", { actor: str(p.actor_email), slot: str(p.slot) }),
  "credential.deleted": (p) =>
    i18n.t("activity.credential_deleted", { actor: str(p.actor_email), slot: str(p.slot) }),
  "admin.user_created": (p) =>
    i18n.t("activity.admin_user_created", {
      actor: str(p.actor_email),
      target: str(p.target_email),
      display_name: str(p.target_display_name),
    }),
  "admin.user_deleted": (p) =>
    i18n.t("activity.admin_user_deleted", {
      actor: str(p.actor_email),
      target: str(p.target_email),
    }),
  "admin.capability_granted": (p) =>
    i18n.t("activity.admin_capability_granted", {
      actor: str(p.actor_email),
      capability: str(p.capability),
      target: str(p.target_email),
    }),
  "admin.capability_revoked": (p) =>
    i18n.t("activity.admin_capability_revoked", {
      actor: str(p.actor_email),
      capability: str(p.capability),
      target: str(p.target_email),
    }),
  "admin.audit_log_cleared": (p) =>
    i18n.t("activity.admin_audit_log_cleared", { actor: str(p.actor_email) }),
  "auth.login_rate_limited": (p) =>
    i18n.t("activity.auth_login_rate_limited", {
      email: str(p.attempted_email),
      seconds: str(p.retry_after_seconds),
    }),
  "auth.session_revoked": (p) =>
    i18n.t("activity.auth_session_revoked", {
      actor: str(p.actor_email),
      session: shortId(p.session_id),
    }),
  "auth.token_issued": (p) =>
    i18n.t("activity.auth_token_issued", { actor: str(p.actor_email), label: str(p.label) }),
  "auth.token_deleted": (p) =>
    i18n.t("activity.auth_token_deleted", {
      actor: str(p.actor_email),
      token: shortId(p.token_id),
    }),
  "auth.token_refreshed": (p) =>
    i18n.t("activity.auth_token_refreshed", { actor: str(p.actor_email), label: str(p.label) }),
  "llm.called": (p) =>
    i18n.t("activity.llm_called", {
      model: str(p.model),
      total: str(p.total_tokens),
      prompt: str(p.prompt_tokens),
      completion: str(p.completion_tokens),
      cost: fmtCost(p.cost_usd),
    }),
  "llm.error": (p) => i18n.t("activity.llm_error", { model: str(p.model), error: str(p.error) }),
  "mcp.bundle.discovery_failed": (p) =>
    i18n.t("activity.mcp_bundle_discovery_failed", {
      bundle: str(p.entry_point),
      error_type: str(p.error_type),
      reason: str(p.reason),
    }),
  "mcp.bundle.seed_failed": (p) =>
    i18n.t("activity.mcp_bundle_seed_failed", {
      bundle: str(p.bundle),
      error_type: str(p.error_type),
      reason: str(p.reason),
    }),
  "mcp.server.started": (p) =>
    i18n.t("activity.mcp_server_started", {
      server: str(p.server_name),
      transport: str(p.transport),
      tool_count: str(p.tool_count),
    }),
  "mcp.server.stopped": (p) =>
    i18n.t("activity.mcp_server_stopped", { server: shortId(p.server_id) }),
  "mcp.server.startup_failed": (p) =>
    i18n.t("activity.mcp_server_startup_failed", {
      server: str(p.server_name),
      reason: str(p.reason),
    }),
  "mcp.server.stop_failed": (p) =>
    i18n.t("activity.mcp_server_stop_failed", {
      server: shortId(p.server_id),
      error_type: str(p.error_type),
      reason: str(p.reason),
    }),
  "mcp.tool.called": (p) =>
    i18n.t("activity.mcp_tool_called", {
      stage: str(p.stage),
      agent: str(p.agent),
      tool: str(p.tool),
      server: shortId(p.server_id),
    }),
  "mcp.tool.refused": (p) =>
    i18n.t("activity.mcp_tool_refused", {
      stage: str(p.stage),
      agent: str(p.agent),
      tool: str(p.tool),
      reason: str(p.reason),
    }),
  "mcp.tool.error": (p) =>
    i18n.t("activity.mcp_tool_error", {
      stage: str(p.stage),
      agent: str(p.agent),
      tool: str(p.tool),
      error_type: str(p.error_type),
      reason: str(p.reason),
    }),
}

function summarise(event: AuditEventDto): string | null {
  const fn = SUMMARY[event.kind]
  if (fn) return fn(event.payload)
  return null
}

// Trim long scalar values to keep the row scannable. Full payload is
// available in the JSONL audit file; the activity feed is a glance surface.
function trimValue(v: string): string {
  return v.length > 80 ? `${v.slice(0, 77)}…` : v
}

function PayloadChips({ payload }: { payload: AuditEventDto["payload"] }): React.JSX.Element {
  const entries = Object.entries(payload).filter(([, v]) => v !== null && v !== "")
  if (entries.length === 0) {
    return <span className="text-xs italic text-muted-foreground">(no payload)</span>
  }
  return (
    <span className="flex flex-wrap items-center gap-x-3 gap-y-1 text-xs">
      {entries.map(([k, v]) => (
        <span key={k} className="inline-flex items-baseline gap-1">
          <span className="font-mono text-[10px] uppercase tracking-wide text-muted-foreground">
            {k}
          </span>
          <span className="font-mono text-foreground">{trimValue(String(v))}</span>
        </span>
      ))}
    </span>
  )
}

// ---------------------------------------------------------------------------
// Kind pill
// ---------------------------------------------------------------------------

function kindColour(kind: string): string {
  if (kind.startsWith("auth.login_failed"))
    return "bg-red-100 text-red-700 dark:bg-red-900 dark:text-red-300"
  if (kind.startsWith("admin.user_deleted"))
    return "bg-red-100 text-red-700 dark:bg-red-900 dark:text-red-300"
  if (kind.startsWith("admin."))
    return "bg-amber-100 text-amber-700 dark:bg-amber-900 dark:text-amber-300"
  if (kind.startsWith("auth."))
    return "bg-blue-100 text-blue-700 dark:bg-blue-900 dark:text-blue-300"
  if (kind.startsWith("credential.")) return "bg-muted text-muted-foreground"
  return "bg-muted text-muted-foreground"
}

function KindPill({ kind }: { kind: string }): React.JSX.Element {
  return (
    <span
      className={`inline-flex items-center rounded px-1.5 py-0.5 text-xs font-mono font-medium ${kindColour(kind)}`}
    >
      {kind}
    </span>
  )
}

// ---------------------------------------------------------------------------
// Relative time
// ---------------------------------------------------------------------------

function relativeTime(isoString: string): string {
  const diff = Date.now() - new Date(isoString).getTime()
  const seconds = Math.floor(diff / 1000)
  if (seconds < 60) return `${seconds}s ago`
  const minutes = Math.floor(seconds / 60)
  if (minutes < 60) return `${minutes}m ago`
  const hours = Math.floor(minutes / 60)
  if (hours < 24) return `${hours}h ago`
  const days = Math.floor(hours / 24)
  return `${days}d ago`
}

// ---------------------------------------------------------------------------
// Page
// ---------------------------------------------------------------------------

export function AdminActivityPage(): React.JSX.Element {
  const { t } = useTranslation()
  const queryClient = useQueryClient()

  const events = useQuery<AuditEventDto[]>({
    queryKey: ["admin-events"],
    queryFn: () => api.listEvents(200),
    refetchInterval: 15_000,
  })

  const clearMutation = useMutation({
    mutationFn: () => api.clearEvents(),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["admin-events"] })
      toast.success(t("activity.logCleared"))
    },
    onError: (err: Error) => {
      toast.error(err.message)
    },
  })

  return (
    <div className="max-w-3xl space-y-6">
      <h1 className="text-2xl font-semibold">{t("activity.title")}</h1>
      <Card>
        <CardHeader>
          <div className="flex items-center justify-between gap-4">
            <CardTitle>{t("activity.recentEvents")}</CardTitle>
            <div className="flex items-center gap-3">
              <span className="text-xs text-muted-foreground">{t("activity.showingUpTo")}</span>
              <ConfirmDialog
                trigger={
                  <Button variant="destructive" size="sm">
                    {t("activity.clearLog")}
                  </Button>
                }
                title={t("activity.clearLogTitle")}
                description={t("activity.clearLogDesc")}
                confirmLabel={t("activity.clearLogConfirm")}
                destructive
                onConfirm={() => {
                  void clearMutation.mutate()
                }}
              />
            </div>
          </div>
        </CardHeader>
        <CardContent>
          {events.isLoading && (
            <div className="text-sm text-muted-foreground">{t("activity.loading")}</div>
          )}
          {events.error instanceof Error && (
            <div className="rounded border border-red-200 bg-red-50 p-2 text-sm text-red-700 dark:border-red-800 dark:bg-red-950 dark:text-red-400">
              {events.error.message}
            </div>
          )}
          {events.data && events.data.length === 0 && (
            <div className="text-sm text-muted-foreground">{t("activity.noEvents")}</div>
          )}
          {events.data && events.data.length > 0 && (
            <ul className="divide-y divide-border text-sm">
              {events.data.map((ev, i) => {
                const summary = summarise(ev)
                return (
                  <li key={i} className="flex items-start gap-3 py-2 min-w-0">
                    <span className="w-16 shrink-0 text-xs text-muted-foreground pt-0.5">
                      {relativeTime(ev.at)}
                    </span>
                    <KindPill kind={ev.kind} />
                    <span className="min-w-0 break-words text-foreground">
                      {summary !== null ? summary : <PayloadChips payload={ev.payload} />}
                    </span>
                  </li>
                )
              })}
            </ul>
          )}
        </CardContent>
      </Card>
    </div>
  )
}
