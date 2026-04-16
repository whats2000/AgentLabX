import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import * as React from "react"
import { useTranslation } from "react-i18next"
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
  const { t } = useTranslation()
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
      toast.success(t("admin.userCreated"))
    },
    onError: (err: Error) => { toast.error(err.message) },
  })
  const grant = useMutation({
    mutationFn: ({ user_id, capability }: { user_id: string; capability: string }) =>
      api.grantCapability(user_id, capability),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ["users"] })
      toast.success(t("admin.adminGranted"))
    },
    onError: (err: Error) => { toast.error(err.message) },
  })
  const revoke = useMutation({
    mutationFn: ({ user_id, capability }: { user_id: string; capability: string }) =>
      api.revokeCapability(user_id, capability),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ["users"] })
      toast.success(t("admin.adminRevoked"))
    },
    onError: (err: Error) => { toast.error(err.message) },
  })
  const del = useMutation({
    mutationFn: (user_id: string) => api.deleteUser(user_id),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ["users"] })
      toast.success(t("admin.userDeleted"))
    },
    onError: (err: Error) => { toast.error(err.message) },
  })

  return (
    <div className="max-w-3xl space-y-6">
      <h1 className="text-2xl font-semibold">{t("admin.title")}</h1>
      <Card>
        <CardHeader>
          <CardTitle>{t("admin.createUser")}</CardTitle>
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
              <Label>{t("admin.displayNameLabel")}</Label>
              <Input value={name} onChange={(e) => { setName(e.target.value) }} required />
            </div>
            <div className="space-y-2">
              <Label>{t("admin.emailLabel")}</Label>
              <Input
                type="email"
                value={email}
                onChange={(e) => { setEmail(e.target.value) }}
                required
                autoComplete="email"
              />
            </div>
            <div className="space-y-2">
              <Label>{t("admin.initialPassphrase")}</Label>
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
            <Button type="submit" disabled={create.isPending}>{t("admin.createButton")}</Button>
          </form>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>{t("admin.usersCard")}</CardTitle>
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
                          {t("admin.ownerBadge")}
                        </span>
                      )}
                    </div>
                    <div className="text-sm text-slate-500">{u.email}</div>
                    <div className="text-xs text-slate-400">
                      {u.id} · {u.auther_name} · {u.capabilities.join(", ") || t("admin.noCapabilities")}
                    </div>
                  </div>
                  <div className="flex gap-2">
                    {u.id === me?.id ? (
                      <span className="self-center text-xs text-slate-400">{t("common.you")}</span>
                    ) : u.capabilities.includes("owner") ? (
                      <span className="self-center text-xs text-slate-400">{t("common.owner")}</span>
                    ) : (
                      <>
                        {u.capabilities.includes("admin") ? (
                          <ConfirmDialog
                            trigger={<Button variant="outline" size="sm">{t("admin.revokeAdmin")}</Button>}
                            title={t("admin.revokeAdminTitle")}
                            description={
                              <>{t("admin.revokeAdminDesc", { name: u.display_name, email: u.email })}</>
                            }
                            confirmLabel={t("common.revoke")}
                            destructive
                            onConfirm={() => { revoke.mutate({ user_id: u.id, capability: "admin" }) }}
                          />
                        ) : (
                          <Button
                            variant="outline"
                            size="sm"
                            onClick={() => { grant.mutate({ user_id: u.id, capability: "admin" }) }}
                          >
                            {t("admin.grantAdmin")}
                          </Button>
                        )}
                        <ConfirmDialog
                          trigger={<Button variant="outline" size="sm">{t("admin.deleteUser")}</Button>}
                          title={t("admin.deleteUserTitle")}
                          description={
                            <>{t("admin.deleteUserDesc", { name: u.display_name, email: u.email })}</>
                          }
                          confirmLabel={t("common.delete")}
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
            <div className="text-sm text-slate-500">{t("admin.noUsers")}</div>
          )}
        </CardContent>
      </Card>
    </div>
  )
}
