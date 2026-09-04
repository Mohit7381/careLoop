"""journey_events_for() - deterministic derivation of Finding.journey_events
from the Fetcher's own ct_events (gap #4 from the PR #3 follow-up: the real
Analyst never populated this field, so Code Scout always fell through to
splitting hypothesis prose - which live-verified against real GitLab search
handed doc-file hits before any real source, review D1.2).
"""
from app.agents.analyst.journey_events import journey_events_for
from app.schemas.contracts import CtEventRow, Finding

# The real CT event names, as they appear in
# monetization_dwh.modeled_fact_halodoc_consumer_event — dotted AND
# underscored. The earlier simplified aliases (cart_add, order_abandoned)
# existed nowhere: not in the warehouse, and not in any repo Code Scout
# searches with them.
CT_EVENTS = [
    CtEventRow(event_name="pharmacy.view.product_detail_page", count=665850),
    CtEventRow(event_name="pharmacy.click.add_to_cart_button", count=633229),
    CtEventRow(event_name="pharmacy.view.cart_review_page", count=809611),
    CtEventRow(event_name="pharmacy.click.confirm_payment_button", count=96395),
    CtEventRow(event_name="pharmacy.backend.transaction_abandoned", count=244715),
]


def _finding(**overrides) -> Finding:
    kwargs = dict(
        rank=1, origin="warehouse", stage="pharmacy_checkout",
        hypothesis="h", confidence="high", confirm_via="x",
    )
    kwargs.update(overrides)
    return Finding(**kwargs)


def test_matches_order_abandoned_on_an_abandon_hypothesis():
    finding = _finding(hypothesis="176,045 orders remain unallocated due to abandonment reasons")
    events = journey_events_for(finding, CT_EVENTS)
    assert "pharmacy.backend.transaction_abandoned" in events


def test_matches_cart_events_on_a_cart_hypothesis():
    finding = _finding(hypothesis="most loss is concentrated in 'user abandon the cart'")
    events = journey_events_for(finding, CT_EVENTS)
    assert "pharmacy.click.add_to_cart_button" in events   # "cart" token
    assert "pharmacy.view.cart_review_page" in events      # needs the '.' split too
    assert "pharmacy.backend.transaction_abandoned" in events  # "abandon" stems


def test_no_overlap_returns_empty_not_a_forced_guess():
    """Conservative by design - never force an event name onto an unrelated
    finding just to have something to show."""
    finding = _finding(hypothesis="loss is concentrated in higher price bands")
    assert journey_events_for(finding, CT_EVENTS) == []


def test_voc_origin_returns_empty_has_its_own_search_terms():
    """VoC findings already have theme_search_terms from the journey config
    - journey_events is a warehouse-origin concept (real analytics events),
    not something to force onto VoC findings."""
    finding = _finding(origin="voc", hypothesis="users mention transaction_abandoned constantly")
    assert journey_events_for(finding, CT_EVENTS) == []


def test_no_ct_events_returns_empty():
    finding = _finding(hypothesis="order abandoned")
    assert journey_events_for(finding, []) == []
