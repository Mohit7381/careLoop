"""app/scope_resolver.py — the "resolve prose to structured parameters"
half of prompt-scoped analysis (decision #13). Rule-based on purpose: a
wrong guess here silently narrows what a run even looks at, so an
unmatched message must say so honestly rather than default to guessing
the whole journey."""
from app.scope_resolver import resolve_dimensions


def test_direct_category_name_resolves():
    dims, reply = resolve_dimensions("pd_checkout", "just look at payments please")
    assert dims == ["payments"]
    assert "payments" in reply


def test_english_synonym_resolves():
    dims, reply = resolve_dimensions("pd_checkout", "analyze cart abandonment dropoff")
    assert dims == ["pharmacy_checkout"]


def test_multiple_categories_in_one_message():
    dims, _ = resolve_dimensions("pd_checkout", "look at payments and delivery issues")
    assert set(dims) == {"payments", "delivery"}


def test_underscore_category_name_with_a_space_resolves():
    dims, _ = resolve_dimensions("pd_checkout", "focus on pharmacy checkout only")
    assert dims == ["pharmacy_checkout"]


def test_unmatched_message_is_an_honest_empty_result_not_a_guess():
    dims, reply = resolve_dimensions("pd_checkout", "tell me something interesting")
    assert dims == []
    assert "couldn't match" in reply
    # the reply must actually name the real categories rather than a vague apology
    assert "payments" in reply and "consultation" in reply


def test_empty_message_does_not_crash():
    dims, reply = resolve_dimensions("pd_checkout", "")
    assert dims == []
    assert reply
