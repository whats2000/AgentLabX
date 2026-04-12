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
