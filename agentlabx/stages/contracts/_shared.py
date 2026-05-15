"""Shared sub-models for stage contracts. Task 3 extends this file."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class NoteRef(BaseModel):  # type: ignore[explicit-any]
    """A7 hook placeholder. Task 3 may extend with body / created_at."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    id: str
    category: str


# ---------------------------------------------------------------------------
# Identity / domain primitives
# ---------------------------------------------------------------------------


class ResearchQuestion(BaseModel):  # type: ignore[explicit-any]
    """A research question tied to a project — internal stage glue."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    text: str
    project_id: str


class Hypothesis(BaseModel):  # type: ignore[explicit-any]
    """LLM-synthesised hypothesis with ablation and baseline references."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    id: str
    statement: str
    baselines: list[str]
    ablations: list[str]


class DatasetRef(BaseModel):  # type: ignore[explicit-any]
    """Reference to a dataset, optionally specifying a split hint — internal."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    dataset_id: str
    name: str
    split_hint: str | None


class Metric(BaseModel):  # type: ignore[explicit-any]
    """A named scalar metric parsed from code.exec stdout."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    name: str
    value: float
    unit: str | None


# ---------------------------------------------------------------------------
# Citation (normalised across arxiv + S2)
# ---------------------------------------------------------------------------


class Citation(BaseModel):  # type: ignore[explicit-any]
    """Normalised citation record from arxiv or Semantic Scholar.

    ``paper_id`` is the arxiv id when ``source=="arxiv"`` and the S2
    ``paperId`` when ``source=="semantic_scholar"``.  Pair with ``source`` to
    disambiguate.

    ``external_ids`` is populated from S2 ``externalIds`` (DOI, ArXiv, MAG,
    PubMed); it is empty for arxiv-sourced citations.

    ``year`` is parsed from ``published_date`` for arxiv-sourced citations.

    ``venue``, ``citation_count`` are only meaningful for S2 sources.
    ``fields_of_study`` is the union of S2 ``fieldsOfStudy`` and arxiv
    ``categories``.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    paper_id: str
    title: str
    authors: list[str]
    year: int
    source: Literal["arxiv", "semantic_scholar", "other"]
    url: str | None
    external_ids: dict[str, str] = Field(default_factory=dict)
    abstract: str | None = None
    venue: str | None = None
    citation_count: int | None = None
    fields_of_study: list[str] = Field(default_factory=list)
    open_access_pdf_url: str | None = None


# ---------------------------------------------------------------------------
# RAG / grounding
# ---------------------------------------------------------------------------


class ChunkRef(BaseModel):  # type: ignore[explicit-any]
    """Flat span reference to a chunk in a paper — survives Chroma round-trip.

    Flat ``span_start`` / ``span_end`` fields are used instead of a tuple
    because tuples do not survive Chroma metadata round-trips (I-4 fix).
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    chunk_id: str
    paper_id: str
    span_start: int
    span_end: int
    score: float

    @model_validator(mode="after")
    def _check_span_ordering(self) -> ChunkRef:
        if self.span_end < self.span_start:
            raise ValueError(
                f"span_end ({self.span_end}) must be >= span_start ({self.span_start})"
            )
        return self


# ---------------------------------------------------------------------------
# Artifacts (filesystem-produced + stage-hashed)
# ---------------------------------------------------------------------------


class ArtifactRef(BaseModel):  # type: ignore[explicit-any]
    """Reference to a filesystem artifact produced by a stage.

    ``path`` is the absolute path passed to ``filesystem.write_file``.
    ``content_hash`` is computed in stage code (SHA-256 of bytes after write)
    — the filesystem MCP tool returns no hash; stage code must compute it.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    artifact_id: str
    kind: Literal["dataset", "split", "script", "model", "report", "plot", "table", "other"]
    path: str
    content_hash: str


# ---------------------------------------------------------------------------
# Tool-output sub-models
# ---------------------------------------------------------------------------


class ExecLog(BaseModel):  # type: ignore[explicit-any]
    """Exact match to the ``code.exec`` MCP tool payload.

    ``exit_code=-1`` indicates a timeout.  Streams are pre-truncated upstream
    at 256 KiB before this model is constructed.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    stdout: str
    stderr: str
    exit_code: int


class MemoryEntryRef(BaseModel):  # type: ignore[explicit-any]
    """Exact match to a ``memory.get`` / ``memory.search`` element.

    ``created_at`` arrives as an ISO-8601 string on the wire; Pydantic parses
    it to ``datetime`` automatically in ``mode="json"``.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    id: str
    category: str
    body: str
    source_run_id: str | None
    created_at: datetime


# ---------------------------------------------------------------------------
# Cross-stage synthesis-side models
# ---------------------------------------------------------------------------


class Finding(BaseModel):  # type: ignore[explicit-any]
    """A synthesised research finding with full provenance.

    ``verbatim_values`` reproduces the exact ``Metric.value`` floats referenced
    by this finding (anti-fabrication requirement per SRS B6).

    ``cited_chunk_ids`` enables per-finding RAG grounding for the B7 citation
    verifier (I-2 fix).
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    id: str
    statement: str
    cited_metric_names: list[str]
    cited_artifact_ids: list[str]
    cited_chunk_ids: list[str] = Field(default_factory=list)
    verbatim_values: dict[str, float]


class ActionItem(BaseModel):  # type: ignore[explicit-any]
    """A review action item produced by ``peer_review``."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    id: str
    severity: Literal["minor", "major", "blocker"]
    description: str
    target_section: str | None


class CitationSummary(BaseModel):  # type: ignore[explicit-any]
    """Used by ``literature_review.summaries``.

    Each summary paragraph traces to one citation and its supporting RAG
    chunks.  Placed in ``_shared.py`` because ``ChunkRef`` is already shared
    and future stages (e.g. plan_formulation) may iterate summaries.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    citation_id: str
    paragraph: str
    chunk_refs: list[ChunkRef]


# ---------------------------------------------------------------------------
# Public surface
# ---------------------------------------------------------------------------

__all__ = [
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
]
