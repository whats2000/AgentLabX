import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { Eye, KeyRound, Save, Trash2, X } from "lucide-react"
import * as React from "react"
import { useTranslation } from "react-i18next"
import { toast } from "sonner"

import { api, type CredentialSlotDto, type MCPScope } from "@/api/client"
import { ConfirmDialog } from "@/components/confirm-dialog"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { PasswordInput } from "@/components/ui/password-input"

interface Props {
  slotRefs: string[]
  scope: MCPScope
  isAdmin: boolean
}

interface SlotApi {
  list: () => Promise<CredentialSlotDto[]>
  put: (slot: string, value: string) => Promise<void>
  del: (slot: string) => Promise<void>
  reveal: (slot: string) => Promise<{ slot: string; value: string }>
  queryKey: readonly string[]
}

function userSlotApi(): SlotApi {
  return {
    list: api.listCredentials,
    put: api.putCredential,
    del: api.deleteCredential,
    reveal: api.revealCredential,
    queryKey: ["credentials"],
  }
}

function adminSlotApi(): SlotApi {
  return {
    list: api.listAdminCredentials,
    put: api.putAdminCredential,
    del: api.deleteAdminCredential,
    reveal: api.revealAdminCredential,
    queryKey: ["admin-credentials"],
  }
}

export function SlotsPanel({ slotRefs, scope, isAdmin }: Props): React.JSX.Element | null {
  const { t } = useTranslation()

  // Admin-scope slots resolve out of admin_configs, which only admins can read
  // or write. For a non-admin user looking at an admin-scope server we hide
  // the writer entirely (they can still see the slot names alongside).
  const slotApi = scope === "admin" ? adminSlotApi() : userSlotApi()
  const writable = scope === "user" || isAdmin

  const stored = useQuery<CredentialSlotDto[]>({
    queryKey: slotApi.queryKey,
    queryFn: slotApi.list,
    enabled: writable,
  })

  const storedSet = React.useMemo(() => {
    return new Set((stored.data ?? []).map((s) => s.slot))
  }, [stored.data])

  if (slotRefs.length === 0) return null

  return (
    <div className="space-y-2">
      <div className="flex items-center gap-2 text-xs font-semibold uppercase tracking-wide text-muted-foreground">
        <KeyRound className="h-3.5 w-3.5" />
        {t("mcp.slotPanelTitle")}
      </div>
      <ul className="space-y-2">
        {slotRefs.map((ref) => (
          <SlotRow
            key={ref}
            slot={ref}
            isStored={storedSet.has(ref)}
            slotApi={slotApi}
            writable={writable}
          />
        ))}
      </ul>
      {scope === "admin" && !isAdmin ? (
        <p className="text-xs text-muted-foreground">{t("mcp.adminSlotReadonly")}</p>
      ) : null}
    </div>
  )
}

function SlotRow({
  slot,
  isStored,
  slotApi,
  writable,
}: {
  slot: string
  isStored: boolean
  slotApi: SlotApi
  writable: boolean
}): React.JSX.Element {
  const { t } = useTranslation()
  const qc = useQueryClient()
  const [editing, setEditing] = React.useState(false)
  const [value, setValue] = React.useState("")
  const [revealed, setRevealed] = React.useState<string | null>(null)

  const put = useMutation({
    mutationFn: () => slotApi.put(slot, value),
    onSuccess: () => {
      setValue("")
      setEditing(false)
      void qc.invalidateQueries({ queryKey: slotApi.queryKey })
      toast.success(t("mcp.slotSavedRestartHint"))
    },
    onError: (err: Error) => {
      toast.error(err.message)
    },
  })

  const del = useMutation({
    mutationFn: () => slotApi.del(slot),
    onSuccess: () => {
      setRevealed(null)
      void qc.invalidateQueries({ queryKey: slotApi.queryKey })
      toast.success(t("mcp.slotDeleted"))
    },
    onError: (err: Error) => {
      toast.error(err.message)
    },
  })

  const reveal = useMutation({
    mutationFn: () => slotApi.reveal(slot),
    onSuccess: (data) => {
      setRevealed(data.value)
    },
    onError: (err: Error) => {
      toast.error(err.message)
    },
  })

  return (
    <li className="rounded border border-border bg-background/50 p-2.5 space-y-2">
      <div className="flex flex-wrap items-center gap-2">
        <code className="font-mono text-xs">{slot}</code>
        {isStored ? (
          <span className="inline-flex items-center gap-1 rounded-full bg-emerald-100 px-2 py-0.5 text-[10px] font-medium uppercase tracking-wide text-emerald-700 dark:bg-emerald-950 dark:text-emerald-300">
            {t("mcp.slotSet")}
          </span>
        ) : (
          <span className="inline-flex items-center gap-1 rounded-full bg-amber-100 px-2 py-0.5 text-[10px] font-medium uppercase tracking-wide text-amber-700 dark:bg-amber-950 dark:text-amber-300">
            {t("mcp.slotUnset")}
          </span>
        )}
        <div className="ml-auto flex shrink-0 gap-1">
          {writable ? (
            <Button
              type="button"
              size="sm"
              variant="outline"
              onClick={() => {
                setEditing((v) => !v)
                setRevealed(null)
              }}
            >
              {editing ? (
                <X className="h-4 w-4" />
              ) : isStored ? (
                t("mcp.slotEdit")
              ) : (
                t("mcp.slotSet")
              )}
            </Button>
          ) : null}
          {writable && isStored ? (
            <Button
              type="button"
              size="sm"
              variant="outline"
              onClick={() => {
                reveal.mutate()
              }}
              disabled={reveal.isPending}
            >
              <Eye className="h-4 w-4" />
            </Button>
          ) : null}
          {writable && isStored ? (
            <ConfirmDialog
              trigger={
                <Button type="button" size="sm" variant="outline">
                  <Trash2 className="h-4 w-4" />
                </Button>
              }
              title={t("mcp.slotDeleteTitle")}
              description={<>{t("mcp.slotDeleteDesc", { slot })}</>}
              confirmLabel={t("common.delete")}
              destructive
              onConfirm={() => {
                del.mutate()
              }}
            />
          ) : null}
        </div>
      </div>

      {revealed !== null ? (
        <div className="rounded border border-dashed border-border bg-muted/40 p-2">
          <Input value={revealed} readOnly className="font-mono text-xs" />
        </div>
      ) : null}

      {editing && writable ? (
        <form
          className="flex items-end gap-2"
          onSubmit={(e) => {
            e.preventDefault()
            put.mutate()
          }}
        >
          <div className="flex-1 space-y-1">
            <PasswordInput
              value={value}
              onChange={(e) => {
                setValue(e.target.value)
              }}
              placeholder={t("mcp.slotValuePlaceholder")}
              required
              autoFocus
            />
          </div>
          <Button type="submit" size="sm" disabled={put.isPending || value.length === 0}>
            <Save className="h-4 w-4" />
            {t("common.save")}
          </Button>
        </form>
      ) : null}
    </li>
  )
}
