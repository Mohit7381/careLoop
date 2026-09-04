"""prd_generator.py's _requirements_block — merges CodeGap remedies and
Suggestions (tech/business/process) into ONE continuously-numbered FR
list, so a business/process change reads as just as valid a requirement
as a code fix (Harshit's ask, 2026-09-04 hackathon chat) rather than a
second-class appendix."""
from app.pipeline.nodes.prd_generator import _render_prd_llm_stub, _requirements_block
from app.schemas.contracts import CodeGap, Finding, Remedy, Suggestion, TrendReport


def _gap(remedies=None) -> CodeGap:
    return CodeGap(
        finding_rank=1, origin="warehouse", stage="pharmacy_checkout",
        service="oms", repo="timor/oms", mechanism_found=True,
        gap_class="missing_retention_hook", gap_statement="g", file="F.java", line=1,
        remedies=remedies or [],
    )


def _suggestion(suggestion_type="business", verification_status="not_applicable", **kw) -> Suggestion:
    return Suggestion(
        finding_rank=1, origin="warehouse", stage="pharmacy_checkout",
        service="oms", repo="timor/oms",
        suggestion_type=suggestion_type, title="Title", description="Desc", rationale="Because",
        verification_status=verification_status, **kw,
    )


def test_numbering_continues_from_remedies_into_suggestions():
    gap = _gap(remedies=[
        Remedy(proposal="r1", signature="s1", status="absent", searched_terms=["a"]),
        Remedy(proposal="r2", signature="s2", status="exists", evidence_file="F.java", evidence_line=5),
    ])
    suggestions = [_suggestion(suggestion_type="business")]

    block = _requirements_block(gap, suggestions)

    assert "FR-1:" in block and "FR-2:" in block and "FR-3:" in block
    assert "FR-4:" not in block


def test_business_suggestion_is_labelled_and_not_conflated_with_a_code_remedy():
    block = _requirements_block(None, [_suggestion(suggestion_type="business")])
    assert "FR-1:" in block
    assert "**[Business suggestion]**" in block


def test_suggestion_verification_states_are_distinguishable():
    absent = _requirements_block(None, [_suggestion(suggestion_type="tech", verification_status="absent")])
    exists = _requirements_block(None, [_suggestion(suggestion_type="tech", verification_status="exists", evidence_file="F.java", evidence_line=3)])
    unverified = _requirements_block(None, [_suggestion(suggestion_type="tech", verification_status="unverified")])

    assert "not found in code" in absent
    assert "already built" in exists
    assert "unverified" in unverified.lower()


def test_no_gap_and_no_suggestions_is_an_empty_block_not_a_fabrication():
    assert _requirements_block(None, []) == ""


def test_render_stub_uses_suggestions_as_the_solution_when_no_gap_was_located():
    """A finding can have Suggestions with no diagnosed CodeGap at all — the
    PRD must still produce a real solution section, not a TODO placeholder,
    when there's a legitimate business/process idea to act on."""
    finding = Finding(
        rank=1, origin="warehouse", stage="pharmacy_checkout",
        hypothesis="h", confidence="high", confirm_via="x",
    )
    suggestions = [_suggestion(suggestion_type="process")]

    _, body = _render_prd_llm_stub(
        finding, gaps=[], suggestions=suggestions, trend=TrendReport(),
        quotes=[], run_id=1, window_start="a", window_end="b",
    )

    assert "no code gap was located" in body  # honest about why — not silently omitted
    assert "FR-1:" in body
    assert "TODO(Code Scout): pipeline ran without a resolved code_gap" not in body


def test_render_stub_falls_back_to_honest_todo_when_nothing_at_all_exists():
    finding = Finding(
        rank=1, origin="warehouse", stage="pharmacy_checkout",
        hypothesis="h", confidence="high", confirm_via="x",
    )
    _, body = _render_prd_llm_stub(
        finding, gaps=[], suggestions=[], trend=TrendReport(),
        quotes=[], run_id=1, window_start="a", window_end="b",
    )
    assert "TODO(Code Scout): pipeline ran without a resolved code_gap" in body
