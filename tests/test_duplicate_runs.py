"""Two different questions about the same week must both be allowed to run."""
from types import SimpleNamespace

from app.api.routes_analysis import find_duplicate_run


def _run(rid, prompt):
    return SimpleNamespace(id=rid, config={"scope": {"prompt": prompt}})


def test_a_different_question_on_the_same_window_is_not_a_duplicate():
    in_flight = [_run(6, "check how many and why the users are dropping off during the payments")]
    assert find_duplicate_run(in_flight, "why are users dropping off after adding items to cart") is None


def test_the_same_question_attaches_to_the_run_in_flight():
    in_flight = [_run(6, "Why are users dropping off during the payments ")]
    assert find_duplicate_run(in_flight, "why are users dropping off during the payments").id == 6


def test_an_unscoped_run_only_collides_with_another_unscoped_run():
    in_flight = [_run(1, None)]
    assert find_duplicate_run(in_flight, None).id == 1
    assert find_duplicate_run(in_flight, "any question") is None
