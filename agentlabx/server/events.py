"""Event type constants emitted during pipeline execution."""

from __future__ import annotations

# Stage lifecycle
STAGE_STARTED = "stage_started"
STAGE_COMPLETED = "stage_completed"
STAGE_FAILED = "stage_failed"

# Agent activity (Plan 4 does not emit these yet — tools and agents do in
# later plans. Reserved here so WS handlers can filter consistently.)
AGENT_THINKING = "agent_thinking"
AGENT_TOOL_CALL = "agent_tool_call"
AGENT_DIALOGUE = "agent_dialogue"

# Pipeline routing
TRANSITION = "transition"
CHECKPOINT_REACHED = "checkpoint_reached"

# Observability
COST_UPDATE = "cost_update"
ERROR = "error"
