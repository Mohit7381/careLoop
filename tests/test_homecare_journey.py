"""Journey #3 — Halolab homecare. Golden asserts on the frozen fixture."""
import json
from pathlib import Path

from app.agents.analyst import phase1
from app.agents.analyst.aggregate_tool import AggregateTool
from app.agents.scope_resolver import pick_journey
from app.journeys import all_journeys, load_journey
from app.schemas.contracts import Snapshot

FIX = Path(__file__).parent.parent / "fixtures" / "homecare"
CFG = load_journey("homecare")
SNAP = Snapshot(**json.loads((FIX / "snapshot.json").read_text()))
CUTS = json.loads((FIX / "cohort_cuts.json").read_text())


def _rate(dim, seg):
    tool = AggregateTool(CUTS, CFG["drilldown_dimensions"])
    rows = {r["segment"]: r for r in tool.aggregate("confirmed", dim)["rows"]}
    return rows[seg]["rate"]


def test_the_booking_step_is_the_whole_story():
    table = phase1.funnel_table(SNAP, CFG["stages"])
    gap = phase1.largest_drop(table)
    assert (gap["from_stage"], gap["to_stage"]) == ("created", "confirmed")
    assert gap["lost"] == 4804 and abs(gap["share_of_prev"] - 0.8144) < 0.001


def test_most_bookings_never_pick_a_slot():
    """4,267 of 5,899 bookings never reach the schedule step and none of them convert;
    once a slot is chosen the booking converts 52-80%."""
    tool = AggregateTool(CUTS, CFG["drilldown_dimensions"])
    rows = {r["segment"]: r for r in tool.aggregate("confirmed", "lead_time")["rows"]}
    assert rows["no_slot_chosen"]["entered"] == 4267 and rows["no_slot_chosen"]["converted"] == 0
    assert _rate("lead_time", "under_6_hours") > 0.79 and _rate("lead_time", "same_day") > 0.64


def test_golden_rates():
    assert abs(_rate("region", "Jakarta") - 0.7492) < 0.001
    assert _rate("region", "West Java") < 0.22 and _rate("region", "East Java") < 0.06
    assert abs(_rate("transaction_source", "halodoc_customer") - 0.1256) < 0.001
    assert _rate("transaction_source", "b2b_project") > 0.86 and _rate("transaction_source", "whatsapp_order") > 0.70
    assert abs(_rate("interface_type", "ios") - 0.1564) < 0.001


def test_payments_page_is_the_dominant_recorded_reason():
    clusters = phase1.cluster_reasons(SNAP.reasons, CFG["artifact_reasons"])
    flat = json.dumps(clusters)
    assert "customer went back from payments page" in flat and "3520" in flat


def test_rate_bearing_and_distribution_cuts():
    tool = AggregateTool(CUTS, CFG["drilldown_dimensions"])
    assert set(tool.rate_bearing_dimensions) == set(CFG["drilldown_dimensions"]) - {"abandon_reason"}


def test_prompts_about_lab_visits_pick_this_journey():
    js = all_journeys()
    assert pick_journey("how many homecare bookings do not get confirmed, and why", js)[0] == "homecare"
    assert pick_journey("why are lab test bookings dropping off outside jakarta", js)[0] == "homecare"
    assert pick_journey("why are users dropping off after adding items to cart", js)[0] == "pd_checkout"


def test_code_hints_are_the_verified_ones():
    assert {"abandon", "schedule", "slot"} <= set(CFG["code_hints"]["by_stage"]["homecare"])
    assert CFG["routing"]["homecare"][0] == "halolab/oms"
