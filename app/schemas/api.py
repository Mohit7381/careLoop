from typing import Any, Optional

from pydantic import BaseModel

from app.schemas.contracts import RunStatus


class CreateRunRequest(BaseModel):
    journey: str = "pd_checkout"
    window_start: Optional[str] = None  # YYYY-MM-DD, Jakarta-time date; defaults to 30 days back
    window_end: Optional[str] = None
    prev_window_start: Optional[str] = None
    prev_window_end: Optional[str] = None
    dimensions: Optional[list[str]] = None


class CreateRunResponse(BaseModel):
    run_id: int
    status: RunStatus


class PrdSummary(BaseModel):
    finding_rank: int
    title: Optional[str] = None
    markdown: str
    edited: bool = False


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
    suggestions: list[dict[str, Any]]
    voc: dict[str, Any]
    drilldown_trail: list[dict[str, Any]]
    artifacts: list[dict[str, Any]]
    report_markdown: Optional[str] = None
    prd_markdown: Optional[str] = None  # the #1 finding's PRD only — kept for back-compat
    prds: list[PrdSummary] = []         # one per finding, up to MAX_PRDS_PER_RUN — NEW


class DeliverResponse(BaseModel):
    run_id: int
    delivered: bool
    detail: str


class PrdChatRequest(BaseModel):
    message: str


class PrdChatResponse(BaseModel):
    finding_rank: int
    reply: str
    markdown: str
    applied: bool
