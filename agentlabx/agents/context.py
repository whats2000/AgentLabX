"""ContextAssembler: filters PipelineState by MemoryScope for LLM context."""

from __future__ import annotations

import json
from typing import Any

from agentlabx.agents.base import MemoryScope

# Stage output keys that live in PipelineState
STAGE_OUTPUT_KEYS: frozenset[str] = frozenset(
    {
        "literature_review",
        "plan",
        "data_exploration",
        "dataset_code",
        "experiment_results",
        "interpretation",
        "report",
        "review",
    }
)

# Keys always visible to every agent regardless of scope
ALWAYS_VISIBLE_KEYS: frozenset[str] = frozenset(
    {
        "research_topic",
        "hypotheses",
        "current_stage",
    }
)

# Internal / control keys that should never be exposed to agents
INTERNAL_KEYS: frozenset[str] = frozenset(
    {
        "session_id",
        "user_id",
        "stage_config",
        "next_stage",
        "human_override",
        "default_sequence",
        "completed_stages",
        "stage_iterations",
        "total_iterations",
        "max_stage_iterations",
        "max_total_iterations",
        "transition_log",
        "review_feedback",
        "messages",
        "errors",
        "cost_tracker",
        "pending_requests",
        "completed_requests",
    }
)


class ContextAssembler:
    """Assembles a filtered context dict from PipelineState using a MemoryScope."""

    def assemble(self, state: dict[str, Any], scope: MemoryScope) -> dict[str, Any]:
        """Return a filtered view of state according to scope.

        Always includes: research_topic, hypotheses, current_stage.
        Includes stage output keys that match read patterns.
        Includes summarize-matched keys with _summarized marker.
        Excludes internal/control keys.
        """
        context: dict[str, Any] = {}

        # Always-visible keys
        for key in ALWAYS_VISIBLE_KEYS:
            if key in state:
                context[key] = state[key]

        # Stage outputs matched by read scope
        for key in STAGE_OUTPUT_KEYS:
            if key in ALWAYS_VISIBLE_KEYS:
                continue  # already included
            if key in state and _scope_matches_key(scope, key):
                context[key] = state[key]

        # Summarize-matched fields
        for key, instruction in scope.summarize.items():
            if key in state and key not in context:
                context[key] = {
                    "_summarized": True,
                    "summary_instruction": instruction,
                    "data": state[key],
                }
            elif key in state and key in context:
                # Upgrade to summarized form if already present
                context[key] = {
                    "_summarized": True,
                    "summary_instruction": instruction,
                    "data": state[key],
                }

        return context

    def format_for_prompt(self, context: dict[str, Any]) -> str:
        """Format the assembled context dict as a string for LLM prompt injection."""
        lines: list[str] = ["=== Research Context ==="]
        for key, value in context.items():
            if key == "research_topic":
                lines.append(f"Research Topic: {value}")
            elif key == "current_stage":
                lines.append(f"Current Stage: {value}")
            else:
                lines.append(f"\n[{key.upper()}]")
                if isinstance(value, dict) and value.get("_summarized"):
                    lines.append(f"(summarize as: {value['summary_instruction']})")
                    lines.append(_serialize(value.get("data")))
                elif isinstance(value, list):
                    for item in value:
                        lines.append(_serialize(item))
                else:
                    lines.append(_serialize(value))
        return "\n".join(lines)


def _scope_matches_key(scope: MemoryScope, key: str) -> bool:
    """Check if a stage output key is readable given the scope.

    A pattern like 'literature_review.*' matches the key 'literature_review'
    (treating the whole stage output as readable when any sub-path is allowed).
    Also checks direct fnmatch (e.g. '*' matches everything).
    """
    import fnmatch as _fnmatch

    for pattern in scope.read:
        if _fnmatch.fnmatch(key, pattern):
            return True
        # 'literature_review.*' should match the top-level key 'literature_review'
        if pattern.endswith(".*"):
            prefix = pattern[:-2]
            if key == prefix:
                return True
    return False


def _serialize(obj: Any) -> str:
    """Convert an object to a readable string."""
    if hasattr(obj, "model_dump"):
        return json.dumps(obj.model_dump(), indent=2, default=str)
    if isinstance(obj, dict):
        return json.dumps(obj, indent=2, default=str)
    if isinstance(obj, list):
        return "\n".join(_serialize(item) for item in obj)
    return str(obj)
