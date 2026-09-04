"""Code Scout searches for things that exist in code.

Run 3 (live) searched timor/oms for pharmacy.click.confirm_cart_button,
3_to_5_items and basket_size, exhausted its budget and found nothing. Those are
analytics events and segment labels. Verified against GitLab the same day:
every one of them scores 0 source hits, while abandon / CartItem / erx score
6 / 7 / 11. Seeds now come from the journey's verified code_hints first.
"""
from app.agents.code_scout.assessor import StubCodeGapAssessor
from app.agents.code_scout.node import seed_search_terms
from app.agents.code_scout.search_client import normalise_term
from app.journeys import load_journey
from app.schemas.contracts import DrilldownStep, EvidenceItem, Finding

CFG = load_journey("pd_checkout")


def _finding(**kw):
    base = dict(rank=2, origin="warehouse", stage="pharmacy_checkout", confidence="medium",
                hypothesis="Basket size correlates with conversion: 1_item converts at 0.4422 vs 3_to_5_items 0.2494",
                confirm_via="hold basket size and measure",
                evidence=[EvidenceItem(type="drilldown", metric="1_item: rate=0.4422", value=0.4422)],
                journey_events=["pharmacy.click.confirm_cart_button", "pharmacy.backend.transaction_confirmed"])
    base.update(kw)
    return Finding(**base)


TRAIL = [DrilldownStep(question="q", dimension="item_count",
                       result_rows=[{"segment": "1_item", "entered": 315934, "converted": 139707},
                                    {"segment": "3_to_5_items", "entered": 176399, "converted": 43996}])]


def test_code_hints_for_the_cited_cut_come_first_and_events_last():
    terms = seed_search_terms(_finding(), StubCodeGapAssessor(), CFG, TRAIL)
    assert terms[:2] == ["CartItem", "quantity"], terms           # item_count hints
    assert "abandon" in terms[2:5]                                 # pharmacy_checkout hints
    events = [t for t in terms if t.startswith("pharmacy.")]
    assert events and terms.index(events[0]) > terms.index("abandon"), terms


def test_a_finding_that_cites_no_cut_still_gets_its_stage_hints():
    f = _finding(hypothesis="Most loss is at created->confirmed", evidence=[], journey_events=[])
    terms = seed_search_terms(f, StubCodeGapAssessor(), CFG, TRAIL)
    assert terms[:3] == ["abandon", "abandonOrder", "timeToAbandon"]


def test_voc_multiword_theme_terms_are_reduced_to_a_searchable_token():
    f = _finding(origin="voc", stage="payments", review_count=41, theme="payment/refund",
                 theme_search_terms=["payment_failed", "refund", "payment timeout"],
                 journey_events=[], evidence=[])
    terms = seed_search_terms(f, StubCodeGapAssessor(), CFG, [])
    assert "payment timeout" not in terms and "timeout" in terms
    assert terms[0] == "timeout"                                   # payments stage hint, verified 6 hits


def test_normalise_term_keeps_single_tokens_and_picks_the_longest_word():
    assert normalise_term("session end") == "session"
    assert normalise_term("abandonOrderV2") == "abandonOrderV2"
    assert normalise_term("  ") == ""


def test_seed_list_is_deduplicated_and_bounded():
    f = _finding(journey_events=["abandon", "abandon", "x1", "x2", "x3", "x4", "x5", "x6", "x7"])
    terms = seed_search_terms(f, StubCodeGapAssessor(), CFG, TRAIL)
    assert len(terms) == len({t.lower() for t in terms}) <= 8
