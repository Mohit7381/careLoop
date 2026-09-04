"""Findings are for product and ops readers: every cited row gets a plain-words
label alongside the raw string, and the model is handed the journey's own
words for stages and cuts."""
import json

from app.agents.analyst.aggregate_tool import AggregateTool
from app.agents.analyst.phase2 import run_drilldown
from app.agents.analyst.plain_language import humanise_evidence
from app.journeys import load_journey

CFG = load_journey("consultation")
LABELS = {"stage_labels": CFG["stage_labels"], "dimension_labels": CFG["dimension_labels"]}
GAP = {"from_stage": "created", "to_stage": "confirmed", "entered": 226615, "converted": 139104, "lost": 87511,
       "conversion_from_previous": 0.6138}


def test_a_cohort_row_reads_as_a_sentence():
    raw = '{"segment": "cash", "entered": 154950, "converted": 72093, "rate": 0.4653}'
    assert humanise_evidence(raw) == "cash: 154,950 people, 72,093 went on to the next step (46.5%)"


def test_the_top_gap_uses_the_journey_stage_words():
    raw = json.dumps(GAP)
    out = humanise_evidence(raw, CFG["stage_labels"])
    assert out == "87,511 people were lost between 'requested a consultation' and 'paid and confirmed' out of 226,615 (61.4% continued)"


def test_a_funnel_stage_row_and_a_reason_row():
    assert humanise_evidence('{"stage": "confirmed", "count": 139104, "conversion_from_previous": 0.6138}', CFG["stage_labels"]) \
        == "139,104 people paid and confirmed (61.4% of the previous step)"
    assert humanise_evidence('{"cancellation_reason": "abandoned by system", "count": 54015}') \
        == "54,015 left with the reason 'abandoned by system'"


def test_the_models_appended_number_and_prose_rows_still_parse():
    # the model often echoes a row and then appends ': 0.4' — the UI used to show that verbatim
    assert humanise_evidence('top_gap: lost: 87511, share_of_prev: 0.3862: 0.4').startswith("87,511 people were lost")


def test_unparseable_evidence_falls_back_to_the_raw_text():
    assert humanise_evidence("0.4653") == "0.4653"


def test_findings_carry_labels_and_the_model_sees_the_stage_words():
    cuts = json.load(open("fixtures/consultation/cohort_cuts.json"))
    seen = {}
    def llm(ctx):
        seen.update(ctx)
        return {"done": True, "findings": [{
            "hypothesis": "Cash payers convert far worse than insurance payers.", "stage": "consultation",
            "confidence": "high", "confirm_via": "A/B a pay-later option for cash payers",
            "evidence": ['{"segment": "cash", "entered": 154950, "converted": 72093, "rate": 0.4653}', "87511"],
        }]}
    findings, _, _ = run_drilldown(llm, AggregateTool(cuts, ["payer"]), GAP, {}, ["consultation"], "consultation",
                                   labels=LABELS)
    assert seen["stage_labels"]["created"] == "requested a consultation"
    assert seen["dimension_labels"]["payer"].startswith("how they pay")
    ev = findings[0].evidence
    assert ev[0].label == "cash: 154,950 people, 72,093 went on to the next step (46.5%)"
    assert ev[0].metric.startswith('{"segment": "cash"')          # raw string kept for audit
    assert ev[1].label == "87511"                                  # bare number: nothing to translate


def test_several_rows_in_one_string_are_translated_one_by_one():
    raw = 'phase1 funnel: {"stage": "created", "count": 226615}, {"stage": "confirmed", "count": 139104, "conversion_from_previous": 0.6}: 0.6'
    assert humanise_evidence(raw, CFG["stage_labels"]) == \
        "226,615 people requested a consultation; 139,104 people paid and confirmed (60.0% of the previous step)"


def test_a_quoted_reason_with_a_count_reads_as_a_reason():
    assert humanise_evidence('"abandoned by system": 54015') == "54,015 left with the reason 'abandoned by system'"
    assert humanise_evidence('"abandoned from the patient selection screen": 4134') == \
        "4,134 left with the reason 'abandoned from the patient selection screen'"

