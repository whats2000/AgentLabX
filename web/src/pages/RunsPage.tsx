import * as React from "react"
import { useTranslation } from "react-i18next"

import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"

export function RunsPage(): React.JSX.Element {
  const { t } = useTranslation()
  return (
    <div className="max-w-3xl space-y-6">
      <h1 className="text-2xl font-semibold">{t("runs.title")}</h1>
      <Card>
        <CardHeader>
          <CardTitle>{t("runs.emptyTitle")}</CardTitle>
        </CardHeader>
        <CardContent>
          <p className="text-sm text-muted-foreground">{t("runs.emptyDesc")}</p>
        </CardContent>
      </Card>
    </div>
  )
}
