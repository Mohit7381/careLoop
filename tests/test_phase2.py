"""Drill-down loop with a scripted stub LLM — budget, whitelist, trail."""
from app.agents.analyst.aggregate_tool import AggregateTool
from app.agents.analyst.phase2 import run_drilldown

GAP = {"from_stage": "created", "to_stage": "confirmed", "lost": 417569, "share_of_prev": 0.6452}
ROUTING = ["pharmacy_checkout", "payments", "delivery", "stock", "re_engagement", "consultation"]


def make_llm(script):
    """Replays `script`, then repeats its last response.

    The exploration floor keeps asking after the model first says done, so a
    fixed-length script would StopIteration. Repeating the final response
    models the real case exactly: the model keeps insisting it is finished
    while the floor keeps making it look at another rate-bearing cut.
    """
    calls, last = iter(script), {}
    def llm(ctx):
        nonlocal last
        try:
            last = next(calls)
        except StopIteration:
            pass
        return last
    return llm


def test_happy_path_two_cuts_then_done(cohort_cuts, journey_cfg):
    tool = AggregateTool(cohort_cuts, journey_cfg["drilldown_dimensions"])
    llm = make_llm([
        {"done": False, "next_question": {"dimension": "pd_category", "rationale": "check category skew"}},
        {"done": False, "next_question": {"dimension": "consultation_required", "rationale": "check rx gating"}},
        {"done": True, "findings": [{
            "hypothesis": "rx-gated orders confirm at 30.0% vs 39.0%",
            "stage": "pharmacy_checkout", "confidence": "high",
            "evidence": ["255293", "76641", "0.300"],
            "confirm_via": "A/B a rx-cart resume nudge and compare confirm rates"}]},
    ])
    findings, trail = run_drilldown(llm, tool, GAP, {}, ROUTING, "pharmacy_checkout")
    assert [t.dimension for t in trail][:2] == ["pd_category", "consultation_required"]
    assert findings and findings[0].stage == "pharmacy_checkout"
    assert any(abs(e.value - 255293) < 1 for e in findings[0].evidence)


def test_budget_stops_a_never_done_llm(cohort_cuts, journey_cfg):
    tool = AggregateTool(cohort_cuts, journey_cfg["drilldown_dimensions"])
    llm = lambda ctx: {"done": False,
                       "next_question": {"dimension": "price_band", "rationale": "again"}}
    findings, trail = run_drilldown(llm, tool, GAP, {}, ROUTING, "pharmacy_checkout", budget=10)
    assert len(trail) == 10  # hard stop
    assert findings == []


def test_non_whitelisted_dimension_recorded_as_rejected(cohort_cuts, journey_cfg):
    tool = AggregateTool(cohort_cuts, journey_cfg["drilldown_dimensions"])
    llm = make_llm([
        {"done": False, "next_question": {"dimension": "user_phone", "rationale": "bad"}},
        {"done": True, "findings": []},
    ])
    _, trail = run_drilldown(llm, tool, GAP, {}, ROUTING, "pharmacy_checkout")
    assert trail[0].note == "rejected: not whitelisted"
    assert trail[0].result_rows == []


def test_unknown_llm_stage_falls_back_to_routing_for_gap(cohort_cuts, journey_cfg):
    tool = AggregateTool(cohort_cuts, journey_cfg["drilldown_dimensions"])
    llm = make_llm([{"done": True, "findings": [{
        "hypothesis": "h", "stage": "created→confirmed",  # funnel stage, not routing key
        "confidence": "medium", "evidence": ["647191"],
        "confirm_via": "run the confirming experiment on the gap"}]}])
    findings, _ = run_drilldown(llm, tool, GAP, {}, ROUTING, "pharmacy_checkout")
    assert findings[0].stage == "pharmacy_checkout"


def test_evidence_numbers_extracted_from_prose():
    from app.agents.analyst.phase2 import _num
    assert _num("user_total: 199,417") == 199417.0
    assert _num("rate: 0.3002") == 0.3002
    assert _num(199417) == 199417.0
    assert _num("no numbers here") is None


def test_label_glued_numbers_are_not_mistaken_for_values():
    """'price_band: 75k_200k: 90,851' must cite 90851, never 75."""
    from app.agents.analyst.phase2 import _num
    assert _num("price_band: 75k_200k: 90,851") == 90851.0
    assert _num("price_band: gte_200k: 66,220") == 66220.0
    assert _num("price_band: lt_25k: 24,769") == 24769.0
    assert _num("price_band: 25k_75k: 62,875") == 62875.0
    # trailing prose after the value: last STANDALONE number still wins
    assert _num("consultation_required: rx_gated entered: 255,293 converted: 76,641 rate: 0.3002") == 0.3002
    # all candidates glued -> fall back to the first number
    assert _num("bucket 75k_200k only") == 75.0


def test_run_cannot_conclude_with_a_rate_bearing_dimension_untried(cohort_cuts, journey_cfg):
    """The exploration floor.

    A live run was observed declaring done=True after 3 of its 10 turns,
    having never queried stock_status — a 35.8pp conversion spread — and
    settling for the 9pp rx-gated one instead. Distribution-only cuts can
    only say "most abandons look like X"; only a rate-bearing cut can say
    "X converts worse than Y", so leaving one unlooked-at is not a
    conclusion the run is allowed to reach.
    """
    tool = AggregateTool(cohort_cuts, journey_cfg["drilldown_dimensions"])
    eager_to_finish = lambda ctx: {"done": True, "findings": []}

    _, trail = run_drilldown(eager_to_finish, tool, GAP, {}, ROUTING, "pharmacy_checkout")

    tried = {t.dimension for t in trail}
    assert set(tool.rate_bearing_dimensions) <= tried, (
        f"concluded with these untried: {set(tool.rate_bearing_dimensions) - tried}")
    assert all("exploration floor" in t.question
               for t in trail), "forced cuts must say why they happened"


def test_the_floor_respects_the_budget(cohort_cuts, journey_cfg):
    """It is a floor on exploration, not a licence to exceed the hard budget."""
    tool = AggregateTool(cohort_cuts, journey_cfg["drilldown_dimensions"])
    _, trail = run_drilldown(lambda ctx: {"done": True, "findings": []},
                             tool, GAP, {}, ROUTING, "pharmacy_checkout", budget=2)
    assert len(trail) <= 2


def test_the_floor_does_not_re_query_what_the_model_already_covered(cohort_cuts, journey_cfg):
    """If the model already looked at every rate-bearing cut itself, done means done."""
    tool = AggregateTool(cohort_cuts, journey_cfg["drilldown_dimensions"])
    script = [{"done": False, "next_question": {"dimension": d, "rationale": "r"}}
              for d in tool.rate_bearing_dimensions] + [{"done": True, "findings": []}]
    _, trail = run_drilldown(make_llm(script), tool, GAP, {}, ROUTING, "pharmacy_checkout")
    assert len(trail) == len(tool.rate_bearing_dimensions)
    assert not any("exploration floor" in t.question for t in trail)


def test_two_dimensions_in_one_turn_both_land_in_the_trail(cohort_cuts, journey_cfg):
    """Template 21687 v8 lets the model name a second, untried dimension in
    next_question.also_dimension; both are aggregated before the next turn,
    so the same trail costs half the sequential model calls."""
    llm = make_llm([
        {"done": False, "next_question": {"dimension": "pd_category", "rationale": "skew",
                                          "also_dimension": "consultation_required"}},
        {"done": True, "findings": []},
    ])
    _, trail = run_drilldown(llm, AggregateTool(cohort_cuts, journey_cfg["drilldown_dimensions"]),
                             GAP, {}, ROUTING, "pharmacy_checkout", budget=10)
    assert [s.dimension for s in trail[:2]] == ["pd_category", "consultation_required"]
    assert trail[1].question.startswith("second cut this turn")


def test_a_second_dimension_that_was_already_tried_or_repeats_the_first_is_ignored(cohort_cuts, journey_cfg):
    llm = make_llm([
        {"done": False, "next_question": {"dimension": "pd_category", "rationale": "a", "also_dimension": "pd_category"}},
        {"done": False, "next_question": {"dimension": "consultation_required", "rationale": "b", "also_dimension": "pd_category"}},
        {"done": True, "findings": []},
    ])
    _, trail = run_drilldown(llm, AggregateTool(cohort_cuts, journey_cfg["drilldown_dimensions"]),
                             GAP, {}, ROUTING, "pharmacy_checkout", budget=10)
    assert [s.dimension for s in trail[:2]] == ["pd_category", "consultation_required"]
    assert len({s.dimension for s in trail}) == len(trail)        # no dimension cut twice


def test_pairs_never_exceed_the_budget(cohort_cuts, journey_cfg):
    llm = make_llm([{"done": False, "next_question": {"dimension": "pd_category", "rationale": "a",
                                                       "also_dimension": "consultation_required"}}] * 5)
    _, trail = run_drilldown(llm, AggregateTool(cohort_cuts, journey_cfg["drilldown_dimensions"]),
                             GAP, {}, ROUTING, "pharmacy_checkout", budget=3)
    assert len(trail) == 3
