/**
 * WebSocket event types emitted by the backend.
 * Mirrors agentlabx.server.events + backend Event model.
 */

export type PipelineEventType =
  | "stage_started"
  | "stage_completed"
  | "stage_failed"
  | "agent_thinking"
  | "agent_turn_started"
  | "agent_turn_completed"
  | "agent_llm_request"
  | "agent_llm_response"
  | "agent_tool_call"
  | "agent_tool_result"
  | "agent_dialogue"
  | "pi_decision"
  | "hypothesis_update"
  | "transition"
  | "checkpoint_reached"
  | "cost_update"
  | "error";

export interface PipelineEvent<T = unknown> {
  type: PipelineEventType;
  data: T;
  source?: string | null;
  timestamp?: string; // Fix C backport: ISO-8601 UTC from backend Event.timestamp
}

export interface StageStartedEvent
  extends PipelineEvent<{ stage: string; session_id: string }> {
  type: "stage_started";
}

export interface StageCompletedEvent
  extends PipelineEvent<{
    stage: string;
    session_id: string;
    status: string;
    reason: string;
    next_hint: string | null;
  }> {
  type: "stage_completed";
}

export interface StageFailedEvent
  extends PipelineEvent<{
    stage: string;
    session_id: string;
    error_type: string;
    message: string;
  }> {
  type: "stage_failed";
}

// Client → server action messages
export type ClientAction =
  | {
      action: "update_preferences";
      mode?: "auto" | "hitl";
      stage_controls?: Record<string, string>;
      backtrack_control?: string;
    }
  | { action: "redirect"; target_stage: string; reason?: string }
  | { action: "inject_feedback"; content: string }
  | { action: "approve"; reason?: string }
  | { action: "reject"; reason?: string }
  | { action: "edit"; content: string };
