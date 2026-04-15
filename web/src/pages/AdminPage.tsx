import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import * as React from "react"

import { api, type AdminUserDto } from "@/api/client"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"

export function AdminPage(): React.JSX.Element {
  const qc = useQueryClient()
  const users = useQuery<AdminUserDto[]>({ queryKey: ["users"], queryFn: api.listUsers })
  const [name, setName] = React.useState("")
  const [pass, setPass] = React.useState("")

  const create = useMutation({
    mutationFn: () => api.createUser(name, pass),
    onSuccess: () => {
      setName("")
      setPass("")
      void qc.invalidateQueries({ queryKey: ["users"] })
    },
  })
  const grant = useMutation({
    mutationFn: ({ user_id, capability }: { user_id: string; capability: string }) =>
      api.grantCapability(user_id, capability),
    onSuccess: () => { void qc.invalidateQueries({ queryKey: ["users"] }) },
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
              <Label>Initial passphrase (user can change later)</Label>
              <Input type="password" value={pass} onChange={(e) => { setPass(e.target.value) }} required minLength={8} />
            </div>
            <Button type="submit" disabled={create.isPending}>Create</Button>
          </form>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Users</CardTitle>
        </CardHeader>
        <CardContent>
          {users.data && users.data.length > 0 ? (
            <ul className="divide-y">
              {users.data.map((u) => (
                <li key={u.id} className="flex items-center justify-between py-2">
                  <div>
                    <div className="font-medium">{u.display_name}</div>
                    <div className="text-xs text-slate-500">
                      {u.id} · {u.auther_name} · {u.capabilities.join(", ") || "no capabilities"}
                    </div>
                  </div>
                  {!u.capabilities.includes("admin") ? (
                    <Button
                      variant="outline"
                      size="sm"
                      onClick={() => { grant.mutate({ user_id: u.id, capability: "admin" }) }}
                    >
                      Grant admin
                    </Button>
                  ) : null}
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
