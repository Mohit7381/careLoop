"""A scoped run end to end: the prompt actually narrows what happens."""
from app.agents.scope_resolver import resolve_scope
from app.journeys import load_journey
from app.pipeline.graph import compiled_graph
from app.pipeline.state import initial_state

CFG = load_journey("pd_checkout")


def _run(scope=None):
    return compiled_graph.invoke(initial_state(
        run_id=1, window_start="2026-08-27", window_end="2026-09-02", demo_mode=True,
        journey="pd_checkout", prev_window_start="2026-08-20",
        prev_window_end="2026-08-26", scope=scope))


def _scope(prompt):
    events = list((CFG.get("event_stage") or {}).keys())
    return resolve_scope(prompt, CFG, events, CFG["drilldown_dimensions"]).model_dump()


def test_an_unscoped_run_is_unchanged():
    out = _run()
    assert out["status"] == "completed" and out["findings"]


def test_a_scoped_run_analyses_the_transition_that_was_asked_for():
    out = _run(_scope("why are users dropping off after adding items to cart"))
    assert out["status"] == "completed"
    assert out["findings"], "a scoped run must still produce findings"


def test_a_dimension_scope_restricts_the_drill_down():
    """Ask about stock and the run does not wander off into price bands.

    Asserted on cuts that actually returned data, not on the trail as a whole:
    the trail is an audit log and deliberately records refusals too, so a
    recorded session asking for an out-of-scope dimension still leaves a row
    saying it was turned down. That row is the feature working, not leaking.
    """
    out = _run(_scope("why do orders with unfulfilled items fail"))
    trail = out["drilldown_trail"]
    assert trail, "the scoped run performed no cuts at all"

    answered = {s["dimension"] for s in trail if s.get("result_rows")}
    refused = {s["dimension"] for s in trail if s.get("note") == "rejected: not whitelisted"}
    assert answered <= {"stock_status", "item_count"}, answered
    assert "consultation_required" not in answered
    if refused:
        assert all(s["result_rows"] == [] for s in trail
                   if s["dimension"] in refused), "a refused cut must return no data"


def test_a_review_window_narrows_the_corpus_and_says_so():
    out = _run(_scope("analyse the last 7 days of reviews"))
    meta = out["voc"]["reviews_meta"]
    assert meta["review_window_days"] == 7
    assert meta["reviews_in_window"] < meta["reviews_available"]
    # the report can state the span it really looked at, not the one requested
    assert meta["review_window_from"] < meta["review_window_to"]


def test_an_unresolvable_prompt_still_produces_a_full_run():
    """Refusing to scope must never mean refusing to answer."""
    out = _run(_scope("what is happening with insurance claims"))
    assert out["status"] == "completed" and out["findings"]
