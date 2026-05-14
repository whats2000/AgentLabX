import { useMutation, useQueryClient } from "@tanstack/react-query"
import { CheckCircle2, Loader2, Trash2, X } from "lucide-react"
import * as React from "react"
import { useTranslation } from "react-i18next"
import { toast } from "sonner"

import {
  api,
  type MCPScope,
  type MCPServerCreateRequest,
  type MCPServerDto,
  type MCPTransport,
} from "@/api/client"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"

interface Props {
  isAdmin: boolean
  onClose: () => void
}

interface DraftSlot {
  ref: string
  value: string
}

function splitTokens(raw: string): string[] {
  return raw
    .split(/[\s,]+/)
    .map((s) => s.trim())
    .filter(Boolean)
}

function buildBody(form: FormState): MCPServerCreateRequest {
  const command = form.transport === "stdio" ? splitTokens(form.command) : null
  const url = form.transport === "http" ? form.url.trim() || null : null
  const inprocess_key = form.transport === "inprocess" ? form.inprocess_key.trim() || null : null
  return {
    name: form.name.trim(),
    scope: form.scope,
    transport: form.transport,
    command,
    url,
    inprocess_key,
    env_slot_refs: form.slots.map((s) => s.ref).filter(Boolean),
    declared_capabilities: splitTokens(form.declared_capabilities),
  }
}

interface FormState {
  name: string
  scope: MCPScope
  transport: MCPTransport
  command: string
  url: string
  inprocess_key: string
  declared_capabilities: string
  slots: DraftSlot[]
}

const EMPTY_FORM: FormState = {
  name: "",
  scope: "user",
  transport: "stdio",
  command: "",
  url: "",
  inprocess_key: "",
  declared_capabilities: "",
  slots: [],
}

export function RegisterMCPServerForm({ isAdmin, onClose }: Props): React.JSX.Element {
  const { t } = useTranslation()
  const qc = useQueryClient()
  const [form, setForm] = React.useState<FormState>(EMPTY_FORM)
  const [registered, setRegistered] = React.useState<MCPServerDto | null>(null)

  const register = useMutation({
    mutationFn: async (): Promise<MCPServerDto> => {
      const body = buildBody(form)
      const created = await api.registerMCPServer(body)
      // Persist any slot values the user supplied. user_configs covers user-scope
      // servers; admin slots beyond that need an admin_configs writer (out of scope
      // for this surface — show a warning instead).
      const eligible = form.slots.filter((s) => s.ref && s.value)
      for (const s of eligible) {
        if (form.scope === "user") {
          await api.putCredential(s.ref, s.value)
        }
      }
      return created
    },
    onSuccess: (server) => {
      setRegistered(server)
      void qc.invalidateQueries({ queryKey: ["mcp-servers"] })
      void qc.invalidateQueries({ queryKey: ["credentials"] })
      toast.success(t("mcp.registerOk", { count: server.tools.length }))
    },
    onError: (err: Error) => {
      toast.error(err.message)
    },
  })

  const rollback = useMutation({
    mutationFn: async (id: string) => {
      await api.deleteMCPServer(id)
    },
    onSuccess: () => {
      setRegistered(null)
      setForm(EMPTY_FORM)
      void qc.invalidateQueries({ queryKey: ["mcp-servers"] })
      toast.success(t("mcp.discardOk"))
    },
    onError: (err: Error) => {
      toast.error(err.message)
    },
  })

  function set<K extends keyof FormState>(key: K, value: FormState[K]): void {
    setForm((prev) => ({ ...prev, [key]: value }))
  }

  function addSlot(): void {
    setForm((prev) => ({ ...prev, slots: [...prev.slots, { ref: "", value: "" }] }))
  }

  function removeSlot(index: number): void {
    setForm((prev) => ({ ...prev, slots: prev.slots.filter((_, i) => i !== index) }))
  }

  function patchSlot(index: number, patch: Partial<DraftSlot>): void {
    setForm((prev) => ({
      ...prev,
      slots: prev.slots.map((s, i) => (i === index ? { ...s, ...patch } : s)),
    }))
  }

  // Once a registration has succeeded we show the "result" card so the user can
  // verify discovered tools and either keep or roll back.
  if (registered) {
    return (
      <Card className="border-emerald-300 dark:border-emerald-800">
        <CardHeader>
          <CardTitle className="flex items-center gap-2 text-base">
            <CheckCircle2 className="h-4 w-4 text-emerald-600 dark:text-emerald-400" />
            {t("mcp.registerSuccessTitle", { name: registered.name })}
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-3 text-sm">
          <p className="text-muted-foreground">
            {t("mcp.registerSuccessBody", { count: registered.tools.length })}
          </p>
          {registered.tools.length > 0 ? (
            <ul className="space-y-1 rounded border border-border bg-muted/30 p-2">
              {registered.tools.map((tool) => (
                <li key={tool.tool_name} className="font-mono text-xs">
                  {tool.tool_name}
                  {tool.capabilities.length > 0 ? (
                    <span className="ml-2 text-muted-foreground">
                      [{tool.capabilities.join(", ")}]
                    </span>
                  ) : null}
                </li>
              ))}
            </ul>
          ) : (
            <p className="text-xs text-amber-600 dark:text-amber-400">{t("mcp.registerNoTools")}</p>
          )}
          <div className="flex gap-2 pt-1">
            <Button
              type="button"
              size="sm"
              onClick={() => {
                setRegistered(null)
                setForm(EMPTY_FORM)
                onClose()
              }}
            >
              {t("mcp.keep")}
            </Button>
            <Button
              type="button"
              size="sm"
              variant="outline"
              disabled={rollback.isPending}
              onClick={() => {
                rollback.mutate(registered.id)
              }}
            >
              <Trash2 className="h-4 w-4" /> {t("mcp.discard")}
            </Button>
          </div>
        </CardContent>
      </Card>
    )
  }

  return (
    <Card>
      <CardHeader>
        <div className="flex items-start justify-between gap-2">
          <CardTitle className="text-base">{t("mcp.registerTitle")}</CardTitle>
          <Button type="button" variant="outline" size="sm" onClick={onClose}>
            <X className="h-4 w-4" />
          </Button>
        </div>
      </CardHeader>
      <CardContent>
        <form
          className="space-y-4"
          onSubmit={(e) => {
            e.preventDefault()
            register.mutate()
          }}
        >
          <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
            <div className="space-y-1.5">
              <Label>{t("mcp.fieldName")}</Label>
              <Input
                value={form.name}
                onChange={(e) => {
                  set("name", e.target.value)
                }}
                required
                placeholder="my-arxiv"
              />
            </div>
            <div className="space-y-1.5">
              <Label>{t("mcp.fieldScope")}</Label>
              <select
                className="flex h-9 w-full rounded-md border border-input bg-background px-2 py-1 text-sm ring-offset-background focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                value={form.scope}
                onChange={(e) => {
                  set("scope", e.target.value as MCPScope)
                }}
              >
                <option value="user">{t("mcp.scopeUserDesc")}</option>
                {isAdmin ? <option value="admin">{t("mcp.scopeAdminDesc")}</option> : null}
              </select>
            </div>
            <div className="space-y-1.5">
              <Label>{t("mcp.fieldTransport")}</Label>
              <select
                className="flex h-9 w-full rounded-md border border-input bg-background px-2 py-1 text-sm ring-offset-background focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                value={form.transport}
                onChange={(e) => {
                  set("transport", e.target.value as MCPTransport)
                }}
              >
                <option value="stdio">stdio</option>
                <option value="http">http</option>
                <option value="inprocess">inprocess</option>
              </select>
            </div>
            <div className="space-y-1.5">
              <Label>{t("mcp.fieldDeclaredCaps")}</Label>
              <Input
                value={form.declared_capabilities}
                onChange={(e) => {
                  set("declared_capabilities", e.target.value)
                }}
                placeholder="paper_search, paper_fetch"
              />
            </div>
          </div>

          {form.transport === "stdio" ? (
            <div className="space-y-1.5">
              <Label>{t("mcp.fieldCommand")}</Label>
              <Input
                value={form.command}
                onChange={(e) => {
                  set("command", e.target.value)
                }}
                required
                placeholder="uvx my-mcp-server --flag value"
                className="font-mono text-sm"
              />
              <p className="text-xs text-muted-foreground">{t("mcp.fieldCommandHint")}</p>
            </div>
          ) : null}

          {form.transport === "http" ? (
            <div className="space-y-1.5">
              <Label>{t("mcp.fieldUrl")}</Label>
              <Input
                value={form.url}
                onChange={(e) => {
                  set("url", e.target.value)
                }}
                required
                placeholder="https://mcp.example.com/streamable"
                className="font-mono text-sm"
              />
            </div>
          ) : null}

          {form.transport === "inprocess" ? (
            <div className="space-y-1.5">
              <Label>{t("mcp.fieldInprocessKey")}</Label>
              <Input
                value={form.inprocess_key}
                onChange={(e) => {
                  set("inprocess_key", e.target.value)
                }}
                required
                placeholder="memory_server"
                className="font-mono text-sm"
              />
              <p className="text-xs text-muted-foreground">{t("mcp.fieldInprocessKeyHint")}</p>
            </div>
          ) : null}

          <div className="space-y-2">
            <div className="flex items-center justify-between">
              <Label>{t("mcp.fieldSlots")}</Label>
              <Button type="button" variant="outline" size="sm" onClick={addSlot}>
                {t("mcp.addSlot")}
              </Button>
            </div>
            {form.slots.length === 0 ? (
              <p className="text-xs text-muted-foreground">{t("mcp.slotsHint")}</p>
            ) : (
              <ul className="space-y-2">
                {form.slots.map((slot, idx) => (
                  <li key={idx} className="flex flex-wrap items-end gap-2">
                    <div className="flex-1 min-w-[140px] space-y-1">
                      <Label className="text-xs">{t("mcp.slotRef")}</Label>
                      <Input
                        value={slot.ref}
                        onChange={(e) => {
                          patchSlot(idx, { ref: e.target.value })
                        }}
                        placeholder="user:key:semantic_scholar"
                        className="font-mono text-xs"
                      />
                    </div>
                    <div className="flex-1 min-w-[180px] space-y-1">
                      <Label className="text-xs">{t("mcp.slotValue")}</Label>
                      <Input
                        type="password"
                        value={slot.value}
                        onChange={(e) => {
                          patchSlot(idx, { value: e.target.value })
                        }}
                        placeholder={t("mcp.slotValuePlaceholder")}
                        autoComplete="off"
                      />
                    </div>
                    <Button
                      type="button"
                      variant="outline"
                      size="sm"
                      onClick={() => {
                        removeSlot(idx)
                      }}
                    >
                      <X className="h-4 w-4" />
                    </Button>
                  </li>
                ))}
              </ul>
            )}
            {form.scope === "admin" ? (
              <p className="rounded border border-amber-300 bg-amber-50 p-2 text-xs text-amber-800 dark:border-amber-800 dark:bg-amber-950 dark:text-amber-300">
                {t("mcp.adminSlotWarning")}
              </p>
            ) : null}
          </div>

          {register.error ? (
            <div className="rounded border border-red-300 bg-red-50 p-2 text-sm text-red-700 dark:border-red-800 dark:bg-red-950 dark:text-red-400">
              {register.error.message}
            </div>
          ) : null}

          <div className="flex items-center gap-2">
            <Button type="submit" disabled={register.isPending}>
              {register.isPending ? (
                <>
                  <Loader2 className="h-4 w-4 animate-spin" />
                  {t("mcp.registering")}
                </>
              ) : (
                t("mcp.registerAndTest")
              )}
            </Button>
            <p className="text-xs text-muted-foreground">{t("mcp.registerHint")}</p>
          </div>
        </form>
      </CardContent>
    </Card>
  )
}
