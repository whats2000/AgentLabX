import { useQuery } from "@tanstack/react-query"
import * as React from "react"
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
  const [error, setError] = React.useState<string | null>(null)
  const { refresh } = useAuth()
  const nav = useNavigate()

  async function submit(e: React.FormEvent<HTMLFormElement>): Promise<void> {
    e.preventDefault()
    setError(null)
    try {
      if (mode === "register") {
        await api.register(displayName, email, passphrase)
        await api.login(email, passphrase)
      } else {
        await api.login(email, passphrase)
      }
      const me = await refresh()
      if (me) {
        nav("/settings")
      } else {
        setError("login succeeded but session was not established; please try again")
      }
    } catch (err) {
      const msg = err instanceof Error ? err.message : String(err)
      setError(msg)
      if (msg.startsWith("429:")) {
        toast.error("Too many failed attempts — try again later")
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
              {mode === "register" ? "Create first identity" : "Log in"}
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
                  <Label>Display name</Label>
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
                <Label>Email</Label>
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
                <Label>Passphrase</Label>
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
              {error ? (
                <div className="rounded border border-red-200 bg-red-50 p-2 text-sm text-red-700">
                  {error}
                </div>
              ) : null}
              <div className="flex items-center justify-between">
                <Button type="submit">
                  {mode === "register" ? "Create & log in" : "Log in"}
                </Button>
                <Button type="button" variant="ghost" onClick={toggleMode}>
                  {mode === "register" ? "Existing? Log in" : "Need to register?"}
                </Button>
              </div>
            </form>
          </CardContent>
        </Card>
        {mode === "login" ? (
          <p className="px-1 text-xs text-slate-400">
            Forgot your passphrase? Run{" "}
            <code className="rounded bg-slate-100 px-1 text-slate-600">
              agentlabx reset-passphrase --email YOUR_EMAIL
            </code>{" "}
            from the server shell.
          </p>
        ) : null}
        {!needsBootstrap && mode === "login" ? (
          <p className="px-1 text-xs text-slate-400">
            Need an account? Ask an admin to provision one for you.
          </p>
        ) : null}
      </div>
    </div>
  )
}
