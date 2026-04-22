// Build a JSON skeleton suitable as a textarea prefill from a JSON-Schema-style
// `input_schema` object as exposed by `MCPToolDto`. Best-effort: handles
// `type`, `default`, and basic `properties` recursion. Unknown shapes degrade
// to `null` rather than crashing — the user is free to edit before submitting.

type SchemaNode = Record<string, unknown>

function isObject(v: unknown): v is SchemaNode {
  return typeof v === "object" && v !== null && !Array.isArray(v)
}

function pickType(node: SchemaNode): string | null {
  const raw = node["type"]
  if (typeof raw === "string") return raw
  if (Array.isArray(raw)) {
    // type: ["string", "null"] — prefer the non-null one for prefill.
    const non_null = raw.find((t) => typeof t === "string" && t !== "null")
    if (typeof non_null === "string") return non_null
    if (raw.includes("null")) return "null"
  }
  return null
}

function prefillNode(node: unknown): unknown {
  if (!isObject(node)) return null
  if ("default" in node) return node["default"]
  if ("const" in node) return node["const"]
  if (Array.isArray(node["enum"]) && node["enum"].length > 0) return node["enum"][0]

  const type = pickType(node)
  switch (type) {
    case "string":
      return ""
    case "integer":
    case "number":
      return 0
    case "boolean":
      return false
    case "null":
      return null
    case "array":
      return []
    case "object":
      return prefillObject(node)
    default:
      // No `type` declared — could be free-form. Use null as a safe placeholder.
      return null
  }
}

function prefillObject(node: SchemaNode): Record<string, unknown> {
  const properties = node["properties"]
  if (!isObject(properties)) return {}
  const required = Array.isArray(node["required"])
    ? new Set(node["required"].filter((r): r is string => typeof r === "string"))
    : null
  const out: Record<string, unknown> = {}
  for (const [key, child] of Object.entries(properties)) {
    // Always include required props; for optional ones, include too so the user
    // sees the full shape (they can delete fields they don't need).
    out[key] = prefillNode(child)
    void required
  }
  return out
}

/** Build a JSON skeleton string from a tool's `input_schema`.
 *
 * Returns a pretty-printed JSON object ready to drop into a textarea.
 * Falls back to `"{}"` when the schema is missing or malformed.
 */
export function prefillFromSchema(schema: Record<string, unknown> | null | undefined): string {
  if (!schema || !isObject(schema)) return "{}"
  const skeleton = isObject(schema["properties"]) ? prefillObject(schema) : prefillNode(schema)
  if (!isObject(skeleton)) return "{}"
  try {
    return JSON.stringify(skeleton, null, 2)
  } catch {
    return "{}"
  }
}
