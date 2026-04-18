import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import * as React from "react"
import { useTranslation } from "react-i18next"
import { toast } from "sonner"

import { api, type CredentialSlotDto } from "@/api/client"
import { useAuth } from "@/auth/AuthProvider"
import { ConfirmDialog } from "@/components/confirm-dialog"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { PasswordInput } from "@/components/ui/password-input"

export function SettingsPage(): React.JSX.Element {
  const { t } = useTranslation()
  const qc = useQueryClient()
  const { identity } = useAuth()
  const slots = useQuery<CredentialSlotDto[]>({
    queryKey: ["credentials"],
    queryFn: api.listCredentials,
  })

  const [slot, setSlot] = React.useState("")
  const [value, setValue] = React.useState("")
  const [revealed, setRevealed] = React.useState<Record<string, string>>({})

  const put = useMutation({
    mutationFn: () => api.putCredential(slot, value),
    onSuccess: () => {
      setSlot("")
      setValue("")
      void qc.invalidateQueries({ queryKey: ["credentials"] })
      toast.success(t("settings.credentialSaved"))
    },
    onError: (err: Error) => { toast.error(err.message) },
  })
  const del = useMutation({
    mutationFn: (s: string) => api.deleteCredential(s),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ["credentials"] })
      toast.success(t("settings.credentialDeleted"))
    },
    onError: (err: Error) => { toast.error(err.message) },
  })

  return (
    <div className="max-w-3xl space-y-6">
      <h1 className="text-2xl font-semibold">{t("settings.title")}</h1>
      <Card>
        <CardHeader>
          <CardTitle>{t("settings.addUpdate")}</CardTitle>
        </CardHeader>
        <CardContent>
          <form
            className="space-y-4"
            onSubmit={(e) => {
              e.preventDefault()
              put.mutate()
            }}
          >
            <div className="space-y-2">
              <Label>{t("settings.slotLabel")}</Label>
              <Input
                value={slot}
                onChange={(e) => { setSlot(e.target.value) }}
                list="provider-suggestions"
                required
              />
              <datalist id="provider-suggestions">
                <option value="openai" />
                <option value="anthropic" />
                <option value="gemini" />
                <option value="azure" />
                <option value="vertex_ai" />
                <option value="bedrock" />
                <option value="deepseek" />
                <option value="ollama" />
                <option value="together_ai" />
                <option value="groq" />
                <option value="mistral" />
                <option value="cohere" />
                <option value="huggingface" />
                <option value="openrouter" />
                <option value="xai" />
              </datalist>
            </div>
            <div className="space-y-2">
              <Label>{t("settings.valueLabel")}</Label>
              <PasswordInput
                value={value}
                onChange={(e) => { setValue(e.target.value) }}
                required
              />
            </div>
            {put.error ? (
              <div className="rounded border border-red-200 bg-red-50 p-2 text-sm text-red-700 dark:border-red-800 dark:bg-red-950 dark:text-red-400">
                {put.error.message}
              </div>
            ) : null}
            <Button type="submit" disabled={put.isPending}>{t("settings.saveButton")}</Button>
            <p className="mt-3 text-xs text-muted-foreground">
              {t("settings.providerHint")}{" "}
              <a
                href="https://docs.litellm.ai/docs/providers"
                target="_blank"
                rel="noopener noreferrer"
                className="underline hover:text-foreground"
              >
                LiteLLM Providers ↗
              </a>
            </p>
          </form>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>{t("settings.storedCredentials")}</CardTitle>
        </CardHeader>
        <CardContent>
          {del.error ? (
            <div className="mb-4 rounded border border-red-200 bg-red-50 p-2 text-sm text-red-700 dark:border-red-800 dark:bg-red-950 dark:text-red-400">
              {del.error.message}
            </div>
          ) : null}
          {slots.isLoading ? (
            <div className="text-sm text-muted-foreground">{t("common.loading")}</div>
          ) : slots.data && slots.data.length > 0 ? (
            <ul className="divide-y divide-border">
              {slots.data.map((s) => (
                <li key={s.slot} className="flex items-center justify-between py-2 min-w-0">
                  <div className="min-w-0 flex-1">
                    <div className="font-medium">{s.slot}</div>
                    <div className="text-xs text-muted-foreground">{t("settings.updatedAt", { date: s.updated_at })}</div>
                    {revealed[s.slot] ? (
                      <div className="mt-1 font-mono text-xs break-all">{revealed[s.slot]}</div>
                    ) : null}
                  </div>
                  <div className="flex gap-2">
                    <Button
                      variant="outline"
                      size="sm"
                      onClick={() => {
                        void api.revealCredential(s.slot).then((r) => {
                          setRevealed((prev) => ({ ...prev, [s.slot]: r.value }))
                        })
                      }}
                    >
                      {t("common.reveal")}
                    </Button>
                    <ConfirmDialog
                      trigger={<Button variant="outline" size="sm">{t("common.delete")}</Button>}
                      title={t("settings.deleteCredentialTitle")}
                      description={
                        <>{t("settings.deleteCredentialDesc", { slot: s.slot })}</>
                      }
                      confirmLabel={t("common.delete")}
                      destructive
                      onConfirm={() => { del.mutate(s.slot) }}
                    />
                  </div>
                </li>
              ))}
            </ul>
          ) : (
            <div className="text-sm text-muted-foreground">{t("settings.noCredentials")}</div>
          )}
        </CardContent>
      </Card>

      {identity?.capabilities.includes("admin") ? (
        <div className="text-sm text-muted-foreground">
          {t("settings.adminHint")}
        </div>
      ) : null}
    </div>
  )
}
