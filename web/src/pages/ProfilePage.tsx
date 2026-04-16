import { useMutation } from "@tanstack/react-query"
import * as React from "react"

import { api } from "@/api/client"
import { useAuth } from "@/auth/AuthProvider"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { PasswordInput } from "@/components/ui/password-input"

export function ProfilePage(): React.JSX.Element {
  const { identity, refresh } = useAuth()

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
    </div>
  )
}
