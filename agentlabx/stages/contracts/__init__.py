"""Stage contracts package — re-exports all shared sub-models and per-stage I/O models."""

from __future__ import annotations

from agentlabx.stages.contracts._shared import (
    ActionItem,
    ArtifactRef,
    ChunkRef,
    Citation,
    CitationSummary,
    DatasetRef,
    ExecLog,
    Finding,
    Hypothesis,
    MemoryEntryRef,
    Metric,
    NoteRef,
    ResearchQuestion,
)
from agentlabx.stages.contracts.data_exploration import (
    DataExplorationInput,
    DataExplorationOutput,
)
from agentlabx.stages.contracts.data_preparation import (
    DataPreparationInput,
    DataPreparationOutput,
)
from agentlabx.stages.contracts.experimentation import (
    ExperimentationInput,
    ExperimentationOutput,
)
from agentlabx.stages.contracts.interpretation import (
    InterpretationInput,
    InterpretationOutput,
)
from agentlabx.stages.contracts.literature_review import (
    LiteratureReviewInput,
    LiteratureReviewOutput,
)
from agentlabx.stages.contracts.peer_review import (
    PeerReviewInput,
    PeerReviewOutput,
)
from agentlabx.stages.contracts.plan_formulation import (
    PlanFormulationInput,
    PlanFormulationOutput,
)
from agentlabx.stages.contracts.report_writing import (
    ReportWritingInput,
    ReportWritingOutput,
)

__all__ = [
    # Shared sub-models (Task 3)
    "ActionItem",
    "ArtifactRef",
    "ChunkRef",
    "Citation",
    "CitationSummary",
    "DatasetRef",
    "ExecLog",
    "Finding",
    "Hypothesis",
    "MemoryEntryRef",
    "Metric",
    "NoteRef",
    "ResearchQuestion",
    # Per-stage I/O models (Task 4)
    "DataExplorationInput",
    "DataExplorationOutput",
    "DataPreparationInput",
    "DataPreparationOutput",
    "ExperimentationInput",
    "ExperimentationOutput",
    "InterpretationInput",
    "InterpretationOutput",
    "LiteratureReviewInput",
    "LiteratureReviewOutput",
    "PeerReviewInput",
    "PeerReviewOutput",
    "PlanFormulationInput",
    "PlanFormulationOutput",
    "ReportWritingInput",
    "ReportWritingOutput",
]
