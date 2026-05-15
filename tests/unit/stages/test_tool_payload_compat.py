"""Load-bearing grounding tests: raw MCP tool payloads → shared contract models.

Every assertion here verifies that a stage author can take a real tool response
and project it into the corresponding shared sub-model without extra fields or
manual transformation beyond what the spec documents.

This is the load-bearing assertion that A4 stays grounded — if an MCP tool
changes its payload shape and one of these tests breaks, the contracts need
updating before the stage code can trust them.
"""

from __future__ import annotations

from typing import TypedDict

import pytest

from agentlabx.stages.contracts._shared import (
    Citation,
    ExecLog,
    MemoryEntryRef,
)

# ---------------------------------------------------------------------------
# TypedDict helpers — avoid dict[str, object] per project convention
# ---------------------------------------------------------------------------


class _ExecPayload(TypedDict):
    stdout: str
    stderr: str
    exit_code: int


class _MemoryGetPayload(TypedDict):
    id: str
    category: str
    body: str
    source_run_id: str | None
    created_at: str


class _ArxivAuthorEntry(TypedDict):
    # arxiv.search_papers returns flat author strings (not dicts)
    pass


class _ArxivPaperEntry(TypedDict):
    paper_id: str
    title: str
    authors: list[str]
    abstract: str
    categories: list[str]
    published_date: str
    pdf_url: str


class _S2AuthorEntry(TypedDict):
    authorId: str
    name: str


class _S2OpenAccessPdf(TypedDict):
    url: str
    status: str


class _S2ExternalIds(TypedDict, total=False):
    DOI: str
    ArXiv: str


class _S2PaperEntry(TypedDict):
    paperId: str
    title: str
    authors: list[_S2AuthorEntry]
    abstract: str
    year: int
    citationCount: int
    referenceCount: int
    externalIds: _S2ExternalIds
    openAccessPdf: _S2OpenAccessPdf | None
    fieldsOfStudy: list[str]
    venue: str


# ---------------------------------------------------------------------------
# code.exec payload → ExecLog
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "payload",
    [
        _ExecPayload(stdout="loss: 0.42\nacc: 0.87\n", stderr="", exit_code=0),
        _ExecPayload(stdout="", stderr="Killed", exit_code=-1),
    ],
    ids=["success_case", "timeout_case"],
)
def test_exec_log_from_code_exec_payload(payload: _ExecPayload) -> None:
    """code.exec payload validates directly as ExecLog."""
    log = ExecLog.model_validate(payload)
    assert log.exit_code == payload["exit_code"]
    assert log.stdout == payload["stdout"]
    assert log.stderr == payload["stderr"]


# ---------------------------------------------------------------------------
# memory.get payload → MemoryEntryRef
# ---------------------------------------------------------------------------


def test_memory_entry_ref_from_memory_get_payload() -> None:
    """memory.get payload validates directly as MemoryEntryRef; created_at parses to datetime."""
    from datetime import datetime

    payload: _MemoryGetPayload = {
        "id": "uuid-x",
        "category": "finding",
        "body": "augmentation X hurts CT segmentation at 512x512",
        "source_run_id": None,
        "created_at": "2026-05-15T12:34:56+00:00",
    }
    ref = MemoryEntryRef.model_validate(payload)
    assert ref.id == "uuid-x"
    assert ref.category == "finding"
    assert ref.source_run_id is None
    assert isinstance(ref.created_at, datetime)
    assert ref.created_at.tzinfo is not None


# ---------------------------------------------------------------------------
# arxiv.search_papers.papers[0] → Citation projection
# ---------------------------------------------------------------------------


def test_citation_from_arxiv_payload() -> None:
    """A raw arxiv.search_papers paper dict projects cleanly into Citation.

    The point of this test: a stage author can take the raw arxiv dict and
    build a valid Citation with no extra fields needed.
    """
    arxiv: _ArxivPaperEntry = {
        "paper_id": "2304.12345v1",
        "title": "Some Title",
        "authors": ["Alice Bob"],
        "abstract": "We study augmentation for CT segmentation.",
        "categories": ["cs.LG"],
        "published_date": "2023-04-15",
        "pdf_url": "https://arxiv.org/pdf/2304.12345v1",
    }
    citation = Citation(
        paper_id=arxiv["paper_id"],
        title=arxiv["title"],
        authors=arxiv["authors"],
        year=int(arxiv["published_date"][:4]),
        source="arxiv",
        url=arxiv["pdf_url"],
        fields_of_study=arxiv["categories"],
        abstract=arxiv["abstract"],
        open_access_pdf_url=arxiv["pdf_url"],
    )
    assert citation.paper_id == "2304.12345v1"
    assert citation.year == 2023
    assert citation.source == "arxiv"
    assert citation.fields_of_study == ["cs.LG"]
    assert citation.open_access_pdf_url == "https://arxiv.org/pdf/2304.12345v1"
    # Round-trip
    restored = Citation.model_validate(citation.model_dump(mode="json"))
    assert restored == citation


# ---------------------------------------------------------------------------
# semantic_scholar.paper_relevance_search.data[0] → Citation projection
# ---------------------------------------------------------------------------


def test_citation_from_s2_payload() -> None:
    """A raw S2 paper_relevance_search dict projects cleanly into Citation.

    The point of this test: a stage author can take the raw S2 dict and
    build a valid Citation.  Loss-tolerant: unused S2 fields (venue,
    citationCount, referenceCount) map to Citation fields or are dropped.
    """
    s2: _S2PaperEntry = {
        "paperId": "abcdef123456",
        "title": "Some Title",
        "authors": [
            {"authorId": "A1", "name": "Alice"},
            {"authorId": "A2", "name": "Bob"},
        ],
        "abstract": "We study augmentation for CT segmentation.",
        "year": 2024,
        "citationCount": 42,
        "referenceCount": 100,
        "externalIds": {"DOI": "10.1234/abc", "ArXiv": "2401.99999"},
        "openAccessPdf": {"url": "https://example.org/pdf", "status": "GREEN"},
        "fieldsOfStudy": ["Computer Science"],
        "venue": "NeurIPS 2024",
    }
    open_access_url: str | None = (
        s2["openAccessPdf"]["url"] if s2["openAccessPdf"] is not None else None
    )
    citation = Citation(
        paper_id=s2["paperId"],
        title=s2["title"],
        authors=[a["name"] for a in s2["authors"]],
        year=s2["year"],
        source="semantic_scholar",
        url=None,
        external_ids={k: str(v) for k, v in s2["externalIds"].items()},
        abstract=s2["abstract"],
        venue=s2["venue"],
        citation_count=s2["citationCount"],
        fields_of_study=s2["fieldsOfStudy"],
        open_access_pdf_url=open_access_url,
    )
    assert citation.paper_id == "abcdef123456"
    assert citation.source == "semantic_scholar"
    assert citation.authors == ["Alice", "Bob"]
    assert citation.year == 2024
    assert citation.citation_count == 42
    assert citation.venue == "NeurIPS 2024"
    assert citation.external_ids == {"DOI": "10.1234/abc", "ArXiv": "2401.99999"}
    assert citation.open_access_pdf_url == "https://example.org/pdf"
    # Round-trip
    restored = Citation.model_validate(citation.model_dump(mode="json"))
    assert restored == citation


# filesystem.directory_tree payloads are NOT asserted against an A4 model;
# they live in the event log per Q5 pushback.
