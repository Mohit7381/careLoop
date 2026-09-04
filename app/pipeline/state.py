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

    snapshot: dict[str, Any]           # Agent 1 (Fetcher) — Alief
    findings: list[dict[str, Any]]     # Agent 2 (Analyst) — Nakul
    drilldown_trail: list[dict[str, Any]]
    findings_rejected: list[dict[str, Any]]
    code_gaps: list[dict[str, Any]]    # Agent 3 (Code Scout) — Harshit
    trend_report: dict[str, Any]       # Reporter — Mohit
    voc: dict[str, Any]
    prd_draft: Optional[str]           # PRD Generator — Mohit
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
        snapshot={},
        findings=[],
        drilldown_trail=[],
        findings_rejected=[],
        code_gaps=[],
        trend_report={},
        voc={},
        prd_draft=None,
        artifacts=[],
        error=None,
    )
