"""
LangGraph state schema for the CareLoop pipeline.

We thread plain dicts through the graph (LangGraph's native mode) but every
node validates its inputs/outputs against the pydantic models in
app.schemas.contracts before touching them, so a bad shape from any one
teammate's node fails loudly at the boundary instead of corrupting state
silently downstream.
"""
from typing import Any, TypedDict


class GraphState(TypedDict, total=False):
    run_id: int
    window_start: str
    window_end: str
    status: str
    demo_mode: bool

    snapshot: dict[str, Any]           # Agent 1 (Fetcher) — Alief
    findings: list[dict[str, Any]]     # Agent 2 (Analyst) — Nakul
    drilldown_trail: list[dict[str, Any]]
    code_gaps: list[dict[str, Any]]    # Agent 3 (Code Scout) — Harshit
    trend_report: dict[str, Any]       # Reporter — Mohit
    voc: dict[str, Any]
    prd_draft: str | None              # PRD Generator — Mohit
    artifacts: list[dict[str, str]]    # [{kind, uri}]

    error: str | None


def initial_state(run_id: int, window_start: str, window_end: str, demo_mode: bool) -> GraphState:
    return GraphState(
        run_id=run_id,
        window_start=window_start,
        window_end=window_end,
        status="queued",
        demo_mode=demo_mode,
        snapshot={},
        findings=[],
        drilldown_trail=[],
        code_gaps=[],
        trend_report={},
        voc={},
        prd_draft=None,
        artifacts=[],
        error=None,
    )
