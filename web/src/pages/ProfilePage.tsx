import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import * as React from "react"
import { useTranslation } from "react-i18next"
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
  const { t } = useTranslation()
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
      toast.success(t("profile.displayNameUpdated"))
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
      toast.success(t("profile.emailUpdated"))
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
      toast.success(t("profile.passphraseChanged"))
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
      toast.success(t("profile.sessionRevoked"))
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
      toast.success(t("profile.tokenIssued"))
    },
    onError: (err: Error) => { toast.error(err.message) },
  })

  const deleteToken = useMutation({
    mutationFn: (token_id: string) => api.deleteMyToken(token_id),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ["my-tokens"] })
      toast.success(t("profile.tokenDeleted"))
    },
    onError: (err: Error) => { toast.error(err.message) },
  })

  const refreshToken = useMutation({
    mutationFn: (token_id: string) => api.refreshMyToken(token_id),
    onSuccess: (issued) => {
      setNewlyIssuedToken(issued)
      void qc.invalidateQueries({ queryKey: ["my-tokens"] })
      toast.success(t("profile.tokenRefreshed"))
    },
    onError: (err: Error) => { toast.error(err.message) },
  })

  return (
    <div className="max-w-3xl space-y-6">
      <h1 className="text-2xl font-semibold">{t("profile.title")}</h1>
      <Card>
        <CardHeader>
          <CardTitle>{t("profile.cardTitle")}</CardTitle>
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
              <Label>{t("profile.displayNameLabel")}</Label>
              <Input
                value={displayName}
                onChange={(e) => { setDisplayName(e.target.value) }}
                required
                minLength={1}
                maxLength={128}
              />
            </div>
            {updateName.error ? (
              <div className="rounded border border-red-200 bg-red-50 p-2 text-sm text-red-700 dark:border-red-800 dark:bg-red-950 dark:text-red-400">
                {updateName.error.message}
              </div>
            ) : null}
            <Button type="submit" disabled={updateName.isPending}>{t("profile.saveDisplayName")}</Button>
          </form>

          <hr className="border-border" />

          {/* Email */}
          <form
            className="space-y-4"
            onSubmit={(e) => {
              e.preventDefault()
              updateEmail.mutate()
            }}
          >
            <div className="space-y-2">
              <Label>{t("profile.newEmailLabel")}</Label>
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
              <Label>{t("profile.currentPassphraseLabel")}</Label>
              <PasswordInput
                value={emailPass}
                onChange={(e) => { setEmailPass(e.target.value) }}
                required
              />
            </div>
            {updateEmail.error ? (
              <div className="rounded border border-red-200 bg-red-50 p-2 text-sm text-red-700 dark:border-red-800 dark:bg-red-950 dark:text-red-400">
                {updateEmail.error.message}
              </div>
            ) : null}
            <Button type="submit" disabled={updateEmail.isPending}>{t("profile.saveEmail")}</Button>
          </form>

          <hr className="border-border" />

          {/* Passphrase */}
          <form
            className="space-y-4"
            onSubmit={(e) => {
              e.preventDefault()
              updatePass.mutate()
            }}
          >
            <div className="space-y-2">
              <Label>{t("profile.currentPassphraseLabel")}</Label>
              <PasswordInput
                value={oldP}
                onChange={(e) => { setOldP(e.target.value) }}
                required
              />
            </div>
            <div className="space-y-2">
              <Label>{t("profile.newPassphraseLabel")}</Label>
              <PasswordInput
                value={newP}
                onChange={(e) => { setNewP(e.target.value) }}
                required
                minLength={8}
                maxLength={256}
              />
            </div>
            <div className="space-y-2">
              <Label>{t("profile.confirmNewPassphraseLabel")}</Label>
              <PasswordInput
                value={confirmP}
                onChange={(e) => { setConfirmP(e.target.value) }}
                required
              />
            </div>
            {mismatch ? (
              <div className="text-sm text-red-600 dark:text-red-400">{t("profile.passphraseMismatch")}</div>
            ) : null}
            {updatePass.error ? (
              <div className="rounded border border-red-200 bg-red-50 p-2 text-sm text-red-700 dark:border-red-800 dark:bg-red-950 dark:text-red-400">
                {updatePass.error.message}
              </div>
            ) : null}
            <Button
              type="submit"
              disabled={updatePass.isPending || mismatch || newP.length < 8}
            >
              {t("profile.savePassphrase")}
            </Button>
          </form>
        </CardContent>
      </Card>

      {/* Active sessions */}
      <Card>
        <CardHeader>
          <CardTitle>{t("profile.activeSessions")}</CardTitle>
        </CardHeader>
        <CardContent>
          {sessions.isLoading ? (
            <p className="text-sm text-muted-foreground">{t("profile.loadingSessions")}</p>
          ) : sessions.error ? (
            <p className="text-sm text-red-600 dark:text-red-400">{sessions.error.message}</p>
          ) : (
            <ul className="divide-y divide-border">
              {(sessions.data ?? []).map((s) => (
                <li key={s.id} className="flex items-start justify-between gap-4 py-3">
                  <div className="space-y-0.5 text-sm">
                    <div className="flex items-center gap-2">
                      <span className="text-foreground">{t("profile.signedIn", { date: s.issued_at })}</span>
                      {s.is_current ? (
                        <span className="rounded-full bg-blue-100 px-2 py-0.5 text-xs font-medium text-blue-700 dark:bg-blue-900 dark:text-blue-300">
                          {t("profile.thisDevice")}
                        </span>
                      ) : null}
                    </div>
                    <div className="text-muted-foreground">{t("profile.lastSeen", { date: s.last_seen_at })}</div>
                    <div className="text-muted-foreground">{t("profile.expires", { date: s.expires_at })}</div>
                  </div>
                  <ConfirmDialog
                    trigger={
                      <Button
                        variant="destructive"
                        size="sm"
                        disabled={revokeSession.isPending}
                      >
                        {s.is_current ? t("profile.signOutHere") : t("profile.signOutDevice")}
                      </Button>
                    }
                    title={s.is_current ? t("profile.signOutHereTitle") : t("profile.signOutDeviceTitle")}
                    description={
                      s.is_current
                        ? t("profile.signOutHereDesc")
                        : t("profile.signOutDeviceDesc")
                    }
                    confirmLabel={s.is_current ? t("profile.signOutConfirm") : t("common.revoke")}
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
          <CardTitle>{t("profile.personalTokens")}</CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          <p className="text-sm text-muted-foreground">
            {t("profile.tokensDesc", {
              header: "Authorization: Bearer <token>",
            })}
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
              placeholder={t("profile.tokenLabelPlaceholder")}
              value={tokenLabel}
              onChange={(e) => { setTokenLabel(e.target.value) }}
              required
              minLength={1}
              maxLength={128}
              className="flex-1"
            />
            <Button type="submit" disabled={issueToken.isPending || tokenLabel.trim().length === 0}>
              {t("profile.issueToken")}
            </Button>
          </form>

          {issueToken.error ? (
            <div className="rounded border border-red-200 bg-red-50 p-2 text-sm text-red-700 dark:border-red-800 dark:bg-red-950 dark:text-red-400">
              {issueToken.error.message}
            </div>
          ) : null}

          {/* One-shot reveal banner */}
          {newlyIssuedToken ? (
            <div className="rounded border border-amber-300 bg-amber-50 p-3 space-y-2 dark:border-amber-700 dark:bg-amber-950">
              <p className="text-sm font-medium text-amber-800 dark:text-amber-300">
                {t("profile.copyNow")}
              </p>
              <div className="flex items-center gap-2">
                <code className="flex-1 break-all rounded bg-card px-2 py-1 text-xs border border-border text-foreground">
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
                  {t("common.copy")}
                </Button>
                <Button
                  size="sm"
                  variant="ghost"
                  type="button"
                  onClick={() => { setNewlyIssuedToken(null) }}
                >
                  {t("common.dismiss")}
                </Button>
              </div>
              <p className="text-xs text-amber-700 dark:text-amber-400">{t("profile.tokenLabel", { label: newlyIssuedToken.label })}</p>
            </div>
          ) : null}

          {/* Token list */}
          {tokens.isLoading ? (
            <p className="text-sm text-muted-foreground">{t("profile.loadingTokens")}</p>
          ) : tokens.error ? (
            <p className="text-sm text-red-600 dark:text-red-400">{tokens.error.message}</p>
          ) : (tokens.data ?? []).length === 0 ? (
            <p className="text-sm text-muted-foreground">{t("profile.noTokens")}</p>
          ) : (
            <ul className="divide-y divide-border">
              {(tokens.data ?? []).map((tk: TokenRecordDto) => (
                <li key={tk.id} className="flex items-start justify-between gap-4 py-3">
                  <div className="space-y-0.5 text-sm">
                    <div className="font-medium text-foreground">{tk.label}</div>
                    <div className="text-muted-foreground">{t("profile.createdAt", { date: tk.created_at })}</div>
                    <div className="text-muted-foreground">
                      {t("profile.lastUsed", { date: tk.last_used_at ?? t("profile.neverUsed") })}
                    </div>
                  </div>
                  <div className="flex gap-2">
                    <ConfirmDialog
                      trigger={
                        <Button
                          variant="outline"
                          size="sm"
                          disabled={refreshToken.isPending}
                        >
                          {t("profile.refreshToken")}
                        </Button>
                      }
                      title={t("profile.refreshTokenTitle")}
                      description={t("profile.refreshTokenDesc", { label: tk.label })}
                      confirmLabel={t("profile.refreshToken")}
                      onConfirm={() => { refreshToken.mutate(tk.id) }}
                    />
                    <ConfirmDialog
                      trigger={
                        <Button
                          variant="destructive"
                          size="sm"
                          disabled={deleteToken.isPending}
                        >
                          {t("profile.deleteToken")}
                        </Button>
                      }
                      title={t("profile.deleteTokenTitle")}
                      description={t("profile.deleteTokenDesc", { label: tk.label })}
                      confirmLabel={t("common.delete")}
                      destructive
                      onConfirm={() => { deleteToken.mutate(tk.id) }}
                    />
                  </div>
                </li>
              ))}
            </ul>
          )}

          {deleteToken.error ? (
            <div className="rounded border border-red-200 bg-red-50 p-2 text-sm text-red-700 dark:border-red-800 dark:bg-red-950 dark:text-red-400">
              {deleteToken.error.message}
            </div>
          ) : null}
        </CardContent>
      </Card>
    </div>
  )
}
