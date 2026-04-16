import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import * as React from "react"
import { toast } from "sonner"

import { api, type IssuedTokenDto, type SessionDto, type TokenRecordDto } from "@/api/client"
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
    onSuccess: () => {
      void refresh()
      toast.success("Display name updated")
    },
    onError: (err: Error) => { toast.error(err.message) },
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
      toast.success("Email updated")
    },
    onError: (err: Error) => { toast.error(err.message) },
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
      toast.success("Passphrase changed")
    },
    onError: (err: Error) => { toast.error(err.message) },
  })

  // Sessions
  const sessions = useQuery<SessionDto[]>({
    queryKey: ["my-sessions"],
    queryFn: api.listMySessions,
  })

  const revokeSession = useMutation({
    mutationFn: (session_id: string) => api.revokeMySession(session_id),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ["my-sessions"] })
      toast.success("Session revoked")
    },
    onError: (err: Error) => { toast.error(err.message) },
  })

  // API tokens
  const [tokenLabel, setTokenLabel] = React.useState("")
  const [newlyIssuedToken, setNewlyIssuedToken] = React.useState<IssuedTokenDto | null>(null)

  const tokens = useQuery<TokenRecordDto[]>({
    queryKey: ["my-tokens"],
    queryFn: api.listMyTokens,
  })

  const issueToken = useMutation({
    mutationFn: () => api.issueMyToken(tokenLabel),
    onSuccess: (issued) => {
      setNewlyIssuedToken(issued)
      setTokenLabel("")
      void qc.invalidateQueries({ queryKey: ["my-tokens"] })
      toast.success("Token issued")
    },
    onError: (err: Error) => { toast.error(err.message) },
  })

  const revokeToken = useMutation({
    mutationFn: (token_id: string) => api.revokeMyToken(token_id),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ["my-tokens"] })
      toast.success("Token revoked")
    },
    onError: (err: Error) => { toast.error(err.message) },
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

      {/* Personal API tokens */}
      <Card>
        <CardHeader>
          <CardTitle>Personal API tokens</CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          <p className="text-sm text-slate-500">
            Use these tokens to authenticate with{" "}
            <code className="rounded bg-slate-100 px-1 py-0.5 text-xs">
              Authorization: Bearer &lt;token&gt;
            </code>{" "}
            from scripts or other clients.
          </p>

          {/* Issue form */}
          <form
            className="flex gap-2"
            onSubmit={(e) => {
              e.preventDefault()
              issueToken.mutate()
            }}
          >
            <Input
              placeholder="Token label (e.g. ci-key)"
              value={tokenLabel}
              onChange={(e) => { setTokenLabel(e.target.value) }}
              required
              minLength={1}
              maxLength={128}
              className="flex-1"
            />
            <Button type="submit" disabled={issueToken.isPending || tokenLabel.trim().length === 0}>
              Issue token
            </Button>
          </form>

          {issueToken.error ? (
            <div className="rounded border border-red-200 bg-red-50 p-2 text-sm text-red-700">
              {issueToken.error.message}
            </div>
          ) : null}

          {/* One-shot reveal banner */}
          {newlyIssuedToken ? (
            <div className="rounded border border-amber-300 bg-amber-50 p-3 space-y-2">
              <p className="text-sm font-medium text-amber-800">
                Copy now — it will not be shown again.
              </p>
              <div className="flex items-center gap-2">
                <code className="flex-1 break-all rounded bg-white px-2 py-1 text-xs border border-amber-200 text-slate-800">
                  {newlyIssuedToken.token}
                </code>
                <Button
                  size="sm"
                  variant="outline"
                  type="button"
                  onClick={() => {
                    void navigator.clipboard.writeText(newlyIssuedToken.token)
                  }}
                >
                  Copy
                </Button>
                <Button
                  size="sm"
                  variant="ghost"
                  type="button"
                  onClick={() => { setNewlyIssuedToken(null) }}
                >
                  Dismiss
                </Button>
              </div>
              <p className="text-xs text-amber-700">Label: {newlyIssuedToken.label}</p>
            </div>
          ) : null}

          {/* Token list */}
          {tokens.isLoading ? (
            <p className="text-sm text-slate-500">Loading tokens…</p>
          ) : tokens.error ? (
            <p className="text-sm text-red-600">{tokens.error.message}</p>
          ) : (tokens.data ?? []).length === 0 ? (
            <p className="text-sm text-slate-400">No tokens issued yet.</p>
          ) : (
            <ul className="divide-y">
              {(tokens.data ?? []).map((t: TokenRecordDto) => (
                <li key={t.id} className="flex items-start justify-between gap-4 py-3">
                  <div className="space-y-0.5 text-sm">
                    <div className="flex items-center gap-2">
                      <span className="font-medium text-slate-800">{t.label}</span>
                      {t.revoked ? (
                        <span className="rounded-full bg-red-100 px-2 py-0.5 text-xs font-medium text-red-700">
                          revoked
                        </span>
                      ) : null}
                    </div>
                    <div className="text-slate-500">Created: {t.created_at}</div>
                    <div className="text-slate-500">
                      Last used: {t.last_used_at ?? "never used"}
                    </div>
                  </div>
                  {!t.revoked ? (
                    <ConfirmDialog
                      trigger={
                        <Button
                          variant="destructive"
                          size="sm"
                          disabled={revokeToken.isPending}
                        >
                          Revoke
                        </Button>
                      }
                      title="Revoke token?"
                      description={`Token "${t.label}" will be permanently revoked. Any scripts using it will stop working.`}
                      confirmLabel="Revoke"
                      destructive
                      onConfirm={() => { revokeToken.mutate(t.id) }}
                    />
                  ) : null}
                </li>
              ))}
            </ul>
          )}

          {revokeToken.error ? (
            <div className="rounded border border-red-200 bg-red-50 p-2 text-sm text-red-700">
              {revokeToken.error.message}
            </div>
          ) : null}
        </CardContent>
      </Card>
    </div>
  )
}
