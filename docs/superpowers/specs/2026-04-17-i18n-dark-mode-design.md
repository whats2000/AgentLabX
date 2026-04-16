---
title: i18n + Dark Mode — Frontend Infrastructure
status: approved
created: 2026-04-17
scope: web shell only (Layer A1 expansion)
---

# i18n + Dark Mode — Frontend Infrastructure

Add internationalization (type-safe) and light/dark/system theme switching to the AgentLabX web shell. Both are infrastructure that gets harder to retrofit as components grow; wiring them now while the shell is small keeps the cost low.

---

## 1. Internationalization (i18n)

### Library

`react-i18next` + `i18next` + `i18next-browser-languagedetector`.

### Type safety

TypeScript module augmentation on `i18next` so `t("nonexistent.key")` is a compile-time error:

```ts
// web/src/i18n/types.ts
import type en from "./locales/en.json"

declare module "i18next" {
  interface CustomTypeOptions {
    defaultNS: "translation"
    resources: { translation: typeof en }
  }
}
```

The English JSON is the source of truth for the key set. All other locale files must mirror the same keys (missing keys fall back to English at runtime; a CI check can enforce completeness later).

### File structure

```
web/src/i18n/
├── index.ts              # i18next init, language detector, resource loading
├── types.ts              # module augmentation (type-safe t())
└── locales/
    ├── en.json           # English — default, source of truth for keys
    └── zh-TW.json        # Traditional Chinese
```

### JSON shape

Single namespace (`translation`), flat dot-separated keys:

```json
{
  "app.name": "AgentLabX",
  "auth.login": "Log in",
  "auth.register": "Create first identity",
  "auth.email": "Email",
  "auth.passphrase": "Passphrase",
  "auth.displayName": "Display name",
  "auth.createAndLogin": "Create & log in",
  "auth.existingLogin": "Existing? Log in",
  "auth.needRegister": "Need to register?",
  "auth.forgotHint": "Forgot your passphrase? Run {{command}} from the server shell.",
  "auth.needAccount": "Need an account? Ask an admin to provision one for you.",
  "auth.loginFailed": "Login succeeded but session was not established; please try again",
  "nav.runs": "Runs",
  "nav.adminUsers": "Admin Users",
  "nav.activity": "Activity",
  "nav.profile": "Profile",
  "nav.credentials": "Credentials",
  "nav.logout": "Log out",
  "profile.title": "Profile",
  "profile.displayName": "Display name",
  "profile.email": "Email",
  "profile.passphrase": "Passphrase",
  "profile.newPassphrase": "New passphrase",
  "profile.confirmPassphrase": "Confirm new passphrase",
  "profile.currentPassphrase": "Current passphrase",
  "profile.save": "Save",
  "profile.tokens": "Personal API tokens",
  "profile.sessions": "Active sessions",
  "settings.title": "Credentials",
  "settings.addSlot": "Add / update a credential",
  "settings.slot": "Slot",
  "settings.value": "Value",
  "settings.stored": "Stored credentials",
  "settings.reveal": "Reveal",
  "settings.delete": "Delete",
  "admin.title": "Admin — Users",
  "admin.createUser": "Create user",
  "admin.users": "Users",
  "admin.grantAdmin": "Grant admin",
  "admin.revokeAdmin": "Revoke admin",
  "admin.deleteUser": "Delete",
  "admin.owner": "Owner",
  "admin.you": "(you)",
  "admin.activity.title": "Recent Activity",
  "admin.activity.clear": "Clear log",
  "admin.activity.hint": "Showing up to {{limit}} most recent events",
  "runs.title": "Runs",
  "runs.empty": "Stage execution arrives in Layer B. A1 only establishes the server + auth foundation.",
  "common.cancel": "Cancel",
  "common.confirm": "Confirm",
  "common.loading": "Loading…",
  "common.noData": "No data yet.",
  "theme.light": "Light",
  "theme.dark": "Dark",
  "theme.system": "System",
  "lang.en": "English",
  "lang.zh-TW": "繁體中文"
}
```

`zh-TW.json` mirrors every key with Traditional Chinese values.

### Language switcher

A `Globe` Lucide icon + current language label in the user popover menu (Layout.tsx DropdownMenu). Clicking opens a sub-list of available locales. Selection persisted in `localStorage` via `i18next-browser-languagedetector`; detected from browser locale on first visit.

### Adding a new locale

1. Create `web/src/i18n/locales/<locale>.json` with every key translated.
2. Import it in `web/src/i18n/index.ts` and add to the resources map.
3. Add a `"lang.<locale>"` key to `en.json` (and every other locale) with the language's display name.

No component-level changes required.

---

## 2. Dark mode

### Mechanism

Tailwind `darkMode: "class"` — the `dark` class on `<html>` activates all `dark:` utilities.

### Color system

CSS custom properties on `:root` (light) and `.dark` (dark) in `globals.css`. The shadcn/ui components reference these via Tailwind config:

```css
:root {
  --background: 0 0% 100%;
  --foreground: 222 47% 11%;
  --card: 0 0% 100%;
  --card-foreground: 222 47% 11%;
  --muted: 210 40% 96%;
  --muted-foreground: 215 16% 47%;
  --border: 214 32% 91%;
  --input: 214 32% 91%;
  --ring: 222 47% 11%;
  --destructive: 0 84% 60%;
  --destructive-foreground: 0 0% 98%;
}

.dark {
  --background: 222 47% 11%;
  --foreground: 210 40% 98%;
  --card: 224 40% 14%;
  --card-foreground: 210 40% 98%;
  --muted: 217 33% 17%;
  --muted-foreground: 215 20% 65%;
  --border: 217 33% 22%;
  --input: 217 33% 22%;
  --ring: 212 100% 67%;
  --destructive: 0 63% 31%;
  --destructive-foreground: 0 0% 98%;
}
```

Tailwind config maps these: `background: "hsl(var(--background))"`, etc. All existing shadcn primitives (Card, Button, Input, Label, AlertDialog, DropdownMenu) inherit dark colors automatically — no per-component `dark:` overrides needed except for the sidebar and a few layout-level utilities.

### `useTheme` hook

```
web/src/lib/use-theme.ts

type Theme = "light" | "dark" | "system"

Returns: { theme: Theme, setTheme: (t: Theme) => void, resolvedTheme: "light" | "dark" }
```

- Reads `localStorage("agentlabx-theme")`, defaults to `"system"`.
- `"system"` follows `prefers-color-scheme` via `matchMedia`.
- On change: toggles `dark` class on `<html>`, persists to localStorage.
- `resolvedTheme` always resolves to `"light"` or `"dark"` (useful for conditional icon rendering).

### Theme toggle

In the user popover (Layout.tsx DropdownMenu), above the Language item:

- Three icons: `Sun` (light), `Moon` (dark), `Monitor` (system).
- Rendered as a DropdownMenu sub-group with three DropdownMenuItems — one per option. The active option gets a check mark or highlighted style.

### Persistence

Both theme and language are client-local (`localStorage`). No database column, no server round-trip. These are device-level preferences.

---

## 3. Component impact

Every user-visible string in every `.tsx` file is replaced with `t("key")`. Files affected:

- `LoginPage.tsx`, `Layout.tsx`, `ProfilePage.tsx`, `SettingsPage.tsx`, `AdminPage.tsx`, `AdminActivityPage.tsx`, `RunsPage.tsx`
- `confirm-dialog.tsx` (default labels)
- `password-input.tsx` (aria-label)

Color classes in existing components that hardcode `bg-white`, `text-slate-*`, `border-slate-*` etc. are replaced with the CSS-variable-backed Tailwind utilities (`bg-background`, `text-foreground`, `border-border`, etc.) so dark mode applies automatically.

The sidebar (Layout.tsx) needs explicit `dark:` classes for its background, border, and hover states since it's hand-styled rather than a shadcn primitive.

---

## 4. No RTL

Right-to-left layout support is deferred. No `dir="rtl"` flipping, no logical CSS properties. If needed later, it's an additive pass that doesn't conflict with this work.
