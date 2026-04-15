import * as React from "react"

import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"

export function RunsPage(): React.JSX.Element {
  return (
    <div className="max-w-3xl space-y-6">
      <h1 className="text-2xl font-semibold">Runs</h1>
      <Card>
        <CardHeader>
          <CardTitle>No runs yet</CardTitle>
        </CardHeader>
        <CardContent>
          <p className="text-sm text-slate-500">
            Stage execution arrives in Layer B. A1 only establishes the server + auth foundation.
          </p>
        </CardContent>
      </Card>
    </div>
  )
}
