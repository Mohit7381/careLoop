"""Agent 2 — the Analyst node. Ties phases 1-3 into one RunState transition.

Reads journey config; consumes state.snapshot (Fetcher's output) plus the
journey's cohort-cut fixture (via AggregateTool) and PII-scrubbed reviews;
writes state.findings / state.drilldown_trail / state.voc. Fails loudly:
any exception marks the run failed with failed_stage="analyzing" upstream.
"""
import json
from pathlib import Path
from typing import Any, Callable, Optional

from app.agents.analyst import phase1
from app.agents.analyst.aggregate_tool import AggregateTool
from app.agents.analyst.phase2 import run_drilldown
from app.agents.analyst.phase3_voc import corroborate, run_voc
from app.agents.analyst.validator import collect_numbers, filter_findings
from app.journeys import load_journey
from app.schemas.contracts import RunState, validate_routing_stage

FIXTURES = Path("fixtures")


def _default_routing_for_gap(gap: dict, journey_cfg: dict) -> str:
    """Map the funnel drop location to a routing category (Analyst's explicit
    decision, per the contract's routing-category design). Heuristic default:
    the journey's first routing key; the abandon-timer gap in PD routes to
    pharmacy_checkout where timor/oms owns order lifecycle."""
    keys = list(journey_cfg["routing"].keys())
    return "pharmacy_checkout" if "pharmacy_checkout" in keys else keys[0]


def run_analyst(state: RunState,
                llm: Callable[[dict[str, Any]], dict[str, Any]],
                cohort_cuts: Optional[dict] = None,
                reviews: Optional[list[dict]] = None) -> RunState:
    cfg = load_journey(state.journey)
    routing_keys = list(cfg["routing"].keys())

    # ---- phase 1: deterministic ----
    table = phase1.funnel_table(state.snapshot, cfg["stages"])
    gap = phase1.largest_drop(table)
    clusters = phase1.cluster_reasons(state.snapshot.reasons, cfg["artifact_reasons"])
    summary = {"funnel": table, "reason_clusters": clusters}

    # ---- phase 2: agentic drill-down ----
    if cohort_cuts is None and state.demo_mode:
        cuts_path = FIXTURES / state.journey / "cohort_cuts.json"
        cohort_cuts = json.loads(cuts_path.read_text()) if cuts_path.exists() else {}
    tool = AggregateTool(cohort_cuts or {}, cfg["drilldown_dimensions"])
    findings, trail = run_drilldown(
        llm, tool, gap or {}, summary, routing_keys,
        _default_routing_for_gap(gap or {}, cfg))

    # ---- evidence gate (accepts every number the model was shown) ----
    shown = collect_numbers(summary) | collect_numbers(gap or {})
    kept, rejected = filter_findings(findings, state.snapshot, trail, shown)
    gap_events = phase1.events_for_gap(
        gap, cfg.get("journey_events") or {}, state.snapshot.ct_events)
    for f in kept:
        validate_routing_stage(f.stage, routing_keys)
        # Warehouse findings all describe the same funnel gap, so they share
        # its bounding events. VoC findings carry theme_search_terms instead.
        f.journey_events = list(gap_events)

    # ---- phase 3: VoC ----
    voc_findings: list = []
    if reviews is None and state.demo_mode:
        rv_path = FIXTURES / state.journey / "reviews_scrubbed.json"
        reviews = json.loads(rv_path.read_text()) if rv_path.exists() else []
    if reviews:
        next_rank = (max((f.rank for f in kept), default=0)) + 1
        voc_findings, voc = run_voc(reviews, cfg["voc"], next_rank)
        for f in voc_findings:
            validate_routing_stage(f.stage, routing_keys)
        corroborate(kept, voc, cfg["voc"])
        state.voc = voc

    state.findings = kept + voc_findings
    state.drilldown_trail = trail
    state.status = "scanning_code"
    return state
