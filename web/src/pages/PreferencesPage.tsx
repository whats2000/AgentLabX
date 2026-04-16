import { Check, Monitor, Moon, Sun } from "lucide-react"
import * as React from "react"
import { useTranslation } from "react-i18next"

import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import i18n from "@/i18n"
import { useTheme, type Theme } from "@/lib/use-theme"
import { cn } from "@/lib/utils"

// Derive available locales from the i18n resources config — never hardcoded here.
function getAvailableLocales(): string[] {
  const resources = i18n.options.resources
  if (!resources) return []
  return Object.keys(resources)
}

// Map locale string to its lang.* i18n key (which is typed in en.json).
function localeToLangKey(locale: string): "lang.en" | "lang.zh-TW" {
  if (locale === "zh-TW") return "lang.zh-TW"
  return "lang.en"
}

const THEME_OPTIONS: {
  value: Theme
  labelKey: "theme.light" | "theme.dark" | "theme.system"
  Icon: React.ElementType
}[] = [
  { value: "light", labelKey: "theme.light", Icon: Sun },
  { value: "dark", labelKey: "theme.dark", Icon: Moon },
  { value: "system", labelKey: "theme.system", Icon: Monitor },
]

export function PreferencesPage(): React.JSX.Element {
  const { t } = useTranslation()
  const { theme, setTheme } = useTheme()
  const locales = getAvailableLocales()
  const currentLang = i18n.language

  return (
    <div className="max-w-3xl space-y-6">
      <h1 className="text-2xl font-semibold">{t("preferences.title")}</h1>

      {/* Language card */}
      <Card>
        <CardHeader>
          <CardTitle>{t("preferences.language")}</CardTitle>
        </CardHeader>
        <CardContent>
          <ul className="divide-y divide-border">
            {locales.map((locale) => {
              const isActive = currentLang === locale
              const nativeName = t(localeToLangKey(locale))
              return (
                <li key={locale}>
                  <button
                    type="button"
                    className={cn(
                      "flex w-full items-center justify-between px-2 py-3 text-sm transition-colors rounded hover:bg-muted",
                      isActive && "font-medium text-foreground"
                    )}
                    onClick={() => { void i18n.changeLanguage(locale) }}
                  >
                    <span>{nativeName}</span>
                    {isActive ? <Check className="h-4 w-4 text-foreground" /> : null}
                  </button>
                </li>
              )
            })}
          </ul>
        </CardContent>
      </Card>

      {/* Theme card */}
      <Card>
        <CardHeader>
          <CardTitle>{t("preferences.theme")}</CardTitle>
        </CardHeader>
        <CardContent>
          <div className="grid grid-cols-3 gap-3">
            {THEME_OPTIONS.map(({ value, labelKey, Icon }) => {
              const isActive = theme === value
              return (
                <button
                  key={value}
                  type="button"
                  onClick={() => { setTheme(value) }}
                  className={cn(
                    "flex flex-col items-center gap-2 rounded-lg border p-4 text-sm transition-colors hover:bg-muted",
                    isActive
                      ? "border-foreground bg-muted font-medium text-foreground"
                      : "border-border text-muted-foreground"
                  )}
                >
                  <Icon className="h-5 w-5" />
                  {t(labelKey)}
                </button>
              )
            })}
          </div>
        </CardContent>
      </Card>
    </div>
  )
}
