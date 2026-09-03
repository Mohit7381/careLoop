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
    artifacts: list[dict[str, Any]]
