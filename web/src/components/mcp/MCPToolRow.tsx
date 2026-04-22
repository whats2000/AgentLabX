import { useMutation } from "@tanstack/react-query"
import { ChevronDown, ChevronRight, PlayCircle } from "lucide-react"
import * as React from "react"
import { useTranslation } from "react-i18next"

import { api, type MCPToolDto, type ToolInvokeResponse } from "@/api/client"
import { Button } from "@/components/ui/button"
import { Label } from "@/components/ui/label"
import { Textarea } from "@/components/ui/textarea"

interface Props {
  tool: MCPToolDto
}

export function MCPToolRow({ tool }: Props): React.JSX.Element {
  const { t } = useTranslation()
  const [expanded, setExpanded] = React.useState(false)
  const [argsJson, setArgsJson] = React.useState("{}")
  const [argsError, setArgsError] = React.useState<string | null>(null)
  const [result, setResult] = React.useState<ToolInvokeResponse | null>(null)

  const invoke = useMutation({
    mutationFn: async (): Promise<ToolInvokeResponse> => {
      let parsed: unknown
      try {
        parsed = JSON.parse(argsJson)
      } catch (err) {
        const msg = err instanceof Error ? err.message : String(err)
        setArgsError(msg)
        throw new Error(t("mcp.invokeBadJson", { reason: msg }))
      }
      if (typeof parsed !== "object" || parsed === null || Array.isArray(parsed)) {
        const msg = t("mcp.invokeArgsMustBeObject")
        setArgsError(msg)
        throw new Error(msg)
      }
      setArgsError(null)
      return api.invokeMCPTool(tool.server_id, tool.tool_name, parsed as Record<string, unknown>)
    },
    onSuccess: (r) => {
      setResult(r)
    },
    onError: () => {
      setResult(null)
    },
  })

  return (
    <li className="rounded border border-border bg-background/50">
      <button
        type="button"
        className="flex w-full items-start gap-2 p-3 text-left hover:bg-muted/40 transition-colors"
        onClick={() => {
          setExpanded((v) => !v)
        }}
      >
        {expanded ? (
          <ChevronDown className="mt-0.5 h-4 w-4 shrink-0 text-muted-foreground" />
        ) : (
          <ChevronRight className="mt-0.5 h-4 w-4 shrink-0 text-muted-foreground" />
        )}
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-2">
            <code className="font-mono text-sm font-medium">{tool.tool_name}</code>
            {tool.capabilities.map((cap) => (
              <span
                key={cap}
                className="inline-flex items-center rounded-full border border-border bg-muted px-2 py-0.5 text-[10px] font-medium uppercase tracking-wide text-muted-foreground"
              >
                {cap}
              </span>
            ))}
          </div>
          {tool.description ? (
            <p className="mt-1 text-xs text-muted-foreground line-clamp-2">{tool.description}</p>
          ) : null}
        </div>
      </button>

      {expanded ? (
        <div className="space-y-3 border-t border-border p-3">
          <div className="space-y-1.5">
            <Label className="text-xs">{t("mcp.argsJsonLabel")}</Label>
            <Textarea
              rows={4}
              value={argsJson}
              onChange={(e) => {
                setArgsJson(e.target.value)
                setArgsError(null)
              }}
              spellCheck={false}
            />
            {argsError ? (
              <p className="text-xs text-red-600 dark:text-red-400">{argsError}</p>
            ) : null}
          </div>

          <div className="flex items-center gap-2">
            <Button
              type="button"
              size="sm"
              onClick={() => {
                invoke.mutate()
              }}
              disabled={invoke.isPending}
            >
              <PlayCircle className="h-4 w-4" />
              {invoke.isPending ? t("mcp.invoking") : t("mcp.invoke")}
            </Button>
            {invoke.error ? (
              <span className="text-xs text-red-600 dark:text-red-400">{invoke.error.message}</span>
            ) : null}
          </div>

          {result ? (
            <div
              className={
                result.is_error
                  ? "rounded border border-red-300 bg-red-50 p-2 text-xs dark:border-red-800 dark:bg-red-950"
                  : "rounded border border-emerald-300 bg-emerald-50 p-2 text-xs dark:border-emerald-800 dark:bg-emerald-950"
              }
            >
              <div className="mb-1 text-[10px] font-semibold uppercase tracking-wide">
                {result.is_error ? t("mcp.resultError") : t("mcp.resultOk")}
              </div>
              <pre className="whitespace-pre-wrap break-words font-mono text-xs leading-snug">
                {result.text}
              </pre>
              {result.structured ? (
                <details className="mt-2">
                  <summary className="cursor-pointer text-[10px] uppercase tracking-wide text-muted-foreground">
                    {t("mcp.structured")}
                  </summary>
                  <pre className="mt-1 whitespace-pre-wrap break-words font-mono text-xs">
                    {JSON.stringify(result.structured, null, 2)}
                  </pre>
                </details>
              ) : null}
            </div>
          ) : null}
        </div>
      ) : null}
    </li>
  )
}
