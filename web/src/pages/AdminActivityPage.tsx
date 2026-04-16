import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import * as React from "react"
import { toast } from "sonner"

import { api, type AuditEventDto } from "@/api/client"
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
  "auth.registered": (p) => `${str(p.actor_email)} registered (${str(p.display_name)})`,
  "auth.login_success": (p) => `${str(p.actor_email)} logged in`,
  "auth.login_failed": (p) => `Login failed for ${str(p.attempted_email)}`,
  "auth.logout": (p) =>
    p.actor_email ? `${str(p.actor_email)} logged out` : "Anonymous logout",
  "auth.display_name_updated": (p) =>
    `${str(p.actor_email)} changed display name to "${str(p.new_display_name)}"`,
  "auth.email_updated": (p) =>
    `${str(p.old_email)} changed email to ${str(p.new_email)}`,
  "auth.passphrase_updated": (p) => `${str(p.actor_email)} changed passphrase`,
  "credential.stored": (p) =>
    `${str(p.actor_email)} stored credential in slot "${str(p.slot)}"`,
  "credential.deleted": (p) =>
    `${str(p.actor_email)} deleted credential slot "${str(p.slot)}"`,
  "admin.user_created": (p) =>
    `${str(p.actor_email)} created user ${str(p.target_email)} (${str(p.target_display_name)})`,
  "admin.user_deleted": (p) =>
    `${str(p.actor_email)} deleted user ${str(p.target_email)}`,
  "admin.capability_granted": (p) =>
    `${str(p.actor_email)} granted "${str(p.capability)}" to ${str(p.target_email)}`,
  "admin.capability_revoked": (p) =>
    `${str(p.actor_email)} revoked "${str(p.capability)}" from ${str(p.target_email)}`,
  "admin.audit_log_cleared": (p) =>
    `${str(p.actor_email)} cleared the audit log`,
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
  if (kind.startsWith("auth.login_failed")) return "bg-red-100 text-red-700"
  if (kind.startsWith("admin.user_deleted")) return "bg-red-100 text-red-700"
  if (kind.startsWith("admin.")) return "bg-amber-100 text-amber-700"
  if (kind.startsWith("auth.")) return "bg-blue-100 text-blue-700"
  if (kind.startsWith("credential.")) return "bg-slate-100 text-slate-600"
  return "bg-slate-100 text-slate-500"
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
      toast.success("Audit log cleared")
    },
    onError: (err: Error) => {
      toast.error(err.message)
    },
  })

  return (
    <div className="max-w-3xl space-y-6">
      <h1 className="text-2xl font-semibold">Admin — Activity log</h1>
      <Card>
        <CardHeader>
          <div className="flex items-center justify-between gap-4">
            <CardTitle>Recent events (newest first)</CardTitle>
            <div className="flex items-center gap-3">
              <span className="text-xs text-muted-foreground">
                Showing up to 200 most recent events
              </span>
              <ConfirmDialog
                trigger={
                  <Button variant="destructive" size="sm">
                    Clear log
                  </Button>
                }
                title="Clear the audit log?"
                description="All event history will be permanently removed. The clearing action itself will be recorded as the first entry of the new log. This cannot be undone."
                confirmLabel="Clear log"
                destructive
                onConfirm={() => { void clearMutation.mutate() }}
              />
            </div>
          </div>
        </CardHeader>
        <CardContent>
          {events.isLoading && (
            <div className="text-sm text-slate-500">Loading…</div>
          )}
          {events.error instanceof Error && (
            <div className="rounded border border-red-200 bg-red-50 p-2 text-sm text-red-700">
              {events.error.message}
            </div>
          )}
          {events.data && events.data.length === 0 && (
            <div className="text-sm text-slate-500">No events recorded yet.</div>
          )}
          {events.data && events.data.length > 0 && (
            <ul className="divide-y text-sm">
              {events.data.map((ev, i) => (
                <li key={i} className="flex items-start gap-3 py-2">
                  <span className="w-16 shrink-0 text-xs text-slate-400 pt-0.5">
                    {relativeTime(ev.at)}
                  </span>
                  <KindPill kind={ev.kind} />
                  <span className="text-slate-700">{summarise(ev)}</span>
                </li>
              ))}
            </ul>
          )}
        </CardContent>
      </Card>
    </div>
  )
}
