export interface TokenRecordDto {
  id: string
  label: string
  created_at: string
  last_used_at: string | null
}

export interface IssuedTokenDto {
  id: string
  label: string
  token: string // plaintext — shown once
}

export interface SessionDto {
  id: string
  issued_at: string
  expires_at: string
  last_seen_at: string
  is_current: boolean
}

export interface IdentityDto {
  id: string
  email: string
  display_name: string
  auther_name: string
  capabilities: string[]
}

export interface CredentialSlotDto {
  slot: string
  updated_at: string
}

export interface AdminUserDto extends IdentityDto {}

export interface AuditEventDto {
  kind: string
  at: string
  payload: Record<string, string | number | boolean | null>
}

export interface LLMModelDto {
  id: string
  display_name: string
  provider: string
}

export interface LLMProviderDto {
  name: string
  display_name: string
  models: LLMModelDto[]
}

// ---------------------------------------------------------------------------
// MCP (Model Context Protocol) — Stage A3 surface
// ---------------------------------------------------------------------------

export type MCPScope = "user" | "admin"
export type MCPTransport = "stdio" | "http" | "inprocess"

export interface MCPToolDto {
  server_id: string
  server_name: string
  tool_name: string
  description: string
  input_schema: Record<string, unknown>
  capabilities: string[]
}

export interface MCPServerDto {
  id: string
  name: string
  scope: MCPScope
  transport: MCPTransport
  enabled: boolean
  owner_id: string | null
  declared_capabilities: string[]
  tools: MCPToolDto[]
  started_at: string | null
}

export interface MCPServerCreateRequest {
  name: string
  scope: MCPScope
  transport: MCPTransport
  command: string[] | null
  url: string | null
  inprocess_key: string | null
  env_slot_refs: string[]
  declared_capabilities: string[]
}

export interface ToolInvokeResponse {
  is_error: boolean
  text: string
  structured: Record<string, unknown> | null
}

async function request<T>(input: string, init?: RequestInit): Promise<T> {
  const res = await fetch(input, { credentials: "include", ...init })
  if (!res.ok) {
    let detail: string = res.statusText || `HTTP ${res.status}`
    try {
      const body: unknown = await res.json()
      if (
        typeof body === "object" &&
        body !== null &&
        "detail" in body &&
        typeof (body as { detail: unknown }).detail === "string"
      ) {
        detail = (body as { detail: string }).detail
      }
    } catch {
      // body was not JSON; keep statusText
    }
    throw new Error(`${res.status}: ${detail}`)
  }
  if (res.status === 204) return undefined as unknown as T
  return (await res.json()) as T
}

export const api = {
  bootstrapStatus: () =>
    request<{ needs_bootstrap: boolean; remember_me_days: number }>("/api/auth/bootstrap-status"),
  register: (display_name: string, email: string, passphrase: string) =>
    request<IdentityDto>("/api/auth/register", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ display_name, email, passphrase }),
    }),
  login: (email: string, passphrase: string, remember_me = false) =>
    request<IdentityDto>("/api/auth/login", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ email, passphrase, remember_me }),
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
      `/api/settings/credentials/${encodeURIComponent(slot)}/reveal`,
    ),
  listUsers: () => request<AdminUserDto[]>("/api/settings/admin/users"),
  createUser: (display_name: string, email: string, passphrase: string) =>
    request<AdminUserDto>("/api/settings/admin/users", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ display_name, email, passphrase }),
    }),
  grantCapability: (user_id: string, capability: string) =>
    request<void>(`/api/settings/admin/users/${encodeURIComponent(user_id)}/capabilities`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ capability }),
    }),
  deleteUser: (user_id: string) =>
    request<void>(`/api/settings/admin/users/${encodeURIComponent(user_id)}`, {
      method: "DELETE",
    }),
  revokeCapability: (user_id: string, capability: string) =>
    request<void>(
      `/api/settings/admin/users/${encodeURIComponent(user_id)}/capabilities/${encodeURIComponent(capability)}`,
      { method: "DELETE" },
    ),
  updateDisplayName: (display_name: string) =>
    request<IdentityDto>("/api/auth/me/display-name", {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ display_name }),
    }),
  updateEmail: (new_email: string, passphrase: string) =>
    request<IdentityDto>("/api/auth/me/email", {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ new_email, passphrase }),
    }),
  updatePassphrase: (old_passphrase: string, new_passphrase: string) =>
    request<IdentityDto>("/api/auth/me/passphrase", {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ old_passphrase, new_passphrase }),
    }),
  listEvents: (limit = 200) =>
    request<AuditEventDto[]>(`/api/settings/admin/events?limit=${limit}`),
  clearEvents: () => request<void>("/api/settings/admin/events", { method: "DELETE" }),
  listMySessions: () => request<SessionDto[]>("/api/auth/me/sessions"),
  revokeMySession: (session_id: string) =>
    request<void>(`/api/auth/me/sessions/${encodeURIComponent(session_id)}`, {
      method: "DELETE",
    }),
  listMyTokens: () => request<TokenRecordDto[]>("/api/auth/me/tokens"),
  issueMyToken: (label: string) =>
    request<IssuedTokenDto>("/api/auth/me/tokens", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ label }),
    }),
  deleteMyToken: (token_id: string) =>
    request<void>(`/api/auth/me/tokens/${encodeURIComponent(token_id)}`, {
      method: "DELETE",
    }),
  listLLMProviders: () => request<LLMProviderDto[]>("/api/llm/providers"),
  listLLMModels: () => request<LLMModelDto[]>("/api/llm/models"),
  refreshMyToken: (token_id: string) =>
    request<IssuedTokenDto>(`/api/auth/me/tokens/${encodeURIComponent(token_id)}/refresh`, {
      method: "POST",
    }),
  listMCPServers: () => request<MCPServerDto[]>("/api/mcp/servers"),
  getMCPServer: (id: string) => request<MCPServerDto>(`/api/mcp/servers/${encodeURIComponent(id)}`),
  registerMCPServer: (body: MCPServerCreateRequest) =>
    request<MCPServerDto>("/api/mcp/servers", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    }),
  patchMCPServer: (id: string, enabled: boolean) =>
    request<MCPServerDto>(`/api/mcp/servers/${encodeURIComponent(id)}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ enabled }),
    }),
  deleteMCPServer: (id: string) =>
    request<void>(`/api/mcp/servers/${encodeURIComponent(id)}`, { method: "DELETE" }),
  listMCPTools: () => request<MCPToolDto[]>("/api/mcp/tools"),
  invokeMCPTool: (server_id: string, tool: string, args: Record<string, unknown>) =>
    request<ToolInvokeResponse>(
      `/api/mcp/servers/${encodeURIComponent(server_id)}/tools/${encodeURIComponent(tool)}/invoke`,
      {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ args }),
      },
    ),
}
