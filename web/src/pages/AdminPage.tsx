import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import * as React from "react"
import { toast } from "sonner"

import { api, type AdminUserDto } from "@/api/client"
import { useAuth } from "@/auth/AuthProvider"
import { ConfirmDialog } from "@/components/confirm-dialog"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { PasswordInput } from "@/components/ui/password-input"

export function AdminPage(): React.JSX.Element {
  const qc = useQueryClient()
  const { identity: me } = useAuth()
  const users = useQuery<AdminUserDto[]>({ queryKey: ["users"], queryFn: api.listUsers })
  const [name, setName] = React.useState("")
  const [email, setEmail] = React.useState("")
  const [pass, setPass] = React.useState("")

  const create = useMutation({
    mutationFn: () => api.createUser(name, email, pass),
    onSuccess: () => {
      setName("")
      setEmail("")
      setPass("")
      void qc.invalidateQueries({ queryKey: ["users"] })
      toast.success("User created")
    },
    onError: (err: Error) => { toast.error(err.message) },
  })
  const grant = useMutation({
    mutationFn: ({ user_id, capability }: { user_id: string; capability: string }) =>
      api.grantCapability(user_id, capability),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ["users"] })
      toast.success("Admin granted")
    },
    onError: (err: Error) => { toast.error(err.message) },
  })
  const revoke = useMutation({
    mutationFn: ({ user_id, capability }: { user_id: string; capability: string }) =>
      api.revokeCapability(user_id, capability),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ["users"] })
      toast.success("Admin revoked")
    },
    onError: (err: Error) => { toast.error(err.message) },
  })
  const del = useMutation({
    mutationFn: (user_id: string) => api.deleteUser(user_id),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ["users"] })
      toast.success("User deleted")
    },
    onError: (err: Error) => { toast.error(err.message) },
  })

  return (
    <div className="max-w-3xl space-y-6">
      <h1 className="text-2xl font-semibold">Admin — Users</h1>
      <Card>
        <CardHeader>
          <CardTitle>Create user</CardTitle>
        </CardHeader>
        <CardContent>
          <form
            className="space-y-4"
            onSubmit={(e) => {
              e.preventDefault()
              create.mutate()
            }}
          >
            <div className="space-y-2">
              <Label>Display name</Label>
              <Input value={name} onChange={(e) => { setName(e.target.value) }} required />
            </div>
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
              <Label>Initial passphrase (user can change later)</Label>
              <PasswordInput
                value={pass}
                onChange={(e) => { setPass(e.target.value) }}
                required
                minLength={8}
              />
            </div>
            {create.error ? (
              <div className="rounded border border-red-200 bg-red-50 p-2 text-sm text-red-700">
                {create.error.message}
              </div>
            ) : null}
            <Button type="submit" disabled={create.isPending}>Create</Button>
          </form>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Users</CardTitle>
        </CardHeader>
        <CardContent>
          {grant.error ? (
            <div className="mb-4 rounded border border-red-200 bg-red-50 p-2 text-sm text-red-700">
              {grant.error.message}
            </div>
          ) : null}
          {revoke.error ? (
            <div className="rounded border border-red-200 bg-red-50 p-2 text-sm text-red-700">
              {revoke.error.message}
            </div>
          ) : null}
          {del.error ? (
            <div className="rounded border border-red-200 bg-red-50 p-2 text-sm text-red-700">
              {del.error.message}
            </div>
          ) : null}
          {users.data && users.data.length > 0 ? (
            <ul className="divide-y">
              {users.data.map((u) => (
                <li key={u.id} className="flex items-center justify-between py-2">
                  <div>
                    <div className="font-medium">
                      {u.display_name}
                      {u.capabilities.includes("owner") && (
                        <span className="ml-2 rounded bg-amber-100 px-1.5 py-0.5 text-xs font-medium text-amber-700">
                          Owner
                        </span>
                      )}
                    </div>
                    <div className="text-sm text-slate-500">{u.email}</div>
                    <div className="text-xs text-slate-400">
                      {u.id} · {u.auther_name} · {u.capabilities.join(", ") || "no capabilities"}
                    </div>
                  </div>
                  <div className="flex gap-2">
                    {u.id === me?.id ? (
                      <span className="self-center text-xs text-slate-400">(you)</span>
                    ) : u.capabilities.includes("owner") ? (
                      <span className="self-center text-xs text-slate-400">(owner)</span>
                    ) : (
                      <>
                        {u.capabilities.includes("admin") ? (
                          <ConfirmDialog
                            trigger={<Button variant="outline" size="sm">Revoke admin</Button>}
                            title="Revoke admin capability?"
                            description={
                              <>Remove admin privileges from <strong>{u.display_name}</strong> ({u.email}). They will no longer be able to manage users or server-wide settings.</>
                            }
                            confirmLabel="Revoke"
                            destructive
                            onConfirm={() => { revoke.mutate({ user_id: u.id, capability: "admin" }) }}
                          />
                        ) : (
                          <Button
                            variant="outline"
                            size="sm"
                            onClick={() => { grant.mutate({ user_id: u.id, capability: "admin" }) }}
                          >
                            Grant admin
                          </Button>
                        )}
                        <ConfirmDialog
                          trigger={<Button variant="outline" size="sm">Delete</Button>}
                          title="Delete user?"
                          description={
                            <>Delete <strong>{u.display_name}</strong> ({u.email}). All of their credentials, notes, and sessions will be removed. This cannot be undone.</>
                          }
                          confirmLabel="Delete"
                          destructive
                          onConfirm={() => { del.mutate(u.id) }}
                        />
                      </>
                    )}
                  </div>
                </li>
              ))}
            </ul>
          ) : (
            <div className="text-sm text-slate-500">No users yet.</div>
          )}
        </CardContent>
      </Card>
    </div>
  )
}
