"""Stage I/O contracts for the `data_preparation` stage.

Capabilities (A8 allow-list reference): fs_read, fs_write, code_exec.

Tool grounding:
- prep_script: filesystem.write_file path wrapped as ArtifactRef
- splits: dict keys train/val/test; each value is a filesystem.write_file ArtifactRef
- transforms: LLM-described list of data transformations applied
- exec_log: direct code.exec payload (stdout, stderr, exit_code)
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict

from agentlabx.stages.contracts._shared import (
    ArtifactRef,
    DatasetRef,
    ExecLog,
)


class DataPreparationInput(BaseModel):  # type: ignore[explicit-any]
    """Input contract for the data_preparation stage."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    dataset: DatasetRef
    characterization: str
    plan_excerpt: str


class DataPreparationOutput(BaseModel):  # type: ignore[explicit-any]
    """Output contract for the data_preparation stage."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    prep_script: ArtifactRef  # [← filesystem.write_file]
    splits: dict[str, ArtifactRef]  # keys train/val/test; [← code.exec produces files]
    transforms: list[str]  # [LLM]
    exec_log: ExecLog  # [← code.exec]


__all__ = [
    "DataPreparationInput",
    "DataPreparationOutput",
]
