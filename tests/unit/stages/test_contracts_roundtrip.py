"""Round-trip tests for agentlabx.stages.contracts shared sub-models (A4 Task 3)."""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime
from typing import TypedDict

import pytest
from pydantic import ValidationError

from agentlabx.stages.contracts import (
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

# ---------------------------------------------------------------------------
# TypedDict helpers — avoid dict[str, object] per project convention
# ---------------------------------------------------------------------------


class _MemoryEntryRefDict(TypedDict):
    id: str
    category: str
    body: str
    source_run_id: str | None
    created_at: str


# ---------------------------------------------------------------------------
# Round-trip helpers
# ---------------------------------------------------------------------------


def _round_trip_note_ref() -> None:
    original = NoteRef(id="n1", category="finding")
    dumped = original.model_dump(mode="json")
    restored = NoteRef.model_validate(dumped)
    assert restored == original


def _round_trip_research_question() -> None:
    original = ResearchQuestion(text="What is the effect of X?", project_id="proj-42")
    dumped = original.model_dump(mode="json")
    restored = ResearchQuestion.model_validate(dumped)
    assert restored == original


def _round_trip_hypothesis() -> None:
    original = Hypothesis(
        id="h1",
        statement="X improves Y by Z%",
        baselines=["vanilla_transformer"],
        ablations=["no_attention", "no_ffn"],
    )
    dumped = original.model_dump(mode="json")
    restored = Hypothesis.model_validate(dumped)
    assert restored == original


def _round_trip_dataset_ref() -> None:
    original = DatasetRef(dataset_id="ds-1", name="ImageNet", split_hint="train")
    dumped = original.model_dump(mode="json")
    restored = DatasetRef.model_validate(dumped)
    assert restored == original


def _round_trip_dataset_ref_no_split() -> None:
    original = DatasetRef(dataset_id="ds-2", name="CIFAR-10", split_hint=None)
    dumped = original.model_dump(mode="json")
    restored = DatasetRef.model_validate(dumped)
    assert restored == original


def _round_trip_metric() -> None:
    original = Metric(name="accuracy", value=0.9342, unit="%")
    dumped = original.model_dump(mode="json")
    restored = Metric.model_validate(dumped)
    assert restored == original


def _round_trip_chunk_ref() -> None:
    original = ChunkRef(
        chunk_id="c-1",
        paper_id="2304.12345",
        span_start=0,
        span_end=512,
        score=0.87,
    )
    dumped = original.model_dump(mode="json")
    restored = ChunkRef.model_validate(dumped)
    assert restored == original


def _round_trip_artifact_ref() -> None:
    original = ArtifactRef(
        artifact_id="a-1",
        kind="model",
        path="/workspace/runs/run-1/model.pt",
        content_hash="sha256:deadbeef" * 4,
    )
    dumped = original.model_dump(mode="json")
    restored = ArtifactRef.model_validate(dumped)
    assert restored == original


def _round_trip_exec_log() -> None:
    original = ExecLog(stdout="loss: 0.42\n", stderr="", exit_code=0)
    dumped = original.model_dump(mode="json")
    restored = ExecLog.model_validate(dumped)
    assert restored == original


def _round_trip_memory_entry_ref() -> None:
    original = MemoryEntryRef(
        id="m-1",
        category="experiment",
        body="baseline acc = 0.75",
        source_run_id="run-1",
        created_at=datetime.fromisoformat("2026-05-15T12:34:56+00:00"),
    )
    dumped = original.model_dump(mode="json")
    restored = MemoryEntryRef.model_validate(dumped)
    assert restored == original


def _round_trip_finding() -> None:
    original = Finding(
        id="f-1",
        statement="Model achieves 93.4% accuracy.",
        cited_metric_names=["accuracy"],
        cited_artifact_ids=["a-1"],
        cited_chunk_ids=["c-1"],
        verbatim_values={"accuracy": 0.9342},
    )
    dumped = original.model_dump(mode="json")
    restored = Finding.model_validate(dumped)
    assert restored == original


def _round_trip_action_item() -> None:
    original = ActionItem(
        id="ai-1",
        severity="major",
        description="Missing ablation study.",
        target_section="§4 Experiments",
    )
    dumped = original.model_dump(mode="json")
    restored = ActionItem.model_validate(dumped)
    assert restored == original


def _round_trip_citation_summary() -> None:
    chunk = ChunkRef(
        chunk_id="c-2",
        paper_id="1706.03762",
        span_start=100,
        span_end=200,
        score=0.95,
    )
    original = CitationSummary(
        citation_id="cit-1",
        paragraph="Attention Is All You Need introduced the Transformer architecture.",
        chunk_refs=[chunk],
    )
    dumped = original.model_dump(mode="json")
    restored = CitationSummary.model_validate(dumped)
    assert restored == original


# ---------------------------------------------------------------------------
# Parametrized round-trip (one test per model)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "fn",
    [
        _round_trip_note_ref,
        _round_trip_research_question,
        _round_trip_hypothesis,
        _round_trip_dataset_ref,
        _round_trip_dataset_ref_no_split,
        _round_trip_metric,
        _round_trip_chunk_ref,
        _round_trip_artifact_ref,
        _round_trip_exec_log,
        _round_trip_memory_entry_ref,
        _round_trip_finding,
        _round_trip_action_item,
        _round_trip_citation_summary,
    ],
    ids=[
        "NoteRef",
        "ResearchQuestion",
        "Hypothesis",
        "DatasetRef",
        "DatasetRef_no_split",
        "Metric",
        "ChunkRef",
        "ArtifactRef",
        "ExecLog",
        "MemoryEntryRef",
        "Finding",
        "ActionItem",
        "CitationSummary",
    ],
)
def test_round_trip(fn: Callable[[], None]) -> None:
    """Each shared model round-trips through model_dump(mode='json') → model_validate."""
    fn()


# ---------------------------------------------------------------------------
# MemoryEntryRef — ISO-8601 string → datetime
# ---------------------------------------------------------------------------


def test_memory_entry_ref_iso8601_datetime() -> None:
    """ISO-8601 string in created_at is parsed to a timezone-aware datetime."""
    payload: _MemoryEntryRefDict = {
        "id": "m-iso",
        "category": "experiment",
        "body": "test body",
        "source_run_id": None,
        "created_at": "2026-05-15T12:34:56+00:00",
    }
    result = MemoryEntryRef.model_validate(payload)
    assert isinstance(result.created_at, datetime)
    assert result.created_at.tzinfo is not None


# ---------------------------------------------------------------------------
# Citation — arxiv-source round-trip
# ---------------------------------------------------------------------------


def test_citation_arxiv_round_trip() -> None:
    """Citation with source='arxiv' round-trips; S2-only fields are None/empty."""
    original = Citation(
        paper_id="2304.12345",
        title="Attention Is All You Need",
        authors=["Vaswani, A.", "Shazeer, N."],
        year=2017,
        source="arxiv",
        url="https://arxiv.org/abs/1706.03762",
        external_ids={},
        abstract="We propose the Transformer.",
        venue=None,
        citation_count=None,
        fields_of_study=["cs.CL", "cs.LG"],
        open_access_pdf_url="https://arxiv.org/pdf/1706.03762",
    )
    dumped = original.model_dump(mode="json")
    restored = Citation.model_validate(dumped)
    assert restored == original
    assert restored.venue is None
    assert restored.citation_count is None
    assert restored.external_ids == {}


# ---------------------------------------------------------------------------
# Citation — semantic_scholar-source round-trip
# ---------------------------------------------------------------------------


def test_citation_semantic_scholar_round_trip() -> None:
    """Citation with source='semantic_scholar' round-trips with S2-specific fields."""
    original = Citation(
        paper_id="204e3073870fae3d05bcbc2f6a8e263d9b72e776",
        title="Attention Is All You Need",
        authors=["Vaswani, A.", "Shazeer, N."],
        year=2017,
        source="semantic_scholar",
        url="https://api.semanticscholar.org/paper/204e3073870fae3d05bcbc2f6a8e263d9b72e776",
        external_ids={"DOI": "10.x/y", "ArXiv": "2304.12345"},
        venue="NeurIPS",
        citation_count=42,
        fields_of_study=["Computer Science"],
        open_access_pdf_url=None,
    )
    dumped = original.model_dump(mode="json")
    restored = Citation.model_validate(dumped)
    assert restored == original
    assert restored.venue == "NeurIPS"
    assert restored.citation_count == 42
    assert restored.external_ids == {"DOI": "10.x/y", "ArXiv": "2304.12345"}


# ---------------------------------------------------------------------------
# ExecLog — timeout case
# ---------------------------------------------------------------------------


def test_exec_log_timeout_case() -> None:
    """ExecLog with exit_code=-1 (timeout) round-trips correctly."""
    original = ExecLog(stdout="", stderr="Process timed out after 30s.", exit_code=-1)
    dumped = original.model_dump(mode="json")
    restored = ExecLog.model_validate(dumped)
    assert restored == original
    assert restored.exit_code == -1
    assert "timed out" in restored.stderr


# ---------------------------------------------------------------------------
# ChunkRef span validator — positive case
# ---------------------------------------------------------------------------


def test_chunk_ref_span_valid() -> None:
    """ChunkRef with span_start=10, span_end=20 constructs without error."""
    chunk = ChunkRef(
        chunk_id="c-ok",
        paper_id="p-1",
        span_start=10,
        span_end=20,
        score=0.5,
    )
    assert chunk.span_start == 10
    assert chunk.span_end == 20


# ---------------------------------------------------------------------------
# ChunkRef span validator — negative case
# ---------------------------------------------------------------------------


def test_chunk_ref_span_invalid() -> None:
    """ChunkRef with span_start > span_end raises ValidationError."""
    with pytest.raises(ValidationError):
        ChunkRef(
            chunk_id="c-bad",
            paper_id="p-1",
            span_start=20,
            span_end=10,
            score=0.5,
        )
