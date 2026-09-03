"""Drill-down loop with a scripted stub LLM — budget, whitelist, trail."""
from app.agents.analyst.aggregate_tool import AggregateTool
from app.agents.analyst.phase2 import run_drilldown

GAP = {"from_stage": "created", "to_stage": "confirmed", "lost": 417569, "share_of_prev": 0.6452}
ROUTING = ["pharmacy_checkout", "payments", "delivery", "stock", "re_engagement", "consultation"]


def make_llm(script):
    calls = iter(script)
    return lambda ctx: next(calls)


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
    assert len(trail) == 2
    assert trail[1].dimension == "consultation_required"
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
    assert _num("lost 417,569 (share_of_prev 0.6452)") == 417569.0
    assert _num("rate: 0.3002") == 0.3002
    assert _num(199417) == 199417.0
    assert _num("no numbers here") is None
