from typing import Any, Optional

from pydantic import BaseModel

from app.schemas.contracts import RunStatus


class CreateRunRequest(BaseModel):
    journey: str = "pd_checkout"
    window_start: Optional[str] = None  # YYYY-MM-DD, Jakarta-time date; defaults to 30 days back
    window_end: Optional[str] = None
    prev_window_start: Optional[str] = None
    prev_window_end: Optional[str] = None
    # Routing categories (payments, consultation, ...) — a post-run filter on
    # which findings surface. NOT drill-down cuts; those come from `prompt`.
    dimensions: Optional[list[str]] = None
    prompt: Optional[str] = None   # free text; resolved into a RunScope before the run


class CreateRunResponse(BaseModel):
    run_id: int
    status: RunStatus
    scope: Optional[dict[str, Any]] = None
    scope_summary: Optional[str] = None


class ResolveScopeRequest(BaseModel):
    journey: str = "pd_checkout"
    prompt: str


class ResolveScopeResponse(BaseModel):
    """What a prompt was understood to mean, before anything is run.

    The point of resolving separately is that a misreading is visible and
    correctable up front rather than discovered in a finished report.
    """

    scope: dict[str, Any]
    summary: str
    matched_on: list[str]
    unresolved: list[str]


class RunDetailResponse(BaseModel):
    run_id: int
    journey: str
    window_start: str
    window_end: str
    status: RunStatus
    failed_stage: Optional[str] = None
    config: dict[str, Any]
    snapshots: list[dict[str, Any]]
    findings: list[dict[str, Any]]
    code_gaps: list[dict[str, Any]]
    voc: dict[str, Any]
    scope: Optional[dict[str, Any]] = None
    drilldown_trail: list[dict[str, Any]]
    findings_rejected: list[dict[str, Any]] = []
    artifacts: list[dict[str, Any]]
    report_markdown: Optional[str] = None
    prd_markdown: Optional[str] = None


class DeliverResponse(BaseModel):
    run_id: int
    delivered: bool
    detail: str
