import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import * as React from "react"

import { api, type CredentialSlotDto } from "@/api/client"
import { useAuth } from "@/auth/AuthProvider"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"

export function SettingsPage(): React.JSX.Element {
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
    },
  })
  const del = useMutation({
    mutationFn: (s: string) => api.deleteCredential(s),
    onSuccess: () => { void qc.invalidateQueries({ queryKey: ["credentials"] }) },
  })

  return (
    <div className="max-w-3xl space-y-6">
      <h1 className="text-2xl font-semibold">Credentials</h1>
      <Card>
        <CardHeader>
          <CardTitle>Add / update a credential</CardTitle>
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
              <Label>Slot (e.g., "anthropic")</Label>
              <Input value={slot} onChange={(e) => { setSlot(e.target.value) }} required />
            </div>
            <div className="space-y-2">
              <Label>Value</Label>
              <Input
                type="password"
                value={value}
                onChange={(e) => { setValue(e.target.value) }}
                required
              />
            </div>
            <Button type="submit" disabled={put.isPending}>Save</Button>
          </form>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Stored credentials</CardTitle>
        </CardHeader>
        <CardContent>
          {slots.isLoading ? (
            <div className="text-sm text-slate-500">Loading…</div>
          ) : slots.data && slots.data.length > 0 ? (
            <ul className="divide-y">
              {slots.data.map((s) => (
                <li key={s.slot} className="flex items-center justify-between py-2">
                  <div>
                    <div className="font-medium">{s.slot}</div>
                    <div className="text-xs text-slate-500">updated {s.updated_at}</div>
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
                      Reveal
                    </Button>
                    <Button
                      variant="outline"
                      size="sm"
                      onClick={() => { del.mutate(s.slot) }}
                    >
                      Delete
                    </Button>
                  </div>
                </li>
              ))}
            </ul>
          ) : (
            <div className="text-sm text-slate-500">No credentials yet.</div>
          )}
        </CardContent>
      </Card>

      {identity?.capabilities.includes("admin") ? (
        <div className="text-sm text-slate-500">
          You are an admin. Visit the <strong>Admin users</strong> tab to provision identities.
        </div>
      ) : null}
    </div>
  )
}
