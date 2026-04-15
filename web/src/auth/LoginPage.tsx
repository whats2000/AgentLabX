import * as React from "react"
import { useNavigate } from "react-router-dom"

import { api } from "@/api/client"
import { useAuth } from "@/auth/AuthProvider"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { PasswordInput } from "@/components/ui/password-input"

export function LoginPage(): React.JSX.Element {
  const [mode, setMode] = React.useState<"login" | "register">("register")
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
      refresh()
      nav("/settings")
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err))
    }
  }

  return (
    <div className="flex h-full items-center justify-center p-8">
      <Card className="w-full max-w-md">
        <CardHeader>
          <CardTitle>{mode === "register" ? "Create first identity" : "Log in"}</CardTitle>
        </CardHeader>
        <CardContent>
          <form onSubmit={(e) => { void submit(e) }} className="space-y-4">
            {mode === "register" ? (
              <div className="space-y-2">
                <Label>Display name</Label>
                <Input
                  value={displayName}
                  onChange={(e) => { setDisplayName(e.target.value) }}
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
                onChange={(e) => { setEmail(e.target.value) }}
                required
                autoComplete="email"
              />
            </div>
            <div className="space-y-2">
              <Label>Passphrase</Label>
              <PasswordInput
                value={passphrase}
                onChange={(e) => { setPassphrase(e.target.value) }}
                required
                minLength={8}
                autoComplete={mode === "register" ? "new-password" : "current-password"}
              />
            </div>
            {error ? (
              <div className="rounded border border-red-200 bg-red-50 p-2 text-sm text-red-700">
                {error}
              </div>
            ) : null}
            <div className="flex items-center justify-between">
              <Button type="submit">{mode === "register" ? "Create & log in" : "Log in"}</Button>
              <Button
                type="button"
                variant="ghost"
                onClick={() => { setMode(mode === "register" ? "login" : "register") }}
              >
                {mode === "register" ? "Existing? Log in" : "Need to register?"}
              </Button>
            </div>
          </form>
        </CardContent>
      </Card>
    </div>
  )
}
