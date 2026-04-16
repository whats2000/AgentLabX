import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import * as React from "react"

import { api, type SessionDto } from "@/api/client"
import { useAuth } from "@/auth/AuthProvider"
import { ConfirmDialog } from "@/components/confirm-dialog"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { PasswordInput } from "@/components/ui/password-input"

export function ProfilePage(): React.JSX.Element {
  const { identity, refresh } = useAuth()
  const qc = useQueryClient()

  // Display name
  const [displayName, setDisplayName] = React.useState("")
  React.useEffect(() => {
    if (identity) setDisplayName(identity.display_name)
  }, [identity])

  const updateName = useMutation({
    mutationFn: () => api.updateDisplayName(displayName),
    onSuccess: () => { void refresh() },
  })

  // Email
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

  // Passphrase
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

  // Sessions
  const sessions = useQuery<SessionDto[]>({
    queryKey: ["my-sessions"],
    queryFn: api.listMySessions,
  })

  const revokeSession = useMutation({
    mutationFn: (session_id: string) => api.revokeMySession(session_id),
    onSuccess: () => { void qc.invalidateQueries({ queryKey: ["my-sessions"] }) },
  })

  return (
    <div className="max-w-3xl space-y-6">
      <h1 className="text-2xl font-semibold">Profile</h1>
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

      {/* Active sessions */}
      <Card>
        <CardHeader>
          <CardTitle>Active sessions</CardTitle>
        </CardHeader>
        <CardContent>
          {sessions.isLoading ? (
            <p className="text-sm text-slate-500">Loading sessions…</p>
          ) : sessions.error ? (
            <p className="text-sm text-red-600">{sessions.error.message}</p>
          ) : (
            <ul className="divide-y">
              {(sessions.data ?? []).map((s) => (
                <li key={s.id} className="flex items-start justify-between gap-4 py-3">
                  <div className="space-y-0.5 text-sm">
                    <div className="flex items-center gap-2">
                      <span className="text-slate-700">Signed in: {s.issued_at}</span>
                      {s.is_current ? (
                        <span className="rounded-full bg-blue-100 px-2 py-0.5 text-xs font-medium text-blue-700">
                          this device
                        </span>
                      ) : null}
                    </div>
                    <div className="text-slate-500">Last seen: {s.last_seen_at}</div>
                    <div className="text-slate-500">Expires: {s.expires_at}</div>
                  </div>
                  <ConfirmDialog
                    trigger={
                      <Button
                        variant="destructive"
                        size="sm"
                        disabled={revokeSession.isPending}
                      >
                        {s.is_current ? "Sign out here" : "Sign out of that device"}
                      </Button>
                    }
                    title={s.is_current ? "Sign out here?" : "Sign out of that device?"}
                    description={
                      s.is_current
                        ? "You will be signed out of this device and redirected to the login page."
                        : "The session on that device will be revoked immediately."
                    }
                    confirmLabel={s.is_current ? "Sign out" : "Revoke"}
                    destructive
                    onConfirm={() => { revokeSession.mutate(s.id) }}
                  />
                </li>
              ))}
            </ul>
          )}
        </CardContent>
      </Card>
    </div>
  )
}
