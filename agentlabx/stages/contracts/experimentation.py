"""Stage I/O contracts for the `experimentation` stage.

Capabilities (A8 allow-list reference): fs_read, fs_write, code_exec, memory_write.

Tool grounding:
- metrics: parsed from code.exec.stdout (one entry per metric per run)
- artifacts: filesystem.write_file paths (model checkpoints, eval outputs)
- exec_logs: one ExecLog per run — baseline + each ablation
- memory_entries_created: memory.create.id values stored during the run

requires_reproducibility = True is set as a ClassVar on the Stage subclass
(Task 8); the ReproducibilityContract itself lives on StageOutput.reproducibility
from Task 2 and is NOT carried in this contract output.

# Capabilities: fs_read, fs_write, code_exec, memory_write
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from agentlabx.stages.contracts._shared import (
    ArtifactRef,
    ExecLog,
    Hypothesis,
    Metric,
)


class ExperimentationInput(BaseModel):  # type: ignore[explicit-any]
    """Input contract for the experimentation stage."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    hypotheses: list[Hypothesis]
    splits: dict[str, ArtifactRef]
    prep_script: ArtifactRef


class ExperimentationOutput(BaseModel):  # type: ignore[explicit-any]
    """Output contract for the experimentation stage."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    metrics: list[Metric]  # ≥1; [← parsed from code.exec.stdout]
    artifacts: list[ArtifactRef]  # ≥1; [← filesystem.write_file]
    exec_logs: list[ExecLog]  # one per run (baseline + ablations); [← code.exec]
    memory_entries_created: list[str] = Field(default_factory=list)  # [← memory.create.id values]


__all__ = [
    "ExperimentationInput",
    "ExperimentationOutput",
]
