"""Stage I/O contracts for the `data_exploration` stage.

Capabilities (A8 allow-list reference): fs_read, fs_write, code_exec.

Tool grounding:
- summary_stats: parsed from code.exec.stdout pandas describe() output
- plots: filesystem.write_file paths wrapped as ArtifactRef
- characterization: LLM narrative over summary_stats and plots
- exec_log: direct code.exec payload (stdout, stderr, exit_code)

Directory snapshots from filesystem.directory_tree are NOT carried — they
land in events per Q5 pushback.

# Capabilities: fs_read, fs_write, code_exec
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict

from agentlabx.stages.contracts._shared import (
    ArtifactRef,
    DatasetRef,
    ExecLog,
    Hypothesis,
)


class DataExplorationInput(BaseModel):  # type: ignore[explicit-any]
    """Input contract for the data_exploration stage."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    dataset: DatasetRef
    hypotheses: list[Hypothesis]


class DataExplorationOutput(BaseModel):  # type: ignore[explicit-any]
    """Output contract for the data_exploration stage.

    Directory snapshot NOT carried — filesystem.directory_tree payloads land in
    events.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    summary_stats: dict[str, float]  # [← parsed from code.exec.stdout pandas describe()]
    plots: list[ArtifactRef]  # [← filesystem.write_file paths]
    characterization: str  # [LLM]
    exec_log: ExecLog  # [← code.exec]


__all__ = [
    "DataExplorationInput",
    "DataExplorationOutput",
]
