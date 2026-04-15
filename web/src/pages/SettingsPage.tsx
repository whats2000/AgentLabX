import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import * as React from "react"

import { api, type CredentialSlotDto } from "@/api/client"
import { useAuth } from "@/auth/AuthProvider"
import { ConfirmDialog } from "@/components/confirm-dialog"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { PasswordInput } from "@/components/ui/password-input"

export function SettingsPage(): React.JSX.Element {
  const qc = useQueryClient()
  const { identity, refresh } = useAuth()
  const slots = useQuery<CredentialSlotDto[]>({
    queryKey: ["credentials"],
    queryFn: api.listCredentials,
  })

  const [slot, setSlot] = React.useState("")
  const [value, setValue] = React.useState("")
  const [revealed, setRevealed] = React.useState<Record<string, string>>({})

  // Profile — display name
  const [displayName, setDisplayName] = React.useState("")
  React.useEffect(() => {
    if (identity) setDisplayName(identity.display_name)
  }, [identity])

  const updateName = useMutation({
    mutationFn: () => api.updateDisplayName(displayName),
    onSuccess: () => { void refresh() },
  })

  // Profile — email
  const [newEmail, setNewEmail] = React.useState("")
  const [emailPass, setEmailPass] = React.useState("")

  const updateEmail = useMutation({
    mutationFn: () => api.updateEmail(newEmail, emailPass),
    onSuccess: () => {
      setNewEmail("")
      setEmailPass("")
      void refresh()
    },
  })

  // Profile — passphrase
  const [oldP, setOldP] = React.useState("")
  const [newP, setNewP] = React.useState("")
  const [confirmP, setConfirmP] = React.useState("")
  const mismatch = newP !== "" && confirmP !== "" && newP !== confirmP

  const updatePass = useMutation({
    mutationFn: () => api.updatePassphrase(oldP, newP),
    onSuccess: () => {
      setOldP("")
      setNewP("")
      setConfirmP("")
      void refresh()
    },
  })

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
      <Card>
        <CardHeader>
          <CardTitle>Profile</CardTitle>
        </CardHeader>
        <CardContent className="space-y-6">
          {/* Display name */}
          <form
            className="space-y-4"
            onSubmit={(e) => {
              e.preventDefault()
              updateName.mutate()
            }}
          >
            <div className="space-y-2">
              <Label>Display name</Label>
              <Input
                value={displayName}
                onChange={(e) => { setDisplayName(e.target.value) }}
                required
                minLength={1}
                maxLength={128}
              />
            </div>
            {updateName.error ? (
              <div className="rounded border border-red-200 bg-red-50 p-2 text-sm text-red-700">
                {updateName.error.message}
              </div>
            ) : null}
            <Button type="submit" disabled={updateName.isPending}>Save display name</Button>
          </form>

          <hr />

          {/* Email */}
          <form
            className="space-y-4"
            onSubmit={(e) => {
              e.preventDefault()
              updateEmail.mutate()
            }}
          >
            <div className="space-y-2">
              <Label>New email</Label>
              <Input
                type="email"
                value={newEmail}
                onChange={(e) => { setNewEmail(e.target.value) }}
                required
                minLength={3}
                maxLength={320}
              />
            </div>
            <div className="space-y-2">
              <Label>Current passphrase</Label>
              <PasswordInput
                value={emailPass}
                onChange={(e) => { setEmailPass(e.target.value) }}
                required
              />
            </div>
            {updateEmail.error ? (
              <div className="rounded border border-red-200 bg-red-50 p-2 text-sm text-red-700">
                {updateEmail.error.message}
              </div>
            ) : null}
            <Button type="submit" disabled={updateEmail.isPending}>Save email</Button>
          </form>

          <hr />

          {/* Passphrase */}
          <form
            className="space-y-4"
            onSubmit={(e) => {
              e.preventDefault()
              updatePass.mutate()
            }}
          >
            <div className="space-y-2">
              <Label>Current passphrase</Label>
              <PasswordInput
                value={oldP}
                onChange={(e) => { setOldP(e.target.value) }}
                required
              />
            </div>
            <div className="space-y-2">
              <Label>New passphrase</Label>
              <PasswordInput
                value={newP}
                onChange={(e) => { setNewP(e.target.value) }}
                required
                minLength={8}
                maxLength={256}
              />
            </div>
            <div className="space-y-2">
              <Label>Confirm new passphrase</Label>
              <PasswordInput
                value={confirmP}
                onChange={(e) => { setConfirmP(e.target.value) }}
                required
              />
            </div>
            {mismatch ? (
              <div className="text-sm text-red-600">Passphrases do not match.</div>
            ) : null}
            {updatePass.error ? (
              <div className="rounded border border-red-200 bg-red-50 p-2 text-sm text-red-700">
                {updatePass.error.message}
              </div>
            ) : null}
            <Button
              type="submit"
              disabled={updatePass.isPending || mismatch || newP.length < 8}
            >
              Save passphrase
            </Button>
          </form>
        </CardContent>
      </Card>

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
              <PasswordInput
                value={value}
                onChange={(e) => { setValue(e.target.value) }}
                required
              />
            </div>
            {put.error ? (
              <div className="rounded border border-red-200 bg-red-50 p-2 text-sm text-red-700">
                {put.error.message}
              </div>
            ) : null}
            <Button type="submit" disabled={put.isPending}>Save</Button>
          </form>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Stored credentials</CardTitle>
        </CardHeader>
        <CardContent>
          {del.error ? (
            <div className="mb-4 rounded border border-red-200 bg-red-50 p-2 text-sm text-red-700">
              {del.error.message}
            </div>
          ) : null}
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
                    <ConfirmDialog
                      trigger={<Button variant="outline" size="sm">Delete</Button>}
                      title="Delete credential?"
                      description={
                        <>Delete credential slot <strong>{s.slot}</strong>. Any configured provider using this slot will stop working until you add it again.</>
                      }
                      confirmLabel="Delete"
                      destructive
                      onConfirm={() => { del.mutate(s.slot) }}
                    />
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
