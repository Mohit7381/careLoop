"""Reporter narrative + PRD drafting through a real LLM, and what stops them.

Both nodes now call a sphere use case. Both keep their deterministic renderer
as the fallback, because these two artifacts are what a human reads and then
approves — a mechanical sentence beats a missing one, and a fabricated number
is worse than either.
"""
import json
from pathlib import Path

import pytest

from app.pipeline.nodes.prd_generator import prd_generator_node
from app.pipeline.nodes.reporter import reporter_node
from app.pipeline.state import initial_state
from app.schemas.contracts import Snapshot

FIX = Path(__file__).parent.parent / "fixtures" / "pd_checkout"


@pytest.fixture()
def reporter_state(snapshot: Snapshot) -> dict:
    st = initial_state(run_id=1, window_start="2026-08-27", window_end="2026-09-02",
                       demo_mode=True, journey="pd_checkout",
                       prev_window_start="2026-08-20", prev_window_end="2026-08-26")
    st["snapshot"] = snapshot.model_dump()
    st["voc"] = {"themes": [{"theme": "payment/refund", "count": 41}], "reviews_meta": {},
                 "per_finding_quotes": {}}
    return st


def test_narrative_uses_the_model_when_every_sentence_cites_a_row(reporter_state):
    seen = {}

    def llm(ctx):
        seen["rows"] = ctx["delta_table"]
        row = ctx["delta_table"][0]
        return {"narrative_lines": [
            {"text": f"Conversion at '{row['stage']}' moved {row['delta_pp']}pp.",
             "delta_ref": row["id"]}]}

    out = reporter_node(reporter_state, llm=llm)
    assert out["narrative_source"] == "llm"
    assert "moved" in out["trend_report"]["narrative"]
    # right-censored stages are never offered to the model in the first place
    assert all(not r["id"].startswith("stage:confirmed") for r in seen["rows"])


def test_a_sentence_citing_an_unknown_row_is_refused(reporter_state):
    llm = lambda ctx: {"narrative_lines": [
        {"text": "Deliveries collapsed 25pp.", "delta_ref": "stage:invented"}]}
    out = reporter_node(reporter_state, llm=llm)
    assert out["narrative_source"] == "dangling_delta_ref"
    assert "collapsed" not in out["trend_report"]["narrative"]


def test_a_narrative_with_an_invented_number_is_refused(reporter_state):
    def llm(ctx):
        row = ctx["delta_table"][0]
        return {"narrative_lines": [
            {"text": "That is roughly 91,428 orders a week.", "delta_ref": row["id"]}]}
    out = reporter_node(reporter_state, llm=llm)
    assert out["narrative_source"].startswith("ungrounded_numbers")


def test_a_failing_llm_still_produces_a_narrative(reporter_state):
    def boom(ctx):
        raise RuntimeError("sphere call failed")
    out = reporter_node(reporter_state, llm=boom)
    assert out["narrative_source"].startswith("llm_error")
    assert out["trend_report"]["narrative"]          # deterministic text survived


# --- PRD ---------------------------------------------------------------------

def _prd_state(analyst_state) -> dict:
    st = initial_state(run_id=1, window_start="2026-08-27", window_end="2026-09-02",
                       demo_mode=True, journey="pd_checkout")
    st.update({k: v for k, v in analyst_state.items() if k in st or k in
               ("findings", "code_gaps", "voc", "trend_report")})
    return st


def test_prd_keeps_our_draft_banner_even_if_the_model_omits_it(pipeline_state):
    body = "# Fix the abandon path\n\n## 1. Overview\n" + ("Real content. " * 30)
    out = prd_generator_node(pipeline_state, llm=lambda ctx: {"prd_markdown": body})
    assert out["prd_source"] == "llm"
    assert "DRAFT — needs human review" in out["prd_draft"]
    assert "Never auto-filed" in out["prd_draft"]


def test_prd_with_an_invented_number_falls_back(pipeline_state):
    body = ("# Fix\n\n## 1. Overview\n" + "Real content. " * 20 +
            "\nThis will recover 3,400 orders per week.")
    out = prd_generator_node(pipeline_state, llm=lambda ctx: {"prd_markdown": body})
    assert out["prd_source"].startswith("ungrounded_numbers")
    assert "3,400" not in out["prd_draft"]


def test_prd_falls_back_when_the_first_ever_call_fails(pipeline_state):
    def boom(ctx):
        raise RuntimeError("Response contains HTML tags, which are not allowed.")
    out = prd_generator_node(pipeline_state, llm=boom)
    assert out["prd_source"].startswith("llm_error")
    assert "DRAFT" in out["prd_draft"]               # deterministic PRD survived


def test_the_model_is_never_given_room_to_restate_a_verdict(pipeline_state):
    seen = {}

    def llm(ctx):
        seen["inputs"] = ctx["prd_inputs"]
        return {"prd_markdown": "# T\n\n## 1. Overview\n" + "Content. " * 40}

    prd_generator_node(pipeline_state, llm=llm)
    gap = seen["inputs"]["code_gap"]
    if gap and gap["remedies"]:
        # statuses arrive structured, not as prose the model could reword
        assert all(r["status"] in ("exists", "absent", "partial", None)
                   for r in gap["remedies"])
    assert any("never restate an absent remedy" in r for r in seen["inputs"]["rules"])


def test_bare_numbered_sections_become_markdown_headings():
    """Run 8's model draft titled sections '1 Overview (What / Problem ...)'
    with no markdown marker; the PRD drawer showed them as paragraphs."""
    from app.pipeline.nodes.prd_generator import normalise_headings
    raw = "1 Overview (What / Problem / Users / Out of Scope)\n\nWhat\n- Reduce friction.\n\n2 Goals & Success Metrics\n\n- FR-1: do a thing"
    out = normalise_headings(raw)
    assert "## 1. Overview (What / Problem / Users / Out of Scope)" in out
    assert "## 2. Goals & Success Metrics" in out
    assert "- FR-1: do a thing" in out                      # list items untouched
    already = "## 1. Overview\n\n2 Not a heading here"
    assert normalise_headings(already) == already          # drafts with headings are left alone
