import * as React from "react"

export type Theme = "light" | "dark" | "system"

const STORAGE_KEY = "agentlabx-theme"

function getSystemTheme(): "light" | "dark" {
  if (typeof window === "undefined") return "light"
  return window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light"
}

function applyTheme(theme: Theme): void {
  const resolved = theme === "system" ? getSystemTheme() : theme
  document.documentElement.classList.toggle("dark", resolved === "dark")
}

export function useTheme(): {
  theme: Theme
  setTheme: (t: Theme) => void
  resolvedTheme: "light" | "dark"
} {
  const [theme, setThemeState] = React.useState<Theme>(() => {
    const stored = localStorage.getItem(STORAGE_KEY)
    return (stored === "light" || stored === "dark" || stored === "system") ? stored : "system"
  })

  const resolvedTheme: "light" | "dark" = theme === "system" ? getSystemTheme() : theme

  React.useEffect(() => {
    applyTheme(theme)
    localStorage.setItem(STORAGE_KEY, theme)
  }, [theme])

  React.useEffect(() => {
    if (theme !== "system") return
    const mq = window.matchMedia("(prefers-color-scheme: dark)")
    const handler = (): void => { applyTheme("system") }
    mq.addEventListener("change", handler)
    return () => { mq.removeEventListener("change", handler) }
  }, [theme])

  const setTheme = React.useCallback((t: Theme) => { setThemeState(t) }, [])

  return { theme, setTheme, resolvedTheme }
}
