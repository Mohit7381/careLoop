"""
LangGraph state schema for the CareLoop pipeline (v3, matching
app.schemas.contracts.RunState).

We thread plain dicts through the graph (LangGraph's native mode); each
node validates its inputs/outputs against the pydantic models in
app.schemas.contracts at its boundary, so a bad shape from any one
teammate's node fails loudly at the boundary instead of corrupting state
silently downstream. Nakul's and Harshit's real agent functions speak
RunState (pydantic) directly — the node wrappers in
app/pipeline/nodes/{analyst,code_scout}.py convert at the boundary.
"""
from typing import Any, Optional, TypedDict


class GraphState(TypedDict, total=False):
    run_id: int
    journey: str
    window_start: str
    window_end: str
    prev_window_start: Optional[str]
    prev_window_end: Optional[str]
    status: str
    demo_mode: bool
    failed_stage: Optional[str]
    scope: dict[str, Any]
    requested_dimensions: list[str]    # prompt-scoped analysis — decision #13 (routing-category filter)

    snapshot: dict[str, Any]           # Agent 1 (Fetcher) — Alief
    reviews: list[dict[str, Any]]      # Agent 1 (Fetcher) — Alief; PII-scrubbed Play Store reviews
    findings: list[dict[str, Any]]     # Agent 2 (Analyst) — Nakul
    growth_ideas: list[dict[str, Any]]  # Agent 2 (Analyst) — Nakul; phase 2's concluding-turn output
    top_gap_to_stage: Optional[str]    # Agent 2 (Analyst) — Nakul; the funnel stage every finding this run is about
    drilldown_trail: list[dict[str, Any]]
    findings_rejected: list[dict[str, Any]]
    code_gaps: list[dict[str, Any]]    # Agent 3 (Code Scout) — Harshit
    suggestions: list[dict[str, Any]]  # Agent 3 alt flow (Code Scout) — Harshit
    shipped_fixes: list[dict[str, Any]]  # Agent 3 (Code Scout) — Harshit; closed-loop impact
    feature_amplifications: list[dict[str, Any]]  # Reporter — Mohit; explore_shipped_feature output
    trend_report: dict[str, Any]       # Reporter — Mohit
    voc: dict[str, Any]
    prd_draft: Optional[str]           # PRD Generator — Mohit; #1 finding's PRD only, kept for back-compat
    prd_drafts: list[dict[str, Any]]   # PRD Generator — Mohit; one per finding (up to MAX_PRDS_PER_RUN), NEW
    prd_source: str                    # how the #1 draft was produced: llm | deterministic | rejection reason
    artifacts: list[dict[str, str]]    # [{kind, uri}]

    error: Optional[str]


def initial_state(
    run_id: int,
    window_start: str,
    window_end: str,
    demo_mode: bool,
    journey: str = "pd_checkout",
    prev_window_start: Optional[str] = None,
    prev_window_end: Optional[str] = None,
    scope: Optional[dict[str, Any]] = None,
    requested_dimensions: Optional[list[str]] = None,
) -> GraphState:
    return GraphState(
        run_id=run_id,
        journey=journey,
        window_start=window_start,
        window_end=window_end,
        prev_window_start=prev_window_start,
        prev_window_end=prev_window_end,
        status="fetching",
        demo_mode=demo_mode,
        failed_stage=None,
        scope=scope or {},
        requested_dimensions=requested_dimensions or [],
        snapshot={},
        reviews=[],
        findings=[],
        growth_ideas=[],
        top_gap_to_stage=None,
        drilldown_trail=[],
        findings_rejected=[],
        code_gaps=[],
        suggestions=[],
        shipped_fixes=[],
        feature_amplifications=[],
        trend_report={},
        voc={},
        prd_draft=None,
        prd_drafts=[],
        artifacts=[],
        error=None,
    )
