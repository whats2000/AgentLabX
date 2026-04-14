"""report_writing migration (Plan 7E B3) — per-section prior bypass."""
from __future__ import annotations

from agentlabx.core.state import ReportResult, create_initial_state
from agentlabx.stages.report_writing import ReportWritingStage


def test_report_build_plan_itemizes_six_sections():
    stage = ReportWritingStage()
    state = create_initial_state(session_id="s1", user_id="u1", research_topic="t")
    plan = stage.build_plan(state, feedback=None)
    ids = {i["id"] for i in plan["items"]}
    for section in ("abstract", "introduction", "methodology", "results", "discussion", "conclusion"):
        assert f"report:{section}" in ids, f"missing section {section!r}; ids={ids}"


def test_report_prior_bypass_marks_present_sections_done():
    stage = ReportWritingStage()
    state = create_initial_state(session_id="s1", user_id="u1", research_topic="t")
    state["report"] = [
        ReportResult(
            latex_source="...",
            sections={
                "abstract": "abstract text",
                "introduction": "intro text",
            },
            compiled_pdf_path=None,
        )
    ]
    plan = stage.build_plan(state, feedback=None)
    statuses = {i["id"]: i["status"] for i in plan["items"] if i["id"].startswith("report:")}
    # Sections in prior get done; others stay todo
    assert statuses["report:abstract"] == "done"
    assert statuses["report:introduction"] == "done"
    assert statuses["report:methodology"] == "todo"
    assert statuses["report:results"] == "todo"


def test_report_feedback_prevents_all_bypasses():
    stage = ReportWritingStage()
    state = create_initial_state(session_id="s1", user_id="u1", research_topic="t")
    state["report"] = [
        ReportResult(
            latex_source="x",
            sections={"abstract": "x"},
            compiled_pdf_path=None,
        )
    ]
    plan = stage.build_plan(state, feedback="major rewrite")
    statuses = {i["id"]: i["status"] for i in plan["items"] if i["id"].startswith("report:")}
    # Feedback forces all sections back to todo
    for section in ("abstract", "introduction", "methodology", "results", "discussion", "conclusion"):
        assert statuses.get(f"report:{section}") == "todo"


def test_report_build_plan_feedback_item():
    stage = ReportWritingStage()
    state = create_initial_state(session_id="s1", user_id="u1", research_topic="t")
    plan = stage.build_plan(state, feedback="shorten introduction")
    fb = [i for i in plan["items"] if i["source"] == "feedback"]
    assert len(fb) >= 1
