"""The reviewer's question reaches the Analyst as CONTEXT (never evidence), and
the resolver reads growth intent so the model — and the person confirming the
scope — know whether this is a diagnosis or a growth question."""
import json

from app.agents.analyst.aggregate_tool import AggregateTool
from app.agents.analyst.phase2 import run_drilldown
from app.agents.scope_resolver import describe, resolve_intent, resolve_scope
from app.journeys import load_journey

GAP = {"from_stage": "created", "to_stage": "confirmed", "entered": 100, "converted": 40, "lost": 60}


def test_growth_intent_needs_a_verb_and_an_object():
    assert resolve_intent("how can i increase transactions on consultations") == ("growth", ["increase", "consultations", "transactions"])
    assert resolve_intent("why do consultations get abandoned before the doctor joins") == ("diagnosis", [])
    assert resolve_intent("show me more detail on the payments drop") == ("diagnosis", [])   # 'more' alone is not growth


def test_scope_carries_the_intent_and_says_so():
    cfg = load_journey("consultation"); events = list((cfg.get("event_stage") or {}).keys())
    s = resolve_scope("how can i increase transactions on consultations", cfg, events, cfg["drilldown_dimensions"])
    assert s.intent == "growth"
    assert any(m.startswith("intent:growth") for m in s.matched_on)
    assert "growth question" in describe(s, "consultation").lower()
    d = resolve_scope("why do consultations get abandoned", cfg, events, cfg["drilldown_dimensions"])
    assert d.intent == "diagnosis" and "growth" not in describe(d, "consultation").lower()


def test_the_model_sees_the_question_as_context_only():
    cuts = json.load(open("fixtures/pd_checkout/cohort_cuts.json"))
    seen = {}
    def llm(ctx):
        seen.update(ctx)
        # a finding citing a number that appears only in the question must still be rejected downstream;
        # here we only check the context wiring
        return {"done": True, "findings": []}
    run_drilldown(llm, AggregateTool(cuts, ["item_count"]), GAP, {}, ["pharmacy_checkout"], "pharmacy_checkout",
                  user_question="how can i increase transactions by 25 percent", user_intent="growth")
    assert seen["user_question"] == "how can i increase transactions by 25 percent"
    assert seen["user_intent"] == "growth"
    assert 25 not in {v for v in seen.get("top_gap", {}).values() if isinstance(v, (int, float))}
