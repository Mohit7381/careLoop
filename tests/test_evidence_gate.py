"""The evidence gate for generated prose.

The Reporter's narrative and the PRD are the only two places a model writes
free text that a human then approves and forwards. Same rule the Analyst has
always had: cite what you were shown, or it does not ship.
"""
from app.agents.evidence_gate import numbers_in_text, unsupported_numbers

INPUTS = {"entered": 647191, "converted": 229622, "rate": 0.3654,
          "reviews": 41, "nested": [{"lost": 417569}]}


def test_grounded_prose_passes():
    text = ("647,191 orders entered and 229,622 confirmed; the clean-cart rate is "
            "36.5% and 41 reviews mention it. 417,569 were lost.")
    assert unsupported_numbers(text, INPUTS) == []


def test_a_percentage_traces_back_to_its_rate():
    """A model shown 0.3654 may legitimately write "36.5%"."""
    assert unsupported_numbers("confirmation sits at 36.5%", INPUTS) == []
    assert unsupported_numbers("confirmation sits at 0.365", {"rate": 36.54}) == []


def test_an_invented_absolute_is_caught():
    """The exact shape we are guarding against: a plausible-looking projection
    the model computed itself rather than being given."""
    assert unsupported_numbers("recover 5%, about 3,400 orders a week", INPUTS) == [3400.0]


def test_structure_and_dates_are_not_claims():
    text = ("See FR-07 in Section 3. Window 2026-08-27 to 2026-09-02. "
            "At most 2 quotes, 5% uplift target.")
    assert unsupported_numbers(text, INPUTS) == []


def test_labelled_requirement_ids_are_not_read_as_magnitudes():
    assert 7.0 not in numbers_in_text("FR-07 and NFR-3 and OQ-12")


def test_empty_inputs_reject_every_real_number():
    assert unsupported_numbers("we lost 417,569 orders", {}) == [417569.0]


def test_numbers_inside_shown_strings_are_shown_numbers():
    """Live run 7's PRD was rejected for citing the funnel counts, which live
    inside evidence `metric` strings, and a reviewer quote's "61rb". The model
    repeated what it was given; that is not invention."""
    inputs = {"finding": {"evidence": [{"metric": "1_item entered 315,934 converted 139,707 rate 0.4422",
                                        "value": 0.4422}]},
              "anecdotal_quotes": [{"text": "sia sia saya ngeluarin uang, meskipun cuma 61rb"}]}
    text = "Single-item baskets (315,934 entered, 139,707 converted) — one user lost 61rb."
    assert unsupported_numbers(text, inputs) == []
    # ...and a number that appears nowhere, string or leaf, is still caught
    assert unsupported_numbers("this will recover 3,400 orders", inputs) == [3400.0]


def test_status_codes_and_units_are_not_claims_but_bare_counts_are():
    """Run 8's model-written PRD was refused in full for 'result: 200/400' in
    its API-contract section. Real PRDs are full of such numbers."""
    inputs = {"lost": 417569}
    ok = ("POST /v1/checkout/abandon-reason — result: 200/400. Returns 404 when unknown. "
          "HTTP 200 OK. p95 latency under 200 ms, payload below 50 KB, 95% of sessions, "
          "retry after 30 seconds, 2 hours, 3 days, a 1.5x uplift, +2.5pp.")
    assert unsupported_numbers(ok, inputs) == []
    # ...while an invented magnitude with no unit is still caught
    assert unsupported_numbers("this will recover 200 orders a day", inputs) == [200.0]
    assert unsupported_numbers("about 3,400 confirmations", inputs) == [3400.0]
