"""Event type constants emitted during pipeline execution."""

from __future__ import annotations


class EventTypes:
    # Stage lifecycle
    STAGE_STARTED = "stage_started"
    STAGE_COMPLETED = "stage_completed"
    STAGE_FAILED = "stage_failed"

    # Agent turn (Plan 6)
    AGENT_TURN_STARTED = "agent_turn_started"
    AGENT_TURN_COMPLETED = "agent_turn_completed"
    AGENT_LLM_REQUEST = "agent_llm_request"
    AGENT_LLM_RESPONSE = "agent_llm_response"
    AGENT_TOOL_CALL = "agent_tool_call"
    AGENT_TOOL_RESULT = "agent_tool_result"
    AGENT_DIALOGUE = "agent_dialogue"

    # Pipeline / research
    PI_DECISION = "pi_decision"
    HYPOTHESIS_UPDATE = "hypothesis_update"
    CHECKPOINT_REACHED = "checkpoint_reached"

    # Observability
    COST_UPDATE = "cost_update"
    ERROR = "error"
