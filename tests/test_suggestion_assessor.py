"""propose_search_terms() precedence: journey_events (real analytics event
names, confirmed with Nakul 2026-09-03) beat theme_search_terms and the
hypothesis-parsing fallback, regardless of origin. Also covers the D1.3 fix:
an unclassified area returns [] instead of a fabricated placeholder.
"""
from app.agents.code_scout.explore_search_client import GapLocation
from app.agents.code_scout.suggestion_assessor import StubFeatureSuggestionAssessor
from app.schemas.contracts import Finding

assessor = StubFeatureSuggestionAssessor()


def _finding(**overrides) -> Finding:
    kwargs = dict(
        rank=1,
        origin="warehouse",
        stage="consultation",
        hypothesis="51,321/wk consultations killed by a silent timeout",
        confidence="high",
        confirm_via="check re-engagement CT events post-cancel",
    )
    kwargs.update(overrides)
    return Finding(**kwargs)


def test_journey_events_take_priority_when_present():
    finding = _finding(journey_events=["consultation_payment_started", "consultation_payment_timeout"])
    assert assessor.propose_search_terms(finding) == [
        "consultation_payment_started",
        "consultation_payment_timeout",
    ]


def test_journey_events_beat_theme_search_terms_even_for_voc_origin():
    finding = _finding(
        origin="voc",
        journey_events=["pharmacy_checkout_start"],
        theme_search_terms=["abandon"],
    )
    assert assessor.propose_search_terms(finding) == ["pharmacy_checkout_start"]


def test_theme_search_terms_used_when_no_journey_events():
    finding = _finding(origin="voc", theme_search_terms=["abandon"])
    assert assessor.propose_search_terms(finding) == ["abandon"]


def test_falls_back_to_hypothesis_parsing_when_neither_is_set():
    finding = _finding()
    terms = assessor.propose_search_terms(finding)
    assert terms  # non-empty
    assert "consultations" in terms


def test_unclassified_area_returns_no_suggestions_not_a_fabricated_placeholder():
    """review D1.3: an area with no hand-verified suggestion used to return
    a generic 'Investigate further' tech suggestion - indistinguishable on a
    projector from a real recommendation. Must report zero honestly."""
    finding = _finding()
    unclassified = [GapLocation(file="SomeUnrelatedFile.java", line=1, snippet="...")]
    assert assessor.propose_suggestions(finding, unclassified) == []


def test_no_inventory_returns_no_suggestions():
    finding = _finding()
    assert assessor.propose_suggestions(finding, []) == []
