import { useQuery } from "@tanstack/react-query"
import * as React from "react"
import { useTranslation } from "react-i18next"
import { useNavigate } from "react-router-dom"
import { toast } from "sonner"

import { api } from "@/api/client"
import { useAuth } from "@/auth/AuthProvider"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { PasswordInput } from "@/components/ui/password-input"

export function LoginPage(): React.JSX.Element {
  const { t } = useTranslation()
  const bootstrap = useQuery({
    queryKey: ["bootstrap-status"],
    queryFn: api.bootstrapStatus,
  })
  const needsBootstrap = bootstrap.data?.needs_bootstrap ?? false

  // `override` is the user's explicit choice via the toggle button; when null,
  // mode derives from server state (register on fresh installs, login otherwise).
  const [override, setOverride] = React.useState<"login" | "register" | null>(null)
  const mode: "login" | "register" = override ?? (needsBootstrap ? "register" : "login")

  const [email, setEmail] = React.useState("")
  const [displayName, setDisplayName] = React.useState("")
  const [passphrase, setPassphrase] = React.useState("")
  const [rememberMe, setRememberMe] = React.useState(false)
  const [error, setError] = React.useState<string | null>(null)
  const { identity, refresh } = useAuth()
  const nav = useNavigate()

  // Already logged in — redirect away from the login page.
  React.useEffect(() => {
    if (identity) nav("/runs", { replace: true })
  }, [identity, nav])

  async function submit(e: React.SyntheticEvent<HTMLFormElement>): Promise<void> {
    e.preventDefault()
    setError(null)
    try {
      if (mode === "register") {
        await api.register(displayName, email, passphrase)
        await api.login(email, passphrase, rememberMe)
      } else {
        await api.login(email, passphrase, rememberMe)
      }
      const me = await refresh()
      if (me) {
        nav("/settings")
      } else {
        setError(t("auth.sessionError"))
      }
    } catch (err) {
      const msg = err instanceof Error ? err.message : String(err)
      setError(msg)
      if (msg.startsWith("429:")) {
        toast.error(t("auth.tooManyAttempts"))
      }
    }
  }

  function toggleMode(): void {
    setOverride(mode === "register" ? "login" : "register")
    setError(null)
    setPassphrase("")
  }

  return (
    <div className="flex h-full items-center justify-center p-8">
      <div className="w-full max-w-md space-y-4">
        <Card>
          <CardHeader>
            <CardTitle>
              {mode === "register" ? t("auth.register") : t("auth.login")}
            </CardTitle>
          </CardHeader>
          <CardContent>
            <form
              onSubmit={(e) => {
                void submit(e)
              }}
              className="space-y-4"
            >
              {mode === "register" ? (
                <div className="space-y-2">
                  <Label>{t("auth.displayName")}</Label>
                  <Input
                    value={displayName}
                    onChange={(e) => {
                      setDisplayName(e.target.value)
                    }}
                    required
                    autoComplete="name"
                  />
                </div>
              ) : null}
              <div className="space-y-2">
                <Label>{t("auth.email")}</Label>
                <Input
                  type="email"
                  value={email}
                  onChange={(e) => {
                    setEmail(e.target.value)
                  }}
                  required
                  autoComplete="email"
                />
              </div>
              <div className="space-y-2">
                <Label>{t("auth.passphrase")}</Label>
                <PasswordInput
                  value={passphrase}
                  onChange={(e) => {
                    setPassphrase(e.target.value)
                  }}
                  required
                  minLength={8}
                  autoComplete={
                    mode === "register" ? "new-password" : "current-password"
                  }
                />
              </div>
              <label className="flex items-center gap-2 text-sm">
                <input
                  type="checkbox"
                  checked={rememberMe}
                  onChange={(e) => { setRememberMe(e.target.checked) }}
                  className="h-4 w-4 rounded border-input accent-foreground"
                />
                {t("auth.rememberMe")}
              </label>
              {error ? (
                <div className="rounded border border-red-200 bg-red-50 p-2 text-sm text-red-700 dark:border-red-800 dark:bg-red-950 dark:text-red-400">
                  {error}
                </div>
              ) : null}
              <div className="flex items-center justify-between">
                <Button type="submit">
                  {mode === "register" ? t("auth.loginAndCreate") : t("auth.login")}
                </Button>
                <Button type="button" variant="ghost" onClick={toggleMode}>
                  {mode === "register" ? t("auth.existingLogin") : t("auth.needRegister")}
                </Button>
              </div>
            </form>
          </CardContent>
        </Card>
        {mode === "login" ? (
          <p className="px-1 text-xs text-muted-foreground">
            {t("auth.forgotHint", {
              command: "agentlabx reset-passphrase --email YOUR_EMAIL",
            })}
          </p>
        ) : null}
        {!needsBootstrap && mode === "login" ? (
          <p className="px-1 text-xs text-muted-foreground">
            {t("auth.needAccountHint")}
          </p>
        ) : null}
      </div>
    </div>
  )
}
