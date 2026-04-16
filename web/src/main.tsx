import { MutationCache, QueryCache, QueryClient, QueryClientProvider } from "@tanstack/react-query"
import * as React from "react"
import ReactDOM from "react-dom/client"
import { RouterProvider } from "react-router-dom"
import { Toaster } from "sonner"

import "./globals.css"
import { router } from "./router"

const qc = new QueryClient({
  defaultOptions: { queries: { retry: false } },
  queryCache: new QueryCache({
    onError: (err) => {
      if (err instanceof Error && err.message.startsWith("401:")) {
        void qc.invalidateQueries({ queryKey: ["me"] })
      }
    },
  }),
  mutationCache: new MutationCache({
    onError: (err) => {
      if (err instanceof Error && err.message.startsWith("401:")) {
        void qc.invalidateQueries({ queryKey: ["me"] })
      }
    },
  }),
})

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <QueryClientProvider client={qc}>
      <RouterProvider router={router} />
      <Toaster richColors position="top-right" />
    </QueryClientProvider>
  </React.StrictMode>
)
