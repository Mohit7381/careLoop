"""
Agent 2 — Analyst. OWNER: Nakul.

Two-part analysis per FR-02/FR-03:
  (a) Deterministic: rank stage x segment drops, cluster recorded
      cancellation_reason values.
  (b) LLM drill-down: sphere-platform use case receives AGGREGATES ONLY
      (never row-level data) and produces ranked hypotheses for stages
      with no recorded reason, each citing specific numbers. A hypothesis
      with no citable evidence must be rejected before it leaves this node.
  (c) VoC corroboration: negative-review themes above the noise floor
      (>=20 reviews on the fixture) escalate as `origin: voc` findings.

Every finding's `stage` is a ROUTING CATEGORY (RoutingStage — consultation
| pharmacy_checkout | payments | re_engagement), not the funnel-stage id
from the snapshot — that's a judgment call about where the owning code
actually lives (see FUNNEL_STAGE_TO_ROUTING_STUB below), which Code Scout
then routes on with an exact-match lookup. Getting this right (rather
than the funnel-stage name) is what let the proven demo example resolve
correctly: the "payment_processing" funnel drop is caused by code that
lives in the consultation service, not payment-service.

This file stubs (b) with `_call_analyst_llm_stub` — swap for a real
sphere-platform call (use case: settings.llm_use_case_funnel_dropoff,
schema-validated, zero row-level fields) before Day 2. The deterministic
math (a) and the evidence-validator gate are real and should stay.
"""
from typing import Any

from app.pipeline.state import GraphState
from app.schemas.contracts import EvidenceItem, Finding, RoutingStage, SegmentFilter

VOC_ESCALATION_THRESHOLD = 20

# STUB — Nakul: this mapping is exactly the kind of judgment call the real LLM call should make
# (informed by where recorded reasons/code ownership actually point), not a fixed lookup. Kept
# here only so the pipeline has somewhere deterministic to start from on Day 1.
FUNNEL_STAGE_TO_ROUTING_STUB: dict[str, RoutingStage] = {
    "requested": "consultation",
    "payment_processing": "consultation",  # abandon-kill script lives in ConsultationDao, not payment-service
    "payment_failed": "payments",
    "confirmed": "consultation",
    "consultation_completed": "consultation",
    "erx_checkout": "pharmacy_checkout",
    "pharmacy_delivered": "pharmacy_checkout",
}


def _biggest_drop(stages: list[dict[str, Any]]) -> dict[str, Any]:
    """FR-02: identify the single largest absolute drop deterministically, before any LLM call."""
    ranked = sorted(stages, key=lambda s: s["entered"] - s["converted"], reverse=True)
    return ranked[0]


def _call_analyst_llm_stub(top_drop: dict[str, Any], reasons: list[dict[str, Any]]) -> Finding:
    """
    STUB — replace with a sphere-platform LLM call (funnel-dropoff-analysis use case).
    Input to the real call must be schema-validated aggregates only: conversion tables,
    segment comparisons, week-over-week deltas, the clustered reason table. Nakul: this
    is where the whitelisted aggregate() tool loop (10-query budget) also plugs in,
    populating drilldown_trail (and drilldown_ref on the finding it informed).
    """
    dropped = top_drop["entered"] - top_drop["converted"]
    matching_reasons = [r for r in reasons if top_drop["stage"] in r.get("cancellation_reason_group", "")]
    reason_count = sum(r["count"] for r in matching_reasons) if matching_reasons else dropped
    routing_stage = FUNNEL_STAGE_TO_ROUTING_STUB.get(top_drop["stage"], "consultation")

    return Finding(
        rank=1,
        origin="warehouse",
        stage=routing_stage,
        hypothesis=(
            f"{dropped}/wk {top_drop['stage']} drops disproportionately before conversion; "
            f"recorded reasons account for {reason_count} of {dropped} lost."
        ),
        segments=[SegmentFilter(dimension="funnel_stage", value=top_drop["stage"])],
        evidence=[
            EvidenceItem(type="snapshot", metric="entered", value=top_drop["entered"]),
            EvidenceItem(type="snapshot", metric="converted", value=top_drop["converted"]),
            EvidenceItem(type="snapshot", metric="dropped", value=dropped),
        ],
        confidence=0.7 if matching_reasons else 0.4,
        confirm_via=(
            "drill down by segment/channel on the reason table"
            if matching_reasons
            else "instrument a recorded cancellation_reason for this stage"
        ),
    )


def _voc_findings(voc: dict[str, Any], next_rank: int) -> list[Finding]:
    """
    STUB — themes here come pre-clustered from the fixture. The real pipeline has a
    dedicated `voc-theme-classification` sphere-platform use case (confirmed live in AI
    Studio project 7121, 2026-09-03) for turning raw scraped reviews into these theme
    buckets — that LLM call belongs here, before this function runs, not inside it.
    """
    findings = []
    rank = next_rank
    for theme in voc.get("themes", []):
        if theme["count"] < VOC_ESCALATION_THRESHOLD:
            continue
        quotes = theme.get("quotes", [])
        findings.append(
            Finding(
                rank=rank,
                origin="voc",
                stage=theme.get("routing_stage", "consultation"),
                hypothesis=f"Repeated negative reviews point to a '{theme['name']}' problem.",
                confidence=min(0.9, theme["count"] / 100),
                confirm_via="correlate against warehouse drop-off for the same routing category",
                theme=theme["name"],
                theme_search_terms=theme.get("search_terms", []),
                review_count=theme["count"],
                top_quotes=[q["text"] for q in quotes[:2]],
            )
        )
        rank += 1
    return findings


def analyst_node(state: GraphState) -> GraphState:
    snapshot = state["snapshot"]
    stages = snapshot["stages"]
    reasons = snapshot["reasons"]

    top_drop = _biggest_drop(stages)
    warehouse_finding = _call_analyst_llm_stub(top_drop, reasons)

    findings = [warehouse_finding] + _voc_findings(state["voc"], next_rank=2)

    # Evidence validator (FR-03 acceptance criteria): reject any finding with no citable number.
    validated = [f for f in findings if f.has_citable_evidence()]
    if not validated:
        return {
            **state,
            "status": "analyzing",
            "findings": [],
            "error": "insufficient_data: no finding produced citable evidence",
        }

    voc = dict(state["voc"])
    voc["per_finding_quotes"] = _match_quotes_to_findings(validated, voc.get("themes", []))

    return {
        **state,
        "status": "analyzing",
        "findings": [f.model_dump() for f in validated],
        "drilldown_trail": [],  # Nakul: append DrilldownStep entries from the aggregate() loop here
        "voc": voc,
    }


def _match_quotes_to_findings(findings: list[Finding], themes: list[dict[str, Any]]) -> dict[str, list[dict]]:
    """
    The demo's 'human moment': a VoC theme whose routing_stage matches a warehouse
    finding's stage means users are describing the same gap the numbers found —
    surface its quotes under that finding's rank so the report/PRD can show both.
    """
    by_stage: dict[str, dict] = {}
    for t in themes:
        by_stage.setdefault(t.get("routing_stage"), t)
    quotes_by_rank: dict[str, list[dict]] = {}
    for f in findings:
        theme = by_stage.get(f.stage)
        if theme and theme.get("quotes"):
            quotes_by_rank[str(f.rank)] = theme["quotes"]
    return quotes_by_rank
