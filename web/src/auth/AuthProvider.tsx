import { useQuery } from "@tanstack/react-query"
import * as React from "react"

import { api, type IdentityDto } from "@/api/client"

interface AuthContextValue {
  identity: IdentityDto | null
  isLoading: boolean
  refresh: () => Promise<IdentityDto | null>
}

const AuthContext = React.createContext<AuthContextValue | null>(null)

export function AuthProvider({ children }: { children: React.ReactNode }): React.JSX.Element {
  const q = useQuery<IdentityDto | null>({
    queryKey: ["me"],
    queryFn: async () => {
      try {
        return await api.me()
      } catch {
        return null
      }
    },
  })
  const value: AuthContextValue = {
    identity: q.data ?? null,
    isLoading: q.isLoading,
    refresh: async () => {
      const { data } = await q.refetch()
      return data ?? null
    },
  }
  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}

export function useAuth(): AuthContextValue {
  const ctx = React.useContext(AuthContext)
  if (!ctx) throw new Error("useAuth outside AuthProvider")
  return ctx
}
