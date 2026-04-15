export interface IdentityDto {
  id: string
  display_name: string
  auther_name: string
  capabilities: string[]
}

export interface CredentialSlotDto {
  slot: string
  updated_at: string
}

export interface AdminUserDto extends IdentityDto {}

async function request<T>(input: string, init?: RequestInit): Promise<T> {
  const res = await fetch(input, { credentials: "include", ...init })
  if (!res.ok) throw new Error(`${res.status} ${res.statusText}`)
  if (res.status === 204) return undefined as unknown as T
  return (await res.json()) as T
}

export const api = {
  register: (display_name: string, passphrase: string) =>
    request<IdentityDto>("/api/auth/register", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ display_name, passphrase }),
    }),
  login: (identity_id: string, passphrase: string) =>
    request<IdentityDto>("/api/auth/login", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ identity_id, passphrase }),
    }),
  me: () => request<IdentityDto>("/api/auth/me"),
  logout: () => request<void>("/api/auth/logout", { method: "POST" }),
  listCredentials: () => request<CredentialSlotDto[]>("/api/settings/credentials"),
  putCredential: (slot: string, value: string) =>
    request<void>(`/api/settings/credentials/${encodeURIComponent(slot)}`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ value }),
    }),
  deleteCredential: (slot: string) =>
    request<void>(`/api/settings/credentials/${encodeURIComponent(slot)}`, { method: "DELETE" }),
  revealCredential: (slot: string) =>
    request<{ slot: string; value: string }>(
      `/api/settings/credentials/${encodeURIComponent(slot)}/reveal`
    ),
  listUsers: () => request<AdminUserDto[]>("/api/settings/admin/users"),
  createUser: (display_name: string, passphrase: string) =>
    request<AdminUserDto>("/api/settings/admin/users", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ display_name, passphrase }),
    }),
  grantCapability: (user_id: string, capability: string) =>
    request<void>(`/api/settings/admin/users/${encodeURIComponent(user_id)}/capabilities`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ capability }),
    }),
}
