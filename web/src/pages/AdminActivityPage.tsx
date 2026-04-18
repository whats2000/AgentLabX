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

const SUMMARY: Record<string, (p: Payload) => string> = {
  "auth.registered": (p) =>
    i18n.t("activity.auth_registered", { actor: str(p.actor_email), display_name: str(p.display_name) }),
  "auth.login_success": (p) =>
    i18n.t("activity.auth_login_success", { actor: str(p.actor_email) }),
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
    i18n.t("activity.admin_user_deleted", { actor: str(p.actor_email), target: str(p.target_email) }),
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
}

function summarise(event: AuditEventDto): string {
  const fn = SUMMARY[event.kind]
  if (fn) return fn(event.payload)
  return JSON.stringify(event.payload)
}

// ---------------------------------------------------------------------------
// Kind pill
// ---------------------------------------------------------------------------

function kindColour(kind: string): string {
  if (kind.startsWith("auth.login_failed")) return "bg-red-100 text-red-700 dark:bg-red-900 dark:text-red-300"
  if (kind.startsWith("admin.user_deleted")) return "bg-red-100 text-red-700 dark:bg-red-900 dark:text-red-300"
  if (kind.startsWith("admin.")) return "bg-amber-100 text-amber-700 dark:bg-amber-900 dark:text-amber-300"
  if (kind.startsWith("auth.")) return "bg-blue-100 text-blue-700 dark:bg-blue-900 dark:text-blue-300"
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
              <span className="text-xs text-muted-foreground">
                {t("activity.showingUpTo")}
              </span>
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
                onConfirm={() => { void clearMutation.mutate() }}
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
              {events.data.map((ev, i) => (
                <li key={i} className="flex items-start gap-3 py-2 min-w-0">
                  <span className="w-16 shrink-0 text-xs text-muted-foreground pt-0.5">
                    {relativeTime(ev.at)}
                  </span>
                  <KindPill kind={ev.kind} />
                  <span className="min-w-0 break-words text-foreground">{summarise(ev)}</span>
                </li>
              ))}
            </ul>
          )}
        </CardContent>
      </Card>
    </div>
  )
}
