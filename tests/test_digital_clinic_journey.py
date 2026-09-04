"""Journey #4 — Haloskin / Halofit treatment plans. Golden asserts on the frozen fixture."""
import json
from pathlib import Path

from app.agents.analyst import phase1
from app.agents.analyst.aggregate_tool import AggregateTool
from app.agents.scope_resolver import pick_journey
from app.journeys import all_journeys, load_journey
from app.schemas.contracts import Snapshot

FIX = Path(__file__).parent.parent / "fixtures" / "digital_clinic"
CFG = load_journey("digital_clinic")
SNAP = Snapshot(**json.loads((FIX / "snapshot.json").read_text()))
CUTS = json.loads((FIX / "cohort_cuts.json").read_text())


def _rate(dim, seg):
    tool = AggregateTool(CUTS, CFG["drilldown_dimensions"])
    rows = {r["segment"]: r for r in tool.aggregate("confirmed", dim)["rows"]}
    return rows[seg]["rate"]


def test_only_one_in_eight_plans_is_paid_for():
    table = phase1.funnel_table(SNAP, CFG["stages"])
    gap = phase1.largest_drop(table)
    assert (gap["from_stage"], gap["to_stage"]) == ("created", "confirmed")
    assert gap["lost"] == 6319 and abs(gap["share_of_prev"] - 0.8720) < 0.001
    by = {r["stage"]: r for r in table}
    assert by["activated"]["conversion_from_previous"] > 0.92            # once paid, plans start


def test_golden_rates():
    assert abs(_rate("service_type", "haloskin") - 0.1862) < 0.001
    assert abs(_rate("service_type", "halofit") - 0.0533) < 0.001
    assert abs(_rate("payer", "free") - 0.1768) < 0.001
    assert abs(_rate("payer", "cash") - 0.0697) < 0.001
    assert _rate("consultation_fee", "free_consultation") > _rate("consultation_fee", "paid_consultation")


def test_plan_type_is_distribution_only_because_it_would_be_tautological():
    tool = AggregateTool(CUTS, CFG["drilldown_dimensions"])
    assert "plan_type" not in tool.rate_bearing_dimensions
    assert "expiry_reason" not in tool.rate_bearing_dimensions
    assert set(tool.rate_bearing_dimensions) == {"service_type", "payer", "initial_consultation", "consultation_fee", "hour_of_day"}


def test_the_pipeline_placeholder_reason_is_an_artifact():
    assert "handle missing expired status record" in CFG["artifact_reasons"]
    clusters = phase1.cluster_reasons(SNAP.reasons, CFG["artifact_reasons"])
    flat = json.dumps(clusters)
    assert "erx expired" in flat and "361" in flat


def test_prompts_about_haloskin_pick_this_journey():
    js = all_journeys()
    assert pick_journey("how many haloskin treatment plans go unpaid, and why", js)[0] == "digital_clinic"
    assert pick_journey("how can we grow halofit subscriptions", js)[0] == "digital_clinic"
    assert pick_journey("why do consultations get abandoned before the doctor joins", js)[0] == "consultation"


def test_code_hints_and_routing():
    assert {"expire", "treatment", "activate"} <= set(CFG["code_hints"]["by_stage"]["digital_clinic"])
    assert CFG["routing"]["digital_clinic"][0] == "digital-clinic/treatment"
