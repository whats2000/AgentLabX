import type { components } from "../api/generated";

// Named schemas from the FastAPI OpenAPI spec.
export type SessionSummary = components["schemas"]["SessionSummary"];
export type SessionDetail = components["schemas"]["SessionDetail"];
export type SessionCreateRequest = components["schemas"]["SessionCreateRequest"];
export type RedirectRequest = components["schemas"]["RedirectRequest"];
export type PreferencesUpdateRequest =
  components["schemas"]["PreferencesUpdateRequest"];
export type HTTPValidationError = components["schemas"]["HTTPValidationError"];
export type ValidationError = components["schemas"]["ValidationError"];

// Domain enums as string literal unions (matches FastAPI).
export type SessionStatus =
  | "created"
  | "running"
  | "paused"
  | "completed"
  | "failed";

export type ControlLevel = "auto" | "notify" | "approve" | "edit";
export type BacktrackControl = "auto" | "notify" | "approve";
export type Mode = "auto" | "hitl";

// Graph topology types
export type GraphNodeStatus = "pending" | "active" | "complete" | "failed" | "skipped" | "meta";
export type GraphNodeType = "stage" | "transition" | "subgraph";
export type GraphEdgeKind = "sequential" | "backtrack" | "conditional";
export type GraphZone = "discovery" | "implementation" | "synthesis";

export interface GraphNode {
  id: string;
  type: GraphNodeType;
  label: string;
  zone: GraphZone | null;
  status: GraphNodeStatus;
  iteration_count: number;
  skipped: boolean;
}

export interface GraphEdge {
  from: string;
  to: string;
  kind: GraphEdgeKind;
  reason?: string | null;
  attempts?: number | null;
}

export interface GraphCursor {
  node_id: string;
  internal_node?: string | null;
  meeting_node?: string | null;
  agent: string | null;
  started_at: string | null;
}

export interface GraphSubgraphNode {
  id: string;
  type: string;
}

export interface GraphSubgraphEdge {
  from: string;
  to: string;
}

export interface GraphSubgraph {
  id: string;
  kind: "stage_subgraph" | "invocable_only" | string;
  label?: string;
  nodes: GraphSubgraphNode[];
  edges: GraphSubgraphEdge[];
}

export interface GraphTopology {
  nodes: GraphNode[];
  edges: GraphEdge[];
  cursor: GraphCursor | null;
  subgraphs: GraphSubgraph[];
}

// Agent turn / history types
export type AgentTurnKind =
  | "llm_request"
  | "llm_response"
  | "tool_call"
  | "tool_result"
  | "dialogue";

export interface AgentTurnRow {
  turn_id: string;
  parent_turn_id: string | null;
  agent: string;
  stage: string;
  kind: AgentTurnKind;
  payload: Record<string, unknown>;
  system_prompt_hash: string | null;
  tokens_in: number | null;
  tokens_out: number | null;
  cost_usd: number | null;
  is_mock: boolean;
  ts: string;
}

export interface AgentHistoryResponse {
  turns: AgentTurnRow[];
  next_cursor: string | null;
}

// Agent memory
export interface AgentMemoryRecord {
  working_memory: Record<string, unknown>;
  notes: string[];
  last_active_stage: string;
  turn_count: number;
}

// Session agent listing
export interface SessionAgentInfo {
  name: string;
  role: string;
  turn_count: number;
  last_active_stage: string | null;
}

// Agent context view
export interface AgentContextResponse {
  keys: string[];
  preview: Record<string, unknown>;
  scope: {
    read: string[];
    summarize: Record<string, string>;
    write: string[];
  };
}

// PI decision records
export interface PIDecisionRecord {
  decision_id: string;
  action: string;
  confidence: number;
  next_stage: string | null;
  reasoning: string;
  used_fallback: boolean;
  ts: string;
}

// Cross-stage requests
export interface CrossStageRequestRecord {
  from_stage: string;
  to_stage: string;
  request_type: string;
  description: string;
  status: string;
  result?: unknown;
}

export interface RequestsResponse {
  pending: CrossStageRequestRecord[];
  completed: CrossStageRequestRecord[];
}

// Experiments
export interface ExperimentsResponse {
  runs: Array<Record<string, unknown>>;
  log: Array<Record<string, unknown>>;
}

// Stage plans
export type StagePlanStatus = "done" | "edit" | "todo" | "removed";
export type StagePlanItemSource =
  | "contract"
  | "feedback"
  | "request"
  | "user"
  | "prior";

export interface StagePlanItem {
  id: string;
  description: string;
  status: StagePlanStatus;
  source: StagePlanItemSource;
  existing_artifact_ref: string | null;
  edit_note: string | null;
  removed_reason: string | null;
}

export interface StagePlan {
  items: StagePlanItem[];
  rationale: string;
  hash_of_consumed_inputs: string;
}
