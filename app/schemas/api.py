from typing import Any, Optional

from pydantic import BaseModel

from app.schemas.contracts import RunStatus


class CreateRunRequest(BaseModel):
    window_start: Optional[str] = None  # YYYY-MM-DD, Jakarta-time date; defaults to 30 days back
    window_end: Optional[str] = None
    dimensions: Optional[list[str]] = None


class CreateRunResponse(BaseModel):
    run_id: int
    status: RunStatus


class RunDetailResponse(BaseModel):
    run_id: int
    window_start: str
    window_end: str
    status: RunStatus
    config: dict[str, Any]
    snapshots: list[dict[str, Any]]
    findings: list[dict[str, Any]]
    artifacts: list[dict[str, Any]]
